use std::io::Cursor;
use std::sync::{Arc, Mutex};
use async_trait::async_trait;
use openraft::{
    BasicNode, Entry, EntryPayload, LogId, LogState, RaftLogReader, RaftSnapshotBuilder, Snapshot,
    SnapshotMeta, StorageError, StorageIOError, StoredMembership, Vote, storage::RaftStorage,
};
use serde::{Deserialize, Serialize};
use sled::Tree;
use tracing::info;
use soundgate::{Admission, Effect, Event, Gate};
use super::{GateOp, GateWriteResponse, SoundGateTypeConfig};

pub fn open_db(path: &str) -> (Tree, Tree, Tree) {
    let db = sled::open(path).unwrap_or_else(|e| panic!("sled open {path}: {e}"));
    let logs = db.open_tree("logs").expect("open logs tree");
    let meta = db.open_tree("meta").expect("open meta tree");
    let fences = db.open_tree("fences").expect("open fences tree");
    (logs, meta, fences)
}

fn to_err<E: std::fmt::Display>(e: E) -> StorageError<u64> {
    StorageIOError::read_snapshot(None, &std::io::Error::other(e.to_string())).into()
}

#[derive(Serialize, Deserialize, Clone)]
struct SnapData {
    last_log_id: Option<LogId<u64>>,
    last_membership: StoredMembership<u64, BasicNode>,
    fences: Vec<Event>,
}

fn apply_op(gate: &mut Gate, op: &GateOp) -> Option<Admission> {
    match op {
        GateOp::Submit {
            run_id,
            effect_key,
            needs_approval,
        } => Some(gate.submit(Effect {
            run_id: run_id.clone(),
            effect_key: effect_key.clone(),
            needs_approval: *needs_approval,
        })),
        GateOp::Decide {
            run_id,
            effect_key,
            approved,
        } => Some(gate.decide(run_id, effect_key, *approved)),
        GateOp::Cancel { run_id } => {
            gate.cancel(run_id);
            None
        }
    }
}

fn fence_for(op: &GateOp, adm: &Option<Admission>) -> Option<Event> {
    match (op, adm) {
        (GateOp::Submit { run_id, effect_key, .. }, Some(Admission::Release))
        | (GateOp::Decide { run_id, effect_key, .. }, Some(Admission::Release)) => {
            Some(Event::Released {
                run_id: run_id.clone(),
                effect_key: effect_key.clone(),
            })
        }
        (GateOp::Decide { run_id, effect_key, .. }, Some(Admission::RefusedRejected)) => {
            Some(Event::Rejected {
                run_id: run_id.clone(),
                effect_key: effect_key.clone(),
            })
        }
        (GateOp::Cancel { run_id }, _) => Some(Event::Cancelled {
            run_id: run_id.clone(),
        }),
        _ => None,
    }
}

#[derive(Clone)]
pub struct SoundGateStore {
    logs: Tree,
    meta: Tree,
    fences: Tree,
    gate: Arc<Mutex<Gate>>,
    last_applied: Option<LogId<u64>>,
    last_membership: StoredMembership<u64, BasicNode>,
    snapshot_idx: u64,
    fence_seq: Arc<Mutex<u64>>,
}

impl SoundGateStore {
    pub fn new(logs: Tree, meta: Tree, fences: Tree) -> Self {
        let last_applied: Option<LogId<u64>> = meta
            .get(b"last_applied")
            .ok()
            .flatten()
            .and_then(|b| serde_json::from_slice(&b).ok());

        let last_membership: StoredMembership<u64, BasicNode> = meta
            .get(b"last_membership")
            .ok()
            .flatten()
            .and_then(|b| serde_json::from_slice(&b).ok())
            .unwrap_or_default();

        let snapshot_idx: u64 = meta
            .get(b"snapshot_idx")
            .ok()
            .flatten()
            .and_then(|b| serde_json::from_slice(&b).ok())
            .unwrap_or(0);

        let mut gate = Gate::new();
        let mut max_seq: u64 = 0;
        let mut recovered = 0usize;

        for kv in fences.iter() {
            if let Ok((k, v)) = kv {
                if k.len() == 8 {
                    max_seq = max_seq.max(u64::from_be_bytes(k[..8].try_into().unwrap()) + 1);
                }
                if let Ok(ev) = serde_json::from_slice::<Event>(&v) {
                    gate.apply(&ev);
                    recovered += 1;
                }
            }
        }

        if recovered > 0 {
            info!("soundgate-raft: recovered {recovered} fence event(s) from sled");
        }

        Self {
            logs,
            meta,
            fences,
            gate: Arc::new(Mutex::new(gate)),
            last_applied,
            last_membership,
            snapshot_idx,
            fence_seq: Arc::new(Mutex::new(max_seq)),
        }
    }

    #[inline]
    fn log_key(index: u64) -> [u8; 8] {
        index.to_be_bytes()
    }

    fn get_meta<T: for<'de> Deserialize<'de>>(&self, key: &[u8]) -> Option<T> {
        let bytes = self.meta.get(key).ok()??;
        serde_json::from_slice(&bytes).ok()
    }

