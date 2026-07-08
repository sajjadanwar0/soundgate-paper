----------------------------- MODULE SoundGate_Proofs -----------------------------
(***************************************************************************)
(* TLAPS inductive proof that SoundGate!Safety is an invariant of the      *)
(* protocol -- for UNBOUNDED Runs and Keys, which TLC (finite) cannot do.  *)
(*                                                                         *)
(* Structure: the standard inductive-invariant argument.                   *)
(*   1. Init => Safety                                                      *)
(*   2. Safety /\ [Next]_vars => Safety'                                    *)
(*   => Spec => []Safety      (by the TLA+ invariance rule, INV)            *)
(*                                                                         *)
(* Safety is already inductive on its own (it needs no auxiliary strength- *)
(* ening) because I1--I3 were designed as an inductive set. Each transition *)
(* lemma is proved by case split; SMT (the default TLAPS backend) closes    *)
(* each case.                                                              *)
(*                                                                         *)
(* Run:  tlapm SoundGate_Proofs.tla     (or via the Toolbox)               *)
(***************************************************************************)
EXTENDS SoundGate, TLAPS, FiniteSetTheorems

(* Init establishes Safety. *)
THEOREM InitSafety == Init => Safety
BY DEF Init, Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
       Inv_ClosedCompacted

(* Each action preserves Safety. We prove one lemma per action, then combine.
   In every case, the key facts are: (a) TypeOK is preserved because each
   assignment stays within Ids / Runs; (b) the three invariants are preserved
   because inserts happen only under guards that make them safe, and the
   filters in Cancel/Close remove exactly the ids that could violate I3. *)

(* Submit has six disjuncts; four leave the state unchanged. We case-split so
   each SMT obligation is small. The two state-changing cases insert
   id == <<r,k>> which is in Ids (r \in Runs, k \in Keys), is not fenced
   (so r \notin closed, preserving I3), and was checked absent from the other
   sets (preserving I1, I2). *)
LEMMA SubmitPreserves ==
    ASSUME Safety, NEW r \in Runs, NEW k \in Keys, NEW na \in BOOLEAN,
           Submit(r, k, na)
    PROVE  Safety'
PROOF
  <1> DEFINE id == <<r, k>>
  <1>a. id \in Ids
    BY DEF Ids
  <1>b. id[1] = r
    OBVIOUS
  <1>1. CASE UNCHANGED vars
    BY <1>1 DEF Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
                Inv_ClosedCompacted, vars
  <1>2. CASE /\ ~Fenced(r) /\ id \notin released /\ id \notin rejected
             /\ id \notin pending /\ na
             /\ pending' = pending \cup {id}
             /\ UNCHANGED <<released, rejected, cancelled, closed>>
    BY <1>2, <1>a, <1>b
    DEF Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
        Inv_ClosedCompacted, Fenced, Ids
  <1>3. CASE /\ ~Fenced(r) /\ id \notin released /\ id \notin rejected
             /\ id \notin pending /\ ~na
             /\ released' = released \cup {id}
             /\ UNCHANGED <<rejected, pending, cancelled, closed>>
    BY <1>3, <1>a, <1>b
    DEF Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
        Inv_ClosedCompacted, Fenced, Ids
  <1>4. QED
    BY <1>1, <1>2, <1>3 DEF Submit, vars

(* Decide: seven disjuncts after the I1 fix; three change state. The
   pending-branch cases use I2 (a pending id is neither released nor
   rejected) to preserve I1; the not-pending reject case is guarded by
   id \notin released (the TLC-found fix), which preserves I1 directly. *)
LEMMA DecidePreserves ==
    ASSUME Safety, NEW r \in Runs, NEW k \in Keys, NEW ap \in BOOLEAN,
           Decide(r, k, ap)
    PROVE  Safety'
PROOF
  <1> DEFINE id == <<r, k>>
  <1>a. id \in Ids
    BY DEF Ids
  <1>b. id[1] = r
    OBVIOUS
  <1>1. CASE /\ id \in pending /\ Fenced(r)
             /\ pending' = pending \ {id}
             /\ UNCHANGED <<released, rejected, cancelled, closed>>
    BY <1>1 DEF Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
                Inv_ClosedCompacted, Fenced, Ids
  <1>2. CASE /\ id \in pending /\ ~Fenced(r) /\ ap
             /\ pending'  = pending \ {id}
             /\ released' = released \cup {id}
             /\ UNCHANGED <<rejected, cancelled, closed>>
    BY <1>2, <1>a, <1>b
    DEF Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
        Inv_ClosedCompacted, Fenced, Ids
  <1>3. CASE /\ id \in pending /\ ~Fenced(r) /\ ~ap
             /\ pending'  = pending \ {id}
             /\ rejected' = rejected \cup {id}
             /\ UNCHANGED <<released, cancelled, closed>>
    BY <1>3, <1>a, <1>b
    DEF Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
        Inv_ClosedCompacted, Fenced, Ids
  <1>4. CASE /\ id \notin pending /\ Fenced(r) /\ UNCHANGED vars
    BY <1>4 DEF Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
                Inv_ClosedCompacted, vars
  <1>5. CASE /\ id \notin pending /\ ~Fenced(r) /\ id \in released
             /\ UNCHANGED vars
    BY <1>5 DEF Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
                Inv_ClosedCompacted, vars
  <1>6. CASE /\ id \notin pending /\ ~Fenced(r) /\ id \notin released /\ ~ap
             /\ rejected' = rejected \cup {id}
             /\ UNCHANGED <<released, pending, cancelled, closed>>
    BY <1>6, <1>a, <1>b
    DEF Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
        Inv_ClosedCompacted, Fenced, Ids
  <1>7. CASE /\ id \notin pending /\ ~Fenced(r) /\ id \notin released /\ ap
             /\ UNCHANGED vars
    BY <1>7 DEF Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
                Inv_ClosedCompacted, vars
  <1>8. QED
    BY <1>1, <1>2, <1>3, <1>4, <1>5, <1>6, <1>7 DEF Decide, vars

LEMMA CancelPreserves ==
    ASSUME Safety, NEW r \in Runs, Cancel(r)
    PROVE  Safety'
BY DEF Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
       Inv_ClosedCompacted, Cancel, Fenced, Ids

(* Close is the interesting case: it must re-establish I3 for the newly
   closed run while preserving it for others, and it filters released/rejected/
   pending so I1,I2 are preserved (removing elements cannot create overlap). *)
LEMMA ClosePreserves ==
    ASSUME Safety, NEW r \in Runs, Close(r)
    PROVE  Safety'
BY DEF Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
       Inv_ClosedCompacted, Close, Fenced, Ids

(* Combine: Safety is preserved by Next. *)
LEMMA NextPreserves ==
    ASSUME Safety, [Next]_vars
    PROVE  Safety'
PROOF
  <1>1. CASE Next
    BY <1>1, SubmitPreserves, DecidePreserves, CancelPreserves, ClosePreserves
       DEF Next
  <1>2. CASE UNCHANGED vars
    BY <1>2 DEF Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
                Inv_ClosedCompacted, vars
  <1>3. QED BY <1>1, <1>2 DEF Next

(* The invariance theorem. *)
THEOREM SafetyInvariant == Spec => []Safety
PROOF
  <1>1. Init => Safety        BY InitSafety
  <1>2. Safety /\ [Next]_vars => Safety'  BY NextPreserves
  <1>3. QED
    BY <1>1, <1>2, PTL DEF Spec

=============================================================================
