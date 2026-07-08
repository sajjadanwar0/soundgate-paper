//! soundgate: a language-external effect gate for agent frameworks.
//!
//! The measured problem (see the Python probes): a framework's own control
//! flow cannot be trusted to enforce its stop primitives. Under parallelism an
//! approval gate does not cover sibling effects; on resume an effect replays;
//! on cancel/timeout an effect orphans. soundgate moves the enforcement point
//! OUT of the framework: every side effect must be admitted here first.
//!
//! Four properties, each targeting one measured violation axis:
//!   1. HOLD-UNTIL-DECIDED  an approval-gated effect is not released until a
//!      decision arrives -> kills the parallel-approval leak.
//!   2. REJECT-CANCELS      a rejected effect is never released -> kills
//!      reject-after-effect.
//!   3. DEDUP-ON-REPLAY     an effect identity admitted once is refused on
//!      replay -> kills resume/timeout double-execution.
//!   4. FENCE-ON-CANCEL     once a run is cancelled/timed-out, later effects
//!      from it are refused even if a zombie thread submits them -> kills the
//!      orphaned/zombie effect.
//!
//! EFFECT IDENTITY (Definition 1): an effect is identified by the pair
//! (run_id, effect_key). All dedup, rejection, and pending state is scoped by
//! that pair. Scoping by effect_key alone -- the pre-fix behavior -- makes
//! rejections and dedup bleed across unrelated runs (run_B's "charge_card"
//! falsely refused after run_A released it) and lets a second run's held
//! effect clobber the first's in the pending map. The G1 regression tests
//! below encode those counterexamples.
//!
//! This module is pure and deterministic so it can be unit-tested with no I/O.
//! The binary (main.rs) wraps it in a line-delimited JSON TCP protocol that
//! any language can call.
#[cfg(feature = "python")]
mod python;

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

/// Effect identity: (run_id, effect_key). Owned strings for map keys; the
/// per-admission allocation is irrelevant next to the socket round-trip the
/// reference server pays anyway (see e2e/bench_socket.py for the measurement).
type EffectId = (String, String);

/// A submitted side effect awaiting an admission decision.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Effect {
    /// Run this effect belongs to (the unit that can be cancelled).
    pub run_id: String,
    /// Idempotency key: stable across replays of the same logical effect
    /// WITHIN its run. Distinct runs may reuse keys freely.
    pub effect_key: String,
    /// Whether this effect requires human approval before release.
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

/// The gate's verdict for a submitted effect.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case", tag = "verdict")]
pub enum Admission {
    /// Safe to perform now.
    Release,
    /// Held pending an approval decision (property 1).
    HeldForApproval,
    /// Refused: run was cancelled/timed-out (property 4).
    RefusedCancelled,
    /// Refused: this (run_id, effect_key) already released (property 3), or
    /// a decision arrived for an identity the gate has no record of (treated
    /// as a late/unknown decision; conservative refuse -- never a release).
    RefusedDuplicate,
    /// Refused: a decision rejected this effect (property 2).
    RefusedRejected,
}

/// Durable state-change events for write-ahead logging. Only three kinds of
/// state must survive a crash: released identities (the replay fence),
/// rejected identities (reject stickiness), and cancelled runs (the zombie
/// fence). Held-but-undecided effects are deliberately NOT durable: losing a
/// hold means the effect was never released, and the framework's re-submit
/// after restart simply re-holds it -- the conservative (fail-closed) outcome.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "ev", rename_all = "snake_case")]
pub enum Event {
    Released { run_id: String, effect_key: String },
    Rejected { run_id: String, effect_key: String },
    Cancelled { run_id: String },
}

#[derive(Debug, Default)]
pub struct Gate {
    /// (run_id, effect_key) -> already released (dedup set), property 3.
    released: HashSet<EffectId>,
    /// run_id -> cancelled, property 4.
    cancelled: HashSet<String>,
    /// (run_id, effect_key) -> pending effect awaiting approval, property 1.
    pending: HashMap<EffectId, Effect>,
    /// (run_id, effect_key) -> explicit reject decision recorded, property 2.
    rejected: HashSet<EffectId>,
    /// Runs that have terminated. Like `cancelled` this fences late effects,
    /// but it additionally licenses compaction: once a run is closed, its
    /// per-identity released/rejected/pending entries can be dropped because
    /// the run-level fence subsumes them (any late submission refuses via the
    /// fence, not via a per-identity lookup). This bounds memory by the number
    /// of ACTIVE runs rather than by total historical effects.
    closed: HashSet<String>,
}

impl Gate {
    pub fn new() -> Self {
        Gate::default()
    }