    fn put_meta<T: Serialize>(&self, key: &[u8], val: &T) {
        let bytes = serde_json::to_vec(val).expect("serialize meta");
        self.meta.insert(key, bytes).expect("sled meta insert");
    }

    fn last_purged_from_db(&self) -> Option<LogId<u64>> {
        self.get_meta(b"last_purged")
    }

    fn record_fence(&self, ev: &Event) {
        let mut seq = self.fence_seq.lock().unwrap();
        let key = seq.to_be_bytes();
        *seq += 1;
        drop(seq);

        let val = serde_json::to_vec(ev).expect("serialize fence");
        self.fences.insert(key, val).expect("sled fence insert");
    }

    fn dump_fences(&self) -> Vec<Event> {
        self.fences
            .iter()
            .filter_map(|kv| kv.ok())
            .filter_map(|(_, v)| serde_json::from_slice::<Event>(&v).ok())
            .collect()
    }
}

#[async_trait]
impl RaftLogReader<SoundGateTypeConfig> for SoundGateStore {
    async fn get_log_state(&mut self) -> Result<LogState<SoundGateTypeConfig>, StorageError<u64>> {
        let last_purged = self.last_purged_from_db();

        let last = self
            .logs
            .last()
            .ok()
            .flatten()
            .and_then(|(_, v)| serde_json::from_slice::<Entry<SoundGateTypeConfig>>(&v).ok())
            .map(|e| e.log_id)
            .or(last_purged);

        Ok(LogState {
            last_purged_log_id: last_purged,
            last_log_id: last,
        })
    }

    async fn try_get_log_entries<RB>(
        &mut self,
        range: RB,
    ) -> Result<Vec<Entry<SoundGateTypeConfig>>, StorageError<u64>>
    where
        RB: std::ops::RangeBounds<u64> + Clone + std::fmt::Debug + Send + Sync,
    {
        use std::ops::Bound;
        let start_idx = match range.start_bound() {
            Bound::Included(&s) => s,
            Bound::Excluded(&s) => s.saturating_add(1),
            Bound::Unbounded => 0,
        };

        let end_idx: Option<u64> = match range.end_bound() {
            Bound::Included(&e) => Some(e),
            Bound::Excluded(&e) => Some(e.saturating_sub(1)),
            Bound::Unbounded => None,
        };

        let start_key = Self::log_key(start_idx);
        let mut entries = Vec::new();

        for res in self.logs.range(start_key..) {
            let (k, v) = res.map_err(to_err)?;
            let idx = u64::from_be_bytes(k[..8].try_into().unwrap());
            if let Some(end) = end_idx {
                if idx > end {
                    break;
                }
            }
            let entry: Entry<SoundGateTypeConfig> = serde_json::from_slice(&v).map_err(to_err)?;
            entries.push(entry);
        }
        Ok(entries)
    }
}

#[async_trait]
impl RaftSnapshotBuilder<SoundGateTypeConfig> for SoundGateStore {
    async fn build_snapshot(&mut self) -> Result<Snapshot<SoundGateTypeConfig>, StorageError<u64>> {
        self.snapshot_idx += 1;
        let fences = self.dump_fences();

        let snap = SnapData {
            last_log_id: self.last_applied,
            last_membership: self.last_membership.clone(),
            fences,
        };

        let bytes =
            serde_json::to_vec(&snap).map_err(|e| StorageIOError::read_snapshot(None, &e))?;

        self.put_meta(b"snapshot_data", &snap);
        self.put_meta(b"snapshot_idx", &self.snapshot_idx);

        let snapshot_id = format!(
            "snap-{}-{}",
            self.last_applied.map(|l| l.index).unwrap_or(0),
            self.snapshot_idx
        );

        let meta = SnapshotMeta {
            last_log_id: self.last_applied,
            last_membership: self.last_membership.clone(),
            snapshot_id,
        };

        info!(
            "soundgate-raft: snapshot idx={} fences={}",
            self.snapshot_idx,
            snap.fences.len()
        );

        Ok(Snapshot {
            meta,
            snapshot: Box::new(Cursor::new(bytes)),
        })
    }
}

#[async_trait]
impl RaftStorage<SoundGateTypeConfig> for SoundGateStore {
    type LogReader = Self;
    type SnapshotBuilder = Self;

    async fn save_vote(&mut self, vote: &Vote<u64>) -> Result<(), StorageError<u64>> {
        self.put_meta(b"vote", vote);
        Ok(())
    }

    async fn read_vote(&mut self) -> Result<Option<Vote<u64>>, StorageError<u64>> {
        Ok(self.get_meta(b"vote"))
    }

    async fn get_log_reader(&mut self) -> Self::LogReader {
        self.clone()
    }

    async fn append_to_log<I>(&mut self, entries: I) -> Result<(), StorageError<u64>>
    where
        I: IntoIterator<Item = Entry<SoundGateTypeConfig>> + Send,
    {
        for e in entries {
            let key = Self::log_key(e.log_id.index);
            let val = serde_json::to_vec(&e).map_err(to_err)?;
            self.logs.insert(key, val).map_err(to_err)?;
        }

        Ok(())
    }

