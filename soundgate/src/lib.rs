#[cfg(feature = "python")]
mod python;

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

type EffectId = (String, String);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Effect {
    pub run_id: String,
    pub effect_key: String,
    pub needs_approval: bool,
}

impl Effect {
    fn id(&self) -> EffectId {
        (self.run_id.clone(), self.effect_key.clone())
    }
}

fn id_of(run_id: &str, effect_key: &str) -> EffectId {
    (run_id.to_string(), effect_key.to_string())
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case", tag = "verdict")]
pub enum Admission {
    Release,
    HeldForApproval,
    RefusedCancelled,
    RefusedDuplicate,
    RefusedRejected,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "ev", rename_all = "snake_case")]
pub enum Event {
    Released { run_id: String, effect_key: String },
    Rejected { run_id: String, effect_key: String },
    Cancelled { run_id: String },
    // 2026-10-02 (final files, Access-2026-43496): CloseRun is durable. The
    // paper's bounded-state claim (Sec. V, deployment obligations) needs the
    // deployed server, not only the library, to close runs and replay closes.
    Closed { run_id: String },
}

#[derive(Debug, Default)]
pub struct Gate {
    released: HashSet<EffectId>,
    cancelled: HashSet<String>,
    pending: HashMap<EffectId, Effect>,
    rejected: HashSet<EffectId>,
    closed: HashSet<String>,
}

impl Gate {
    pub fn new() -> Self {
        Gate::default()
    }

    pub fn submit(&mut self, e: Effect) -> Admission {
        if self.cancelled.contains(&e.run_id) || self.closed.contains(&e.run_id) {
            return Admission::RefusedCancelled;
        }

        let id = e.id();

        if self.released.contains(&id) {
            return Admission::RefusedDuplicate;
        }

        if self.rejected.contains(&id) {
            return Admission::RefusedRejected;
        }

        if self.pending.contains_key(&id) {
            return Admission::HeldForApproval;
        }

        if e.needs_approval {
            self.pending.insert(id, e);
            Admission::HeldForApproval
        } else {
            self.released.insert(id);
            Admission::Release
        }
    }

    pub fn decide(&mut self, run_id: &str, effect_key: &str, approved: bool) -> Admission {
        let id = id_of(run_id, effect_key);
        let effect = match self.pending.remove(&id) {
            Some(e) => e,
            None => {
                if self.cancelled.contains(run_id) || self.closed.contains(run_id) {
                    return Admission::RefusedCancelled;
                }

                if self.released.contains(&id) {
                    return Admission::RefusedDuplicate;
                }

                if !approved {
                    self.rejected.insert(id);
                    return Admission::RefusedRejected;
                }

                return Admission::RefusedDuplicate;
            }
        };

        if self.cancelled.contains(&effect.run_id) || self.closed.contains(&effect.run_id) {
            return Admission::RefusedCancelled;
        }

        if approved {
            self.released.insert(id);
            Admission::Release
        } else {
            self.rejected.insert(id);
            Admission::RefusedRejected
        }
    }

    pub fn cancel(&mut self, run_id: &str) {
        self.cancelled.insert(run_id.to_string());

        let drop: Vec<EffectId> = self
            .pending
            .keys()
            .filter(|(run, _)| run == run_id)
            .cloned()
            .collect();

        for k in drop {
            self.pending.remove(&k);
        }
    }

    pub fn close_run(&mut self, run_id: &str) {
        self.closed.insert(run_id.to_string());
        self.released.retain(|(r, _)| r != run_id);
        self.rejected.retain(|(r, _)| r != run_id);

        let drop: Vec<EffectId> =
            self.pending.keys().filter(|(r, _)| r == run_id).cloned().collect();

        for k in drop {
            self.pending.remove(&k);
        }
    }