    /// Submit an effect for admission. The ordering of checks encodes the
    /// safety priority: cancellation and duplication dominate approval.
    pub fn submit(&mut self, e: Effect) -> Admission {
        // Property 4: a cancelled OR closed run's effects never release, even
        // late. Both are run-level fences; closed additionally means the run
        // terminated normally and its per-identity state may have been
        // compacted away (see close_run).
        if self.cancelled.contains(&e.run_id) || self.closed.contains(&e.run_id) {
            return Admission::RefusedCancelled;
        }
        let id = e.id();
        // Property 3: never release the same logical effect twice.
        if self.released.contains(&id) {
            return Admission::RefusedDuplicate;
        }
        // Property 2: an effect that was already rejected stays rejected.
        if self.rejected.contains(&id) {
            return Admission::RefusedRejected;
        }
        // Idempotent hold: an identity already awaiting a decision stays held,
        // regardless of this submission's needs_approval flag. Without this,
        // re-submitting a held identity with needs_approval=false would
        // release it while leaving the stale pending entry in place, which a
        // later decide() would then honor as a SECOND release. (Found by the
        // randomized invariant harness; see randomized_invariants_hold.) The
        // first submission's disposition wins; a resubmission is never a fresh
        // release of an identity whose fate is not yet decided.
        if self.pending.contains_key(&id) {
            return Admission::HeldForApproval;
        }
        if e.needs_approval {
            // Property 1: hold; do not release until decide() says so.
            self.pending.insert(id, e);
            Admission::HeldForApproval
        } else {
            self.released.insert(id);
            Admission::Release
        }
    }

    /// Record a human decision for a held effect of a specific run. Returns
    /// the resulting admission: Release if approved (and still valid), or a
    /// Refused reason. The run_id is REQUIRED: decisions are scoped to the
    /// effect identity (run_id, effect_key); a key alone is ambiguous when
    /// concurrent runs reuse keys.
    pub fn decide(&mut self, run_id: &str, effect_key: &str, approved: bool) -> Admission {
        let id = id_of(run_id, effect_key);
        let effect = match self.pending.remove(&id) {
            Some(e) => e,
            None => {
                // Nothing pending under this identity. Name the reason:
                // a cancelled/closed run's fence dominates (this is the
                // approve-after-cancel path -- CANCELLED, not "duplicate").
                if self.cancelled.contains(run_id) || self.closed.contains(run_id) {
                    return Admission::RefusedCancelled;
                }
                // If the identity ALREADY RELEASED, a late decision of either
                // polarity is too late: the effect happened. Report duplicate
                // and -- critically -- do NOT record a contradictory rejection.
                // (Found by TLC model checking the concurrent protocol: a late
                // reject of a released identity put the id in both `released`
                // and `rejected`, violating the disjointness invariant I1. See
                // formal/tla/SoundGate.tla and the i1_* regression test.)
                if self.released.contains(&id) {
                    return Admission::RefusedDuplicate;
                }
                // A reject with no pending effect is recorded so a later
                // replayed submit of the same identity stays rejected.
                if !approved {
                    self.rejected.insert(id);
                    return Admission::RefusedRejected;
                }
                // An approve with no pending effect: late (already released)
                // or unknown identity. Either way, conservative refuse.
                return Admission::RefusedDuplicate;
            }
        };
        // Cancellation/closure may have arrived while the effect was held.
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

    /// Cancel a run. All future and currently-held effects from it are refused.
    pub fn cancel(&mut self, run_id: &str) {
        self.cancelled.insert(run_id.to_string());
        // Drop any held effects belonging to this run.
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

    /// Mark a run terminal and compact its per-identity state. After this,
    /// the run is fenced (late effects refuse via RefusedCancelled) and its
    /// released/rejected/pending entries are dropped, so steady-state memory
    /// is bounded by active runs, not by total effects ever admitted.
    ///
    /// Safety of compaction: dropping a closed run's `released` identities is
    /// sound precisely because the run-level fence now refuses ANY of its
    /// submissions -- a replayed effect from a closed run cannot slip through
    /// as a fresh release, it refuses via the fence. Dropping `pending` is the
    /// same conservative choice as cancel: an undecided effect is never
    /// released. This is why close_run must NOT be called on a run that may
    /// still legitimately emit new, releasable effects.
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
    /// Total per-identity entries retained (released + rejected + pending).
    /// Used by tests to show compaction bounds memory.
    pub fn state_len(&self) -> usize {
        self.released.len() + self.rejected.len() + self.pending.len()
    }
    /// Per-identity entries retained for a single run (0 after close_run).
    pub fn state_len_for(&self, run_id: &str) -> usize {
        self.released.iter().filter(|(r, _)| r == run_id).count()
            + self.rejected.iter().filter(|(r, _)| r == run_id).count()
            + self.pending.keys().filter(|(r, _)| r == run_id).count()
    }
    pub fn pending_count(&self) -> usize {
        self.pending.len()
    }

    /// Apply a durable event during recovery. Idempotent: replaying a log
    /// twice yields the same state, so torn/duplicated tail lines are safe.
    pub fn apply(&mut self, ev: &Event) {
        match ev {
            Event::Released { run_id, effect_key } => {
                self.released.insert((run_id.clone(), effect_key.clone()));
            }
            Event::Rejected { run_id, effect_key } => {
                self.rejected.insert((run_id.clone(), effect_key.clone()));
            }
            Event::Cancelled { run_id } => self.cancel(run_id),
        }
    }
}

// ------------------------------- unit tests -------------------------------
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
        assert_eq!(g.pending_count(), 1); // not released while awaiting approval
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
        // replay of the same logical effect (node re-run on resume)
        assert_eq!(g.submit(eff("r1", "charge_card", false)), Admission::RefusedDuplicate);
    }

