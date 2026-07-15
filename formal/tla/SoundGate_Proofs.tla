----------------------------- MODULE SoundGate_Proofs -----------------------------

EXTENDS SoundGate, TLAPS, FiniteSetTheorems

(* Init establishes Safety. *)
THEOREM InitSafety == Init => Safety
BY DEF Init, Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
       Inv_ClosedCompacted


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

LEMMA ClosePreserves ==
    ASSUME Safety, NEW r \in Runs, Close(r)
    PROVE  Safety'
BY DEF Safety, TypeOK, Inv_Disjoint, Inv_PendingUndecided,
       Inv_ClosedCompacted, Close, Fenced, Ids

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

THEOREM SafetyInvariant == Spec => []Safety
PROOF
  <1>1. Init => Safety        BY InitSafety
  <1>2. Safety /\ [Next]_vars => Safety'  BY NextPreserves
  <1>3. QED
    BY <1>1, <1>2, PTL DEF Spec

=============================================================================
