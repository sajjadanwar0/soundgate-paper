use vstd::prelude::*;

verus! {

pub type Run = int;
pub type Key = int;
pub type Id = (Run, Key);

pub enum Verdict {
    Release,
    HeldForApproval,
    RefusedCancelled,
    RefusedDuplicate,
    RefusedRejected,
}

// The gate's abstract state.
pub struct Gate {
    pub released: Set<Id>,
    pub rejected: Set<Id>,
    pub pending: Set<Id>,
    pub cancelled: Set<Run>,
    pub closed: Set<Run>,
}

impl Gate {
    // A run is "fenced" iff cancelled or closed. Both fence late effects
    // (lib.rs submit: `cancelled.contains || closed.contains`).
    pub open spec fn fenced(self, r: Run) -> bool {
        self.cancelled.contains(r) || self.closed.contains(r)
    }

    // ---- THE STATE INVARIANT ----
    // Everything the safety proof needs, as one inductive invariant. Each
    // conjunct is justified against the code in comments.
    pub open spec fn inv(self) -> bool {
        // (I1) released and rejected are disjoint: an identity is never both
        //      released and rejected. submit/decide only ever add to one, and
        //      only when the other does not already contain the id.
        &&& (forall|id: Id| #![auto] !(self.released.contains(id) && self.rejected.contains(id)))
        // (I2) a pending identity is neither released nor rejected: it is held,
        //      undecided. (submit inserts into pending only past the released
        //      and rejected checks; decide removes from pending before adding
        //      to released/rejected.)
        &&& (forall|id: Id| #![auto] self.pending.contains(id)
                ==> !self.released.contains(id) && !self.rejected.contains(id))
        // (I3) FENCE COMPACTION INVARIANT (the reviewers' zombie-after-close
        //      race): a closed run retains NO per-identity state. This is what
        //      makes dropping a closed run's released-set sound -- a replayed
        //      effect from a closed run cannot be found in `released` (so it
        //      can't read as duplicate) nor slip through; it refuses via the
        //      fence, checked first. close_run establishes this; no later
        //      transition can add an id for a closed run (submit refuses
        //      fenced runs before touching any set; decide on a fenced run
        //      returns before adding).
        &&& (forall|id: Id| #![auto] self.closed.contains(id.0)
                ==> !self.released.contains(id) && !self.rejected.contains(id)
                    && !self.pending.contains(id))
    }


    // submit(e). Mirrors lib.rs::submit. Returns (new_state, verdict).
    pub open spec fn submit(self, r: Run, k: Key, needs_approval: bool) -> (Gate, Verdict) {
        let id = (r, k);
        if self.fenced(r) {
            // lib.rs:125 -- cancelled || closed  => RefusedCancelled
            (self, Verdict::RefusedCancelled)
        } else if self.released.contains(id) {
            // lib.rs:130 -- already released => RefusedDuplicate
            (self, Verdict::RefusedDuplicate)
        } else if self.rejected.contains(id) {
            // lib.rs:134 -- already rejected => RefusedRejected
            (self, Verdict::RefusedRejected)
        } else if self.pending.contains(id) {
            // lib.rs:145 -- idempotent hold (the double-release fix)
            (self, Verdict::HeldForApproval)
        } else if needs_approval {
            // lib.rs:150 -- hold
            (Gate { pending: self.pending.insert(id), ..self }, Verdict::HeldForApproval)
        } else {
            // lib.rs:153 -- release
            (Gate { released: self.released.insert(id), ..self }, Verdict::Release)
        }
    }

    // decide(r,k,approved). Mirrors lib.rs::decide.
    pub open spec fn decide(self, r: Run, k: Key, approved: bool) -> (Gate, Verdict) {
        let id = (r, k);
        if self.pending.contains(id) {
            // pending.remove(id) happened; now branch (lib.rs:185+)
            let s1 = Gate { pending: self.pending.remove(id), ..self };
            if s1.fenced(r) {
                // lib.rs:186 -- fence dominates a held effect
                (s1, Verdict::RefusedCancelled)
            } else if approved {
                // lib.rs:190 -- release
                (Gate { released: s1.released.insert(id), ..s1 }, Verdict::Release)
            } else {
                // lib.rs:193 -- reject
                (Gate { rejected: s1.rejected.insert(id), ..s1 }, Verdict::RefusedRejected)
            }
        } else {
            // nothing pending (lib.rs None branch)
            if self.fenced(r) {
                (self, Verdict::RefusedCancelled)
            } else if self.released.contains(id) {
                // late decision on a released identity: too late either way;
                // do NOT record a contradictory rejection. This branch is the
                // fix for the I1 violation TLC found (release; late reject).
                (self, Verdict::RefusedDuplicate)
            } else if !approved {
                (Gate { rejected: self.rejected.insert(id), ..self }, Verdict::RefusedRejected)
            } else {
                (self, Verdict::RefusedDuplicate)
            }
        }
    }


    pub open spec fn cancel(self, r: Run) -> Gate {
        Gate {
            cancelled: self.cancelled.insert(r),
            pending: self.pending.filter(|id: Id| id.0 != r),
            ..self
        }
    }


    pub open spec fn close_run(self, r: Run) -> Gate {
        Gate {
            closed: self.closed.insert(r),
            released: self.released.filter(|id: Id| id.0 != r),
            rejected: self.rejected.filter(|id: Id| id.0 != r),
            pending: self.pending.filter(|id: Id| id.0 != r),
            ..self
        }
    }
}

pub open spec fn init() -> Gate {
    Gate {
        released: Set::empty(),
        rejected: Set::empty(),
        pending: Set::empty(),
        cancelled: Set::empty(),
        closed: Set::empty(),
    }
}

proof fn init_inv()
    ensures init().inv()
{
    // empty sets: all three conjuncts hold vacuously.
}


proof fn submit_preserves(g: Gate, r: Run, k: Key, na: bool)
    requires g.inv()
    ensures (#[trigger] g.submit(r, k, na)).0.inv()
{
    let (g2, _v) = g.submit(r, k, na);

    assert(g2.inv()) by {
        reveal(Gate::inv);
    }
}

proof fn decide_preserves(g: Gate, r: Run, k: Key, ap: bool)
    requires g.inv()
    ensures (#[trigger] g.decide(r, k, ap)).0.inv()
{
    let (g2, _v) = g.decide(r, k, ap);
    assert(g2.inv()) by {
        reveal(Gate::inv);
    }
}

proof fn cancel_preserves(g: Gate, r: Run)
    requires g.inv()
    ensures (#[trigger] g.cancel(r)).inv()
{
    assert(g.cancel(r).inv()) by {
        reveal(Gate::inv);
    }
}

proof fn close_preserves(g: Gate, r: Run)
    requires g.inv()
    ensures (#[trigger] g.close_run(r)).inv()
{

    assert(g.close_run(r).inv()) by {
        reveal(Gate::inv);
    }
}


proof fn p4_fence_blocks_release(g: Gate, r: Run, k: Key, na: bool)
    requires g.inv(), g.fenced(r)
    ensures (g.submit(r, k, na)).1 is RefusedCancelled
{
    // submit's first branch fires because fenced(r).
}

// P4 also over decide: deciding a fenced run's effect never releases.
proof fn p4_fence_blocks_decide_release(g: Gate, r: Run, k: Key, ap: bool)
    requires g.inv(), g.fenced(r)
    ensures !((g.decide(r, k, ap)).1 is Release)
{
    // If pending: the inner fenced(r) branch returns RefusedCancelled before
    // the approved branch. If not pending: the None-branch fenced check
    // returns RefusedCancelled. Either way, not Release.
}

// P3 / DEDUP-ON-REPLAY: once an identity is released, resubmitting it never
// releases again (it refuses as duplicate, OR as cancelled if the run has
// since been fenced -- but never Release).
proof fn p3_no_double_release(g: Gate, r: Run, k: Key, na: bool)
    requires g.inv(), g.released.contains((r, k))
    ensures !((g.submit(r, k, na)).1 is Release)
{
    // Either fenced (branch 1, RefusedCancelled) or released.contains is true
    // (branch 2, RefusedDuplicate). The release branch is unreachable because
    // it requires !released.contains(id).
}

// P2 / REJECT-CANCELS: a rejected identity never releases on resubmission.
proof fn p2_rejected_stays(g: Gate, r: Run, k: Key, na: bool)
    requires g.inv(), g.rejected.contains((r, k))
    ensures !((g.submit(r, k, na)).1 is Release)
{
    // By I1, rejected implies !released, so branch 2 is skipped; branch 3
    // (rejected) fires -> RefusedRejected. (Or branch 1 if fenced.)
}

proof fn p1_gated_holds(g: Gate, r: Run, k: Key)
    requires
        g.inv(),
        !g.fenced(r),
        !g.released.contains((r, k)),
        !g.rejected.contains((r, k)),
    ensures (g.submit(r, k, true)).1 is HeldForApproval
{
    // With needs_approval=true and all prior checks false, submit either takes
    // the pending-idempotent branch (HeldForApproval) or the needs_approval
    // branch (HeldForApproval). Never Release.
}

fn main() {}

} // verus!