    #[test]
    fn property3_dedup_after_approval() {
        let mut g = Gate::new();
        g.submit(eff("r1", "deploy", true));
        assert_eq!(g.decide("r1", "deploy", true), Admission::Release);
        // a replayed submit after approval must not release again
        assert_eq!(g.submit(eff("r1", "deploy", true)), Admission::RefusedDuplicate);
    }

    #[test]
    fn property4_fence_on_cancel_blocks_zombie() {
        let mut g = Gate::new();
        g.cancel("r1");
        // a zombie thread from the cancelled run submits its effect late
        assert_eq!(g.submit(eff("r1", "post_webhook", false)), Admission::RefusedCancelled);
    }

    #[test]
    fn property4_cancel_drops_held_effect() {
        let mut g = Gate::new();
        g.submit(eff("r1", "send_email", true)); // held
        g.cancel("r1");
        assert_eq!(g.pending_count(), 0); // held effect dropped
        // approving it now must not release it -- and the verdict names the
        // real reason: the run's cancellation fence.
        assert_eq!(g.decide("r1", "send_email", true), Admission::RefusedCancelled);
    }

    #[test]
    fn unrelated_runs_unaffected_by_cancel() {
        let mut g = Gate::new();
        g.cancel("r1");
        assert_eq!(g.submit(eff("r2", "ok_effect", false)), Admission::Release);
    }

    // ---- G1 regression tests: effect identity is (run_id, effect_key) ----

    #[test]
    fn g1_cross_run_key_reuse_allowed() {
        // Definition 1 scopes effect identity per run. run_B's "charge_card"
        // is a different logical effect from run_A's and must release.
        let mut g = Gate::new();
        assert_eq!(g.submit(eff("run_A", "charge_card", false)), Admission::Release);
        assert_eq!(g.submit(eff("run_B", "charge_card", false)), Admission::Release);
        // while replay WITHIN a run still dedups:
        assert_eq!(g.submit(eff("run_A", "charge_card", false)), Admission::RefusedDuplicate);
    }

    #[test]
    fn g1_cross_run_rejection_does_not_bleed() {
        let mut g = Gate::new();
        g.submit(eff("run_A", "send_email", true));
        assert_eq!(g.decide("run_A", "send_email", false), Admission::RefusedRejected);
        // run_B's identically-keyed effect is unaffected by run_A's rejection.
        assert_eq!(g.submit(eff("run_B", "send_email", false)), Admission::Release);
    }

    #[test]
    fn g1_approve_after_cancel_reports_cancelled() {
        // The verdict for deciding a cancelled run's effect is CANCELLED,
        // not "duplicate" -- the run's fence is the reason, name it.
        let mut g = Gate::new();
        g.submit(eff("r1", "send_email", true));
        g.cancel("r1");
        assert_eq!(g.decide("r1", "send_email", true), Admission::RefusedCancelled);
    }

    #[test]
    fn g1_cross_run_pending_no_clobber() {
        // Two runs hold the same key concurrently; each decision resolves
        // its OWN effect. Pre-fix, run_B's insert clobbered run_A's held
        // effect and a key-only decide() could not say whose it decided.
        let mut g = Gate::new();
        assert_eq!(g.submit(eff("run_A", "deploy", true)), Admission::HeldForApproval);
        assert_eq!(g.submit(eff("run_B", "deploy", true)), Admission::HeldForApproval);
        assert_eq!(g.pending_count(), 2); // pre-fix: 1 (clobbered)
        assert_eq!(g.decide("run_B", "deploy", true), Admission::Release);
        assert_eq!(g.decide("run_A", "deploy", false), Admission::RefusedRejected);
        // run_A's reject did not affect run_B's released effect; a replay of
        // run_B's effect dedups as released, not rejected.
        assert_eq!(g.submit(eff("run_B", "deploy", true)), Admission::RefusedDuplicate);
    }