    #[cfg(feature = "conformance")]
    pub fn conformance_snapshot(&self) -> (
        std::collections::BTreeSet<(u16, u16)>,
        std::collections::BTreeSet<(u16, u16)>,
        std::collections::BTreeSet<(u16, u16)>,
        std::collections::BTreeSet<u16>,
        std::collections::BTreeSet<u16>,
    ) {
        fn p(id: &EffectId) -> (u16, u16) {
            (id.0.parse().unwrap(), id.1.parse().unwrap())
        }
        (
            self.released.iter().map(p).collect(),
            self.rejected.iter().map(p).collect(),
            self.pending.keys().map(p).collect(),
            self.cancelled.iter().map(|s| s.parse().unwrap()).collect(),
            self.closed.iter().map(|s| s.parse().unwrap()).collect(),
        )
    }

    pub fn is_cancelled(&self, run_id: &str) -> bool {
        self.cancelled.contains(run_id)
    }

    pub fn is_closed(&self, run_id: &str) -> bool {
        self.closed.contains(run_id)
    }

    pub fn state_len(&self) -> usize {
        self.released.len() + self.rejected.len() + self.pending.len()
    }

    pub fn state_len_for(&self, run_id: &str) -> usize {
        self.released.iter().filter(|(r, _)| r == run_id).count()
            + self.rejected.iter().filter(|(r, _)| r == run_id).count()
            + self.pending.keys().filter(|(r, _)| r == run_id).count()
    }
    pub fn pending_count(&self) -> usize {
        self.pending.len()
    }

    pub fn apply(&mut self, ev: &Event) {
        match ev {
            // A record for a closed run is dead state: the run fence refuses
            // every later submit and decide of that run before any identity
            // lookup, so dropping it changes no verdict. Skipping it keeps
            // replay exact when a Released was logged after the run's Closed
            // (the handler logs after releasing the gate lock).
            Event::Released { run_id, .. } | Event::Rejected { run_id, .. }
                if self.closed.contains(run_id) => {}
            Event::Released { run_id, effect_key } => {
                self.released.insert((run_id.clone(), effect_key.clone()));
            }
            Event::Rejected { run_id, effect_key } => {
                self.rejected.insert((run_id.clone(), effect_key.clone()));
            }
            Event::Cancelled { run_id } => self.cancel(run_id),
            Event::Closed { run_id } => self.close_run(run_id),
        }
    }

    /// The smallest event log whose replay rebuilds this gate's durable state
    /// (released, rejected, cancelled, closed), in a deterministic order.
    /// Pending holds are deliberately not durable: losing a hold is
    /// conservative and a resubmission re-holds. Used for WAL compaction.
    pub fn durable_events(&self) -> Vec<Event> {
        let mut closed: Vec<&String> = self.closed.iter().collect();
        closed.sort();
        let mut cancelled: Vec<&String> = self.cancelled.iter().collect();
        cancelled.sort();
        let mut released: Vec<&EffectId> = self.released.iter().collect();
        released.sort();
        let mut rejected: Vec<&EffectId> = self.rejected.iter().collect();
        rejected.sort();

        closed
            .into_iter()
            .map(|r| Event::Closed { run_id: r.clone() })
            .chain(cancelled.into_iter().map(|r| Event::Cancelled { run_id: r.clone() }))
            .chain(released.into_iter().map(|(r, k)| Event::Released {
                run_id: r.clone(),
                effect_key: k.clone(),
            }))
            .chain(rejected.into_iter().map(|(r, k)| Event::Rejected {
                run_id: r.clone(),
                effect_key: k.clone(),
            }))
            .collect()
    }