    async fn delete_conflict_logs_since(
        &mut self,
        log_id: LogId<u64>,
    ) -> Result<(), StorageError<u64>> {
        let start = Self::log_key(log_id.index);
        let keys: Vec<sled::IVec> = self
            .logs
            .range(start..)
            .filter_map(|r| r.ok().map(|(k, _)| k))
            .collect();
        for k in keys {
            self.logs.remove(k).map_err(to_err)?;
        }
        Ok(())
    }

    async fn purge_logs_upto(&mut self, log_id: LogId<u64>) -> Result<(), StorageError<u64>> {
        let end = Self::log_key(log_id.index.saturating_add(1));
        let keys: Vec<sled::IVec> = self
            .logs
            .range(..end)
            .filter_map(|r| r.ok().map(|(k, _)| k))
            .collect();
        for k in keys {
            self.logs.remove(k).map_err(to_err)?;
        }
        self.put_meta(b"last_purged", &log_id);
        Ok(())
    }

    async fn last_applied_state(
        &mut self,
    ) -> Result<(Option<LogId<u64>>, StoredMembership<u64, BasicNode>), StorageError<u64>> {
        Ok((self.last_applied, self.last_membership.clone()))
    }

    async fn apply_to_state_machine(
        &mut self,
        entries: &[Entry<SoundGateTypeConfig>],
    ) -> Result<Vec<GateWriteResponse>, StorageError<u64>> {
        let mut responses = Vec::with_capacity(entries.len());
        let mut newest: Option<LogId<u64>> = None;
        for entry in entries {
            let log_id = entry.log_id;

            let resp = match &entry.payload {
                EntryPayload::Blank => GateWriteResponse::none(),

                EntryPayload::Membership(m) => {
                    self.last_membership = StoredMembership::new(Some(log_id), m.clone());
                    self.put_meta(b"last_membership", &self.last_membership);
                    GateWriteResponse::none()
                }

                EntryPayload::Normal(op) => {
                    let admission = {
                        let mut g = self.gate.lock().unwrap();
                        apply_op(&mut g, op)
                    };

                    if let Some(ev) = fence_for(op, &admission) {
                        self.record_fence(&ev);
                    }

                    match admission {
                        Some(a) => GateWriteResponse::some(a),
                        None => GateWriteResponse::none(),
                    }
                }
            };

            self.last_applied = Some(log_id);
            newest = Some(log_id);
            responses.push(resp);
        }

        if let Some(log_id) = newest {
            self.put_meta(b"last_applied", &log_id);
        }

        Ok(responses)
    }

    async fn get_snapshot_builder(&mut self) -> Self::SnapshotBuilder {
        self.clone()
    }

    async fn begin_receiving_snapshot(&mut self) -> Result<Box<Cursor<Vec<u8>>>, StorageError<u64>> {
        Ok(Box::new(Cursor::new(Vec::new())))
    }

    async fn install_snapshot(
        &mut self,
        meta: &SnapshotMeta<u64, BasicNode>,
        snapshot: Box<Cursor<Vec<u8>>>,
    ) -> Result<(), StorageError<u64>> {
        let bytes = snapshot.into_inner();
        let snap: SnapData = serde_json::from_slice(&bytes)
            .map_err(|e| StorageIOError::read_snapshot(Some(meta.signature()), &e))?;

        let mut gate = Gate::new();

        for ev in &snap.fences {
            gate.apply(ev);
        }

        self.fences.clear().map_err(to_err)?;
        {
            let mut seq = self.fence_seq.lock().unwrap();
            *seq = 0;

            for ev in &snap.fences {
                let key = seq.to_be_bytes();
                *seq += 1;
                let val = serde_json::to_vec(ev).map_err(to_err)?;
                self.fences.insert(key, val).map_err(to_err)?;
            }
        }

        {
            let mut g = self.gate.lock().unwrap();
            *g = gate;
        }

        self.put_meta(b"snapshot_data", &snap);
        self.put_meta(b"last_applied", &snap.last_log_id);
        self.put_meta(b"last_membership", &snap.last_membership);
        self.last_applied = snap.last_log_id;
        self.last_membership = snap.last_membership;

        info!("soundgate-raft: snapshot installed, {} fences", snap.fences.len());
        Ok(())
    }

    async fn get_current_snapshot(
        &mut self,
    ) -> Result<Option<Snapshot<SoundGateTypeConfig>>, StorageError<u64>> {
        let Some(snap) = self.get_meta::<SnapData>(b"snapshot_data") else {
            return Ok(None);
        };

        let bytes =
            serde_json::to_vec(&snap).map_err(|e| StorageIOError::read_snapshot(None, &e))?;

        let snapshot_id = format!(
            "snap-persisted-{}",
            snap.last_log_id.map(|l| l.index).unwrap_or(0)
        );

        let meta = SnapshotMeta {
            last_log_id: snap.last_log_id,
            last_membership: snap.last_membership,
            snapshot_id,
        };

        Ok(Some(Snapshot {
            meta,
            snapshot: Box::new(Cursor::new(bytes)),
        }))
    }
}