    // ---- WAL recovery: state reconstructed from events is enforced ----

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
        // dedup fence survived
        assert_eq!(g.submit(eff("r1", "pay", false)), Admission::RefusedDuplicate);
        // reject stickiness survived
        assert_eq!(g.submit(eff("r1", "mail", true)), Admission::RefusedRejected);
        // cancellation fence survived
        assert_eq!(g.submit(eff("r2", "late", false)), Admission::RefusedCancelled);
        // unrelated runs unaffected
        assert_eq!(g.submit(eff("r3", "pay", false)), Admission::Release);
    }

    #[test]
    fn close_run_fences_and_compacts() {
        let mut g = Gate::new();
        g.submit(eff("r1", "a", false));           // released  (entry 1)
        g.submit(eff("r1", "b", true));            // held      (entry 2)
        g.submit(eff("r1", "c", true));            // held
        g.decide("r1", "c", false);                // rejected  (entry 3)
        assert_eq!(g.state_len(), 3);              // 1 released + 1 pending + 1 rejected
        g.close_run("r1");
        assert_eq!(g.state_len(), 0);              // compacted
        // fenced: any late submission from the closed run refuses
        assert_eq!(g.submit(eff("r1", "a", false)), Admission::RefusedCancelled);
        assert_eq!(g.submit(eff("r1", "c", false)), Admission::RefusedCancelled);
        // deciding a closed run's (gone) held effect reports the fence reason
        assert_eq!(g.decide("r1", "b", true), Admission::RefusedCancelled);
        // other runs entirely unaffected
        assert_eq!(g.submit(eff("r2", "a", false)), Admission::Release);
    }

    #[test]
    fn close_run_does_not_leak_release_after_compaction() {
        // The soundness crux: a replayed effect from a CLOSED run must not
        // slip through as a fresh release just because its released-entry was
        // compacted away.
        let mut g = Gate::new();
        assert_eq!(g.submit(eff("r1", "charge", false)), Admission::Release);
        g.close_run("r1");
        assert_eq!(g.state_len(), 0);
        assert_eq!(g.submit(eff("r1", "charge", false)), Admission::RefusedCancelled);
    }

    #[test]
    fn i1_late_reject_of_released_is_duplicate() {
        // TLC counterexample, as a permanent regression test: release, then a
        // late reject must NOT record a contradictory rejection.
        let mut g = Gate::new();
        assert_eq!(g.submit(eff("r1", "k1", false)), Admission::Release);
        assert_eq!(g.decide("r1", "k1", false), Admission::RefusedDuplicate);
        // the identity stays released-only: a resubmit still dedups (not
        // "rejected"), and a fresh identity is unaffected.
        assert_eq!(g.submit(eff("r1", "k1", true)), Admission::RefusedDuplicate);
        assert_eq!(g.submit(eff("r1", "k2", false)), Admission::Release);
    }

    // Stdlib randomized invariant harness (a scaled proptest that runs with no
    // extra dependencies). The full proptest version lives in
    // tests/proptest_invariants.rs behind the `proptest-tests` feature.
    #[test]
    fn randomized_invariants_hold() {
        // Deterministic LCG so failures are reproducible without a dep.
        let mut seed: u64 = 0x9E3779B97F4A7C15;
        let mut rng = || {
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            (seed >> 33) as u32
        };
        for _ in 0..2000 {
            let mut g = Gate::new();
            // Shadow model of what MUST be true.
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
                        // INVARIANT 1: a fenced run never releases.
                        if cancelled_or_closed.contains(&run) {
                            assert_ne!(v, Admission::Release,
                                       "released from fenced run {run}/{key}");
                        }
                        // INVARIANT 2: never release the same identity twice.
                        if v == Admission::Release {
                            assert!(!ever_released.contains(&id),
                                    "double release of {run}/{key}");
                            ever_released.insert(id);
                        }
                    }
                    2 => {
                        let approve = rng() % 2 == 0;
                        let v = g.decide(&run, &key, approve);
                        // INVARIANT 4 (from the TLC finding): a decision on an
                        // already-released identity never records a rejection.
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
                        // INVARIANT 3: closed runs retain no per-identity state.
                        assert!(!g.released.iter().any(|(r, _)| r == &run));
                        assert!(!g.rejected.iter().any(|(r, _)| r == &run));
                        assert!(!g.pending.keys().any(|(r, _)| r == &run));
                        cancelled_or_closed.insert(run);
                    }
                    _ => {
                        // no-op tick: exercise interleavings
                    }
                }
            }
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