    /// Number of runs whose fence is a closed-run record (one per closed run).
    pub fn closed_count(&self) -> usize {
        self.closed.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn eff(run: &str, key: &str, approval: bool) -> Effect {
        Effect { run_id: run.into(), effect_key: key.into(), needs_approval: approval }
    }

    #[test]
    fn property1_hold_until_decided() {
        let mut g = Gate::new();
        assert_eq!(g.submit(eff("r1", "send_email", true)), Admission::HeldForApproval);
        assert_eq!(g.pending_count(), 1);
    }

    #[test]
    fn property2_reject_cancels_effect() {
        let mut g = Gate::new();
        g.submit(eff("r1", "send_email", true));
        assert_eq!(g.decide("r1", "send_email", false), Admission::RefusedRejected);
        // and a later resubmission of the same identity stays rejected
        assert_eq!(g.submit(eff("r1", "send_email", true)), Admission::RefusedRejected);
    }

    #[test]
    fn property3_dedup_on_replay() {
        let mut g = Gate::new();
        assert_eq!(g.submit(eff("r1", "charge_card", false)), Admission::Release);
        assert_eq!(g.submit(eff("r1", "charge_card", false)), Admission::RefusedDuplicate);
    }

    #[test]
    fn property3_dedup_after_approval() {
        let mut g = Gate::new();
        g.submit(eff("r1", "deploy", true));
        assert_eq!(g.decide("r1", "deploy", true), Admission::Release);
        assert_eq!(g.submit(eff("r1", "deploy", true)), Admission::RefusedDuplicate);
    }

    #[test]
    fn property4_fence_on_cancel_blocks_zombie() {
        let mut g = Gate::new();
        g.cancel("r1");
        assert_eq!(g.submit(eff("r1", "post_webhook", false)), Admission::RefusedCancelled);
    }

    #[test]
    fn property4_cancel_drops_held_effect() {
        let mut g = Gate::new();
        g.submit(eff("r1", "send_email", true));
        g.cancel("r1");
        assert_eq!(g.pending_count(), 0);
        assert_eq!(g.decide("r1", "send_email", true), Admission::RefusedCancelled);
    }

    #[test]
    fn unrelated_runs_unaffected_by_cancel() {
        let mut g = Gate::new();
        g.cancel("r1");
        assert_eq!(g.submit(eff("r2", "ok_effect", false)), Admission::Release);
    }

    #[test]
    fn g1_cross_run_key_reuse_allowed() {
        let mut g = Gate::new();
        assert_eq!(g.submit(eff("run_A", "charge_card", false)), Admission::Release);
        assert_eq!(g.submit(eff("run_B", "charge_card", false)), Admission::Release);
        assert_eq!(g.submit(eff("run_A", "charge_card", false)), Admission::RefusedDuplicate);
    }

    #[test]
    fn g1_cross_run_rejection_does_not_bleed() {
        let mut g = Gate::new();
        g.submit(eff("run_A", "send_email", true));
        assert_eq!(g.decide("run_A", "send_email", false), Admission::RefusedRejected);
        assert_eq!(g.submit(eff("run_B", "send_email", false)), Admission::Release);
    }

    #[test]
    fn g1_approve_after_cancel_reports_cancelled() {
        let mut g = Gate::new();
        g.submit(eff("r1", "send_email", true));
        g.cancel("r1");
        assert_eq!(g.decide("r1", "send_email", true), Admission::RefusedCancelled);
    }

    #[test]
    fn g1_cross_run_pending_no_clobber() {
        let mut g = Gate::new();
        assert_eq!(g.submit(eff("run_A", "deploy", true)), Admission::HeldForApproval);
        assert_eq!(g.submit(eff("run_B", "deploy", true)), Admission::HeldForApproval);
        assert_eq!(g.pending_count(), 2);
        assert_eq!(g.decide("run_B", "deploy", true), Admission::Release);
        assert_eq!(g.decide("run_A", "deploy", false), Admission::RefusedRejected);
        assert_eq!(g.submit(eff("run_B", "deploy", true)), Admission::RefusedDuplicate);
    }

    #[test]
    fn wal_replay_reconstructs_fences() {
        let events = vec![
            Event::Released { run_id: "r1".into(), effect_key: "pay".into() },
            Event::Rejected { run_id: "r1".into(), effect_key: "mail".into() },
            Event::Cancelled { run_id: "r2".into() },
        ];

        let mut g = Gate::new();

        for e in &events {
            g.apply(e);
        }

        assert_eq!(g.submit(eff("r1", "pay", false)), Admission::RefusedDuplicate);
        assert_eq!(g.submit(eff("r1", "mail", true)), Admission::RefusedRejected);
        assert_eq!(g.submit(eff("r2", "late", false)), Admission::RefusedCancelled);
        assert_eq!(g.submit(eff("r3", "pay", false)), Admission::Release);
    }

    #[test]
    fn close_run_fences_and_compacts() {
        let mut g = Gate::new();
        g.submit(eff("r1", "a", false));
        g.submit(eff("r1", "b", true));
        g.submit(eff("r1", "c", true));
        g.decide("r1", "c", false);
        assert_eq!(g.state_len(), 3);
        g.close_run("r1");
        assert_eq!(g.state_len(), 0);
        assert_eq!(g.submit(eff("r1", "a", false)), Admission::RefusedCancelled);
        assert_eq!(g.submit(eff("r1", "c", false)), Admission::RefusedCancelled);
        assert_eq!(g.decide("r1", "b", true), Admission::RefusedCancelled);
        assert_eq!(g.submit(eff("r2", "a", false)), Admission::Release);
    }

    #[test]
    fn close_run_does_not_leak_release_after_compaction() {
        let mut g = Gate::new();

        assert_eq!(g.submit(eff("r1", "charge", false)), Admission::Release);
        g.close_run("r1");
        assert_eq!(g.state_len(), 0);
        assert_eq!(g.submit(eff("r1", "charge", false)), Admission::RefusedCancelled);
    }

    #[test]
    fn i1_late_reject_of_released_is_duplicate() {
        let mut g = Gate::new();
        assert_eq!(g.submit(eff("r1", "k1", false)), Admission::Release);
        assert_eq!(g.decide("r1", "k1", false), Admission::RefusedDuplicate);
        assert_eq!(g.submit(eff("r1", "k1", true)), Admission::RefusedDuplicate);
        assert_eq!(g.submit(eff("r1", "k2", false)), Admission::Release);
    }

    #[test]
    fn randomized_invariants_hold() {
        let mut seed: u64 = 0x9E3779B97F4A7C15;

        let mut rng = || {
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            (seed >> 33) as u32
        };

        for _ in 0..2000 {
            let mut g = Gate::new();
            let mut ever_released: HashSet<EffectId> = HashSet::new();
            let mut cancelled_or_closed: HashSet<String> = HashSet::new();
            let runs = ["a", "b", "c"];
            let keys = ["x", "y", "z"];

            for _ in 0..40 {
                let run = runs[(rng() % 3) as usize].to_string();
                let key = keys[(rng() % 3) as usize].to_string();
                let id = (run.clone(), key.clone());
                match rng() % 6 {
                    0 | 1 => {
                        let approval = rng() % 2 == 0;
                        let v = g.submit(eff(&run, &key, approval));

                        if cancelled_or_closed.contains(&run) {
                            assert_ne!(v, Admission::Release,
                                       "released from fenced run {run}/{key}");
                        }

                        if v == Admission::Release {
                            assert!(!ever_released.contains(&id),
                                    "double release of {run}/{key}");
                            ever_released.insert(id);
                        }
                    }
                    2 => {
                        let approve = rng() % 2 == 0;
                        let v = g.decide(&run, &key, approve);

                        if ever_released.contains(&id) {
                            assert_ne!(v, Admission::RefusedRejected,
                                       "late reject recorded on released {run}/{key}");
                        }

                        if v == Admission::Release {
                            assert!(!cancelled_or_closed.contains(&run),
                                    "decide-released a fenced run {run}");
                            assert!(!ever_released.contains(&id),
                                    "double release via decide of {run}/{key}");
                            ever_released.insert(id);
                        }
                    }
                    3 => {
                        g.cancel(&run);
                        cancelled_or_closed.insert(run);
                    }
                    4 => {
                        g.close_run(&run);
                        assert!(!g.released.iter().any(|(r, _)| r == &run));
                        assert!(!g.rejected.iter().any(|(r, _)| r == &run));
                        assert!(!g.pending.keys().any(|(r, _)| r == &run));
                        cancelled_or_closed.insert(run);
                    }
                    _ => {

                    }
                }
            }
        }
    }

    #[test]
    fn wal_replay_reconstructs_close() {
        let events = vec![
            Event::Released { run_id: "r1".into(), effect_key: "pay".into() },
            Event::Closed { run_id: "r1".into() },
        ];
        let mut g = Gate::new();
        for e in &events {
            g.apply(e);
        }
        assert_eq!(g.state_len(), 0);
        assert!(g.is_closed("r1"));
        assert_eq!(g.submit(eff("r1", "pay", false)), Admission::RefusedCancelled);
        assert_eq!(g.submit(eff("r1", "new", false)), Admission::RefusedCancelled);
        assert_eq!(g.submit(eff("r2", "pay", false)), Admission::Release);
    }

    #[test]
    fn replay_skips_release_logged_after_close() {
        // The handler appends to the WAL after it drops the gate lock, so a
        // release decided before a close can land after the Closed record.
        let events = vec![
            Event::Closed { run_id: "r1".into() },
            Event::Released { run_id: "r1".into(), effect_key: "k".into() },
            Event::Rejected { run_id: "r1".into(), effect_key: "j".into() },
        ];
        let mut g = Gate::new();
        for e in &events {
            g.apply(e);
        }
        assert_eq!(g.state_len(), 0);
        assert_eq!(g.submit(eff("r1", "k", false)), Admission::RefusedCancelled);
        assert_eq!(g.decide("r1", "j", true), Admission::RefusedCancelled);
    }

    #[test]
    fn durable_events_replay_rebuilds_durable_state() {
        let mut seed: u64 = 0xD1B54A32D192ED03;
        let mut rng = || {
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            (seed >> 33) as u32
        };
        for _ in 0..2000 {
            let mut g = Gate::new();
            let runs = ["a", "b", "c", "d"];
            let keys = ["x", "y", "z"];
            for _ in 0..60 {
                let run = runs[(rng() % 4) as usize];
                let key = keys[(rng() % 3) as usize];
                match rng() % 7 {
                    0 | 1 => {
                        g.submit(eff(run, key, rng() % 2 == 0));
                    }
                    2 | 3 => {
                        g.decide(run, key, rng() % 2 == 0);
                    }
                    4 => g.cancel(run),
                    5 => g.close_run(run),
                    _ => {}
                }
            }
            let mut r = Gate::new();
            for e in g.durable_events() {
                r.apply(&e);
            }
            assert_eq!(r.released, g.released);
            assert_eq!(r.rejected, g.rejected);
            assert_eq!(r.cancelled, g.cancelled);
            assert_eq!(r.closed, g.closed);
            assert_eq!(r.pending_count(), 0);
            // Replaying the snapshot twice is a no-op (idempotent records).
            for e in g.durable_events() {
                r.apply(&e);
            }
            assert_eq!(r.released, g.released);
            assert_eq!(r.closed, g.closed);
        }
    }

    #[test]
    fn wal_replay_is_idempotent() {
        let ev = Event::Released { run_id: "r1".into(), effect_key: "k".into() };
        let mut g = Gate::new();
        g.apply(&ev);
        g.apply(&ev); // duplicated tail line after a torn write
        assert_eq!(g.submit(eff("r1", "k", false)), Admission::RefusedDuplicate);
        assert_eq!(g.submit(eff("r1", "k2", false)), Admission::Release);
    }
}
