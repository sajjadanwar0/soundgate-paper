//! SOUNDGATE replicated admission core — openraft 0.8.4 type configuration.
//!
//! Design in one line: the Raft log entry is the admission OPERATION (submit /
//! decide / cancel), and the state machine is the existing `soundgate::Gate`.
//! Every node applies the same committed ops in the same order, so every node
//! reaches identical gate state; the verdict is produced at apply time (on the
//! leader) and returned to the caller. This is the canonical Raft shape
//! (propose -> commit -> apply), which is why it does not require touching the
//! gate's submit/decide logic at all.
//!
//! Relationship to the single-node WAL (main.rs): the WAL fsyncs the *derived
//! fence events* (Released/Rejected/Cancelled) before acknowledging. Here the
//! same admission is instead committed to a majority of the cluster before
//! acknowledging. The reply-after-durability discipline is identical; only the
//! durability substrate changes (local fsync -> Raft majority commit). Held
//! effects remain non-durable across a *snapshot* boundary exactly as in the
//! WAL model (a lost hold is a fail-closed re-hold).

use std::io::Cursor;
use std::sync::Arc;

use openraft::{BasicNode, Config, Entry, SnapshotPolicy, storage::Adaptor};
use serde::{Deserialize, Serialize};
use soundgate::Admission;

pub mod network;
pub mod store;

pub use network::SoundGateNetworkFactory;
pub use store::{SoundGateStore, open_db};

/// A replicated admission operation. This is the Raft log entry payload — the
/// operation, NOT the derived verdict. Mirrors the wire protocol in
/// `main.rs` (submit / decide / cancel); `ping` is not replicated.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case")]
pub enum GateOp {
    Submit {
        run_id: String,
        effect_key: String,
        #[serde(default)]
        needs_approval: bool,
    },
    Decide {
        run_id: String,
        effect_key: String,
        approved: bool,
    },
    Cancel {
        run_id: String,
    },
}

/// The Raft state-machine response: the `Admission` verdict the leader's apply
/// produced. `None` for a cancel (which acks with no verdict) and for
/// non-data entries (Blank / Membership).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GateWriteResponse {
    pub admission: Option<Admission>,
}

impl GateWriteResponse {
    pub fn none() -> Self {
        Self { admission: None }
    }
    pub fn some(a: Admission) -> Self {
        Self { admission: Some(a) }
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct SoundGateTypeConfig;

impl openraft::RaftTypeConfig for SoundGateTypeConfig {
    type D = GateOp;
    type R = GateWriteResponse;
    type NodeId = u64;
    type Node = BasicNode;
    type Entry = Entry<Self>;
    type SnapshotData = Cursor<Vec<u8>>;
}

/// The Adaptor lets a single `RaftStorage` impl serve as both the log store
/// and the state machine (openraft 0.8.x split storage).
pub type SoundGateAdaptor = Adaptor<SoundGateTypeConfig, SoundGateStore>;
pub type SoundGateRaft = openraft::Raft<
    SoundGateTypeConfig,
    SoundGateNetworkFactory,
    SoundGateAdaptor,
    SoundGateAdaptor,
>;

/// Raft timing — identical to the S-Bus deployment this mirrors: 250 ms
/// heartbeat, 500–1000 ms election window, snapshot every 500 committed
/// entries, keep 200 entries after a snapshot so a lagging follower can catch
/// up from the log rather than a full snapshot transfer.
pub fn build_raft_config() -> Arc<Config> {
    Arc::new(Config {
        cluster_name: "soundgate-cluster".into(),
        heartbeat_interval: 250,
        election_timeout_min: 500,
        election_timeout_max: 1000,
        max_in_snapshot_log_to_keep: 200,
        snapshot_policy: SnapshotPolicy::LogsSinceLast(500),
        max_payload_entries: 64,
        ..Default::default()
    })
}