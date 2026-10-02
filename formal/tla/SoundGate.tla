-------------------------------- MODULE SoundGate --------------------------------
EXTENDS FiniteSets, TLC

CONSTANTS Runs,
          Keys

Ids == Runs \X Keys

VARIABLES released,
          rejected,
          pending,
          cancelled,
          closed

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

Submit(r, k, na) ==
    LET id == <<r, k>> IN
    \/ /\ Fenced(r)
       /\ UNCHANGED vars
    \/ /\ ~Fenced(r) /\ id \in released
       /\ UNCHANGED vars
    \/ /\ ~Fenced(r) /\ id \notin released /\ id \in rejected
       /\ UNCHANGED vars
    \/ /\ ~Fenced(r) /\ id \notin released /\ id \notin rejected /\ id \in pending
       /\ UNCHANGED vars
    \/ /\ ~Fenced(r) /\ id \notin released /\ id \notin rejected /\ id \notin pending /\ na
       /\ pending' = pending \cup {id}
       /\ UNCHANGED <<released, rejected, cancelled, closed>>
    \/ /\ ~Fenced(r) /\ id \notin released /\ id \notin rejected /\ id \notin pending /\ ~na
       /\ released' = released \cup {id}
       /\ UNCHANGED <<rejected, pending, cancelled, closed>>

Decide(r, k, ap) ==
    LET id == <<r, k>> IN
    \/ /\ id \in pending
       /\ \/ /\ Fenced(r)
             /\ pending' = pending \ {id}
             /\ UNCHANGED <<released, rejected, cancelled, closed>>
          \/ /\ ~Fenced(r) /\ ap
             /\ pending'  = pending \ {id}
             /\ released' = released \cup {id}
             /\ UNCHANGED <<rejected, cancelled, closed>>
          \/ /\ ~Fenced(r) /\ ~ap
             /\ pending'  = pending \ {id}
             /\ rejected' = rejected \cup {id}
             /\ UNCHANGED <<released, cancelled, closed>>
    \/ /\ id \notin pending
       /\ \/ /\ Fenced(r)
             /\ UNCHANGED vars
          \/ /\ ~Fenced(r) /\ id \in released
             /\ UNCHANGED vars


          \/ /\ ~Fenced(r) /\ id \notin released /\ ~ap
             /\ rejected' = rejected \cup {id}
             /\ UNCHANGED <<released, pending, cancelled, closed>>
          \/ /\ ~Fenced(r) /\ id \notin released /\ ap
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

Inv_Disjoint == released \cap rejected = {}

Inv_PendingUndecided ==
    \A id \in pending : id \notin released /\ id \notin rejected

Inv_ClosedCompacted ==
    \A id \in Ids :
        id[1] \in closed =>
            /\ id \notin released
            /\ id \notin rejected
            /\ id \notin pending

Safety ==
    /\ TypeOK
    /\ Inv_Disjoint
    /\ Inv_PendingUndecided
    /\ Inv_ClosedCompacted

=============================================================================
