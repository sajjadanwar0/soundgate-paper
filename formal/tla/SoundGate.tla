-------------------------------- MODULE SoundGate --------------------------------
(***************************************************************************)
(* SoundGate admission core -- concurrent protocol model (TLA+/TLC).       *)
(*                                                                         *)
(* WHERE THIS COMPLEMENTS VERUS. The Verus proof establishes the four      *)
(* safety properties for the SEQUENTIAL admission logic (one operation at  *)
(* a time -- correct, because the reference gate serializes decisions      *)
(* under a mutex). This TLA+ model checks the CONCURRENT setting the       *)
(* reviewers worried about: agents submitting effects while a run is being *)
(* cancelled/closed, in every interleaving. TLC exhaustively explores all  *)
(* orderings over a small finite domain and checks that no reachable state *)
(* violates the safety invariants -- in particular the zombie-after-close  *)
(* race (a late submission from a closed run must never release).          *)
(*                                                                         *)
(* Run:  tlc SoundGate.tla   (with SoundGate.cfg)                          *)
(***************************************************************************)
EXTENDS FiniteSets, TLC

CONSTANTS Runs,        \* finite set of run ids, e.g. {r1, r2}
          Keys        \* finite set of effect keys, e.g. {k1, k2}

Ids == Runs \X Keys

VARIABLES released,    \* set of (run,key) that have been released
          rejected,    \* set of (run,key) explicitly rejected
          pending,     \* set of (run,key) held awaiting a decision
          cancelled,   \* set of runs cancelled
          closed       \* set of runs closed (terminal, compacted)

vars == <<released, rejected, pending, cancelled, closed>>

Fenced(r) == r \in cancelled \/ r \in closed

TypeOK ==
    /\ released  \subseteq Ids
    /\ rejected  \subseteq Ids
    /\ pending   \subseteq Ids
    /\ cancelled \subseteq Runs
    /\ closed    \subseteq Runs

Init ==
    /\ released  = {}
    /\ rejected  = {}
    /\ pending   = {}
    /\ cancelled = {}
    /\ closed    = {}

(***************************************************************************)
(* Transitions. Each mirrors a lib.rs operation. `na` (needs_approval) and *)
(* `ap` (approved) are chosen nondeterministically to cover all inputs.    *)
(***************************************************************************)

Submit(r, k, na) ==
    LET id == <<r, k>> IN
    \/ /\ Fenced(r)                              \* -> RefusedCancelled
       /\ UNCHANGED vars
    \/ /\ ~Fenced(r) /\ id \in released          \* -> RefusedDuplicate
       /\ UNCHANGED vars
    \/ /\ ~Fenced(r) /\ id \notin released /\ id \in rejected  \* -> RefusedRejected
       /\ UNCHANGED vars
    \/ /\ ~Fenced(r) /\ id \notin released /\ id \notin rejected /\ id \in pending
       /\ UNCHANGED vars                          \* idempotent hold
    \/ /\ ~Fenced(r) /\ id \notin released /\ id \notin rejected /\ id \notin pending /\ na
       /\ pending' = pending \cup {id}            \* hold
       /\ UNCHANGED <<released, rejected, cancelled, closed>>
    \/ /\ ~Fenced(r) /\ id \notin released /\ id \notin rejected /\ id \notin pending /\ ~na
       /\ released' = released \cup {id}          \* release
       /\ UNCHANGED <<rejected, pending, cancelled, closed>>

Decide(r, k, ap) ==
    LET id == <<r, k>> IN
    \/ /\ id \in pending                          \* remove from pending, then:
       /\ \/ /\ Fenced(r)                          \* fence dominates
             /\ pending' = pending \ {id}
             /\ UNCHANGED <<released, rejected, cancelled, closed>>
          \/ /\ ~Fenced(r) /\ ap                   \* release
             /\ pending'  = pending \ {id}
             /\ released' = released \cup {id}
             /\ UNCHANGED <<rejected, cancelled, closed>>
          \/ /\ ~Fenced(r) /\ ~ap                  \* reject
             /\ pending'  = pending \ {id}
             /\ rejected' = rejected \cup {id}
             /\ UNCHANGED <<released, cancelled, closed>>
    \/ /\ id \notin pending                        \* nothing pending
       /\ \/ /\ Fenced(r)
             /\ UNCHANGED vars
          \/ /\ ~Fenced(r) /\ id \in released      \* late decide on a
             /\ UNCHANGED vars                      \* released id: refuse,
                                                    \* record nothing (I1 fix
                                                    \* found by TLC)
          \/ /\ ~Fenced(r) /\ id \notin released /\ ~ap   \* record reject
             /\ rejected' = rejected \cup {id}
             /\ UNCHANGED <<released, pending, cancelled, closed>>
          \/ /\ ~Fenced(r) /\ id \notin released /\ ap    \* stale approve
             /\ UNCHANGED vars

Cancel(r) ==
    /\ cancelled' = cancelled \cup {r}
    /\ pending'   = { id \in pending : id[1] # r }
    /\ UNCHANGED <<released, rejected, closed>>

Close(r) ==
    /\ closed'   = closed \cup {r}
    /\ released' = { id \in released : id[1] # r }
    /\ rejected' = { id \in rejected : id[1] # r }
    /\ pending'  = { id \in pending  : id[1] # r }
    /\ UNCHANGED cancelled

Next ==
    \/ \E r \in Runs, k \in Keys, na \in BOOLEAN : Submit(r, k, na)
    \/ \E r \in Runs, k \in Keys, ap \in BOOLEAN : Decide(r, k, ap)
    \/ \E r \in Runs : Cancel(r)
    \/ \E r \in Runs : Close(r)

Spec == Init /\ [][Next]_vars

(***************************************************************************)
(* SAFETY INVARIANTS (the same properties Verus proves, as state           *)
(* predicates TLC checks on every reachable state).                        *)
(***************************************************************************)

\* I1: released and rejected are disjoint.
Inv_Disjoint == released \cap rejected = {}

\* I2: a pending identity is neither released nor rejected.
Inv_PendingUndecided ==
    \A id \in pending : id \notin released /\ id \notin rejected

\* I3: FENCE COMPACTION -- a closed run retains no per-identity state. This is
\*     the invariant that makes the zombie-after-close race safe.
Inv_ClosedCompacted ==
    \A id \in Ids :
        id[1] \in closed =>
            /\ id \notin released
            /\ id \notin rejected
            /\ id \notin pending

\* The conjunction TLC checks as INVARIANT.
Safety ==
    /\ TypeOK
    /\ Inv_Disjoint
    /\ Inv_PendingUndecided
    /\ Inv_ClosedCompacted

=============================================================================
