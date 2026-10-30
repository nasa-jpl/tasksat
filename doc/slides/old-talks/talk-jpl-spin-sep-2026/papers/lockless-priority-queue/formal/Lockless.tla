-------------------------------- MODULE Lockless --------------------------------
(***************************************************************************)
(* An abstract TLA+ model of Os::Generic::LocklessPriorityQueue           *)
(* (nasa/fprime PR #5076), focused on the `m_available` counter bug.      *)
(*                                                                         *)
(* WHAT THIS MODELS (and what it deliberately abstracts away)              *)
(*                                                                         *)
(*   * Slots carry only their state: FREE / WRITING / READY / READING.    *)
(*     The 62-bit ABA tag is OMITTED on purpose -- the counter bug is      *)
(*     independent of ABA, and the tag was verified correct separately.    *)
(*     Dropping it keeps the state space finite and tiny.                  *)
(*                                                                         *)
(*   * `avail` is the model of m_available (getMessagesAvailable()),       *)
(*     modeled as an unbounded INTEGER so that "going below zero" is       *)
(*     directly observable as avail < 0.  In the real code the field is    *)
(*     unsigned, so avail < 0 corresponds to the wrap to 0xFFFFFFFF        *)
(*     (~4.29 billion) reported in report.md section 5.                    *)
(*                                                                         *)
(* THE ONE KNOB: FIX                                                       *)
(*                                                                         *)
(*   FIX = FALSE  -> producer publishes READY, THEN increments avail.      *)
(*                   (the PR as written)                                   *)
(*   FIX = TRUE   -> producer increments avail, THEN publishes READY.      *)
(*                   (the one-line fix in report.md section 6)             *)
(*                                                                         *)
(* THE MODELING POINT THAT MATTERS (report.md section 9):                  *)
(*   "publish READY" and "increment avail" are SEPARATE atomic steps.      *)
(*   If you collapse them into one action the bug disappears -- which is   *)
(*   precisely why the prose argument missed it.                           *)
(***************************************************************************)
EXTENDS Integers, FiniteSets

CONSTANTS Producers,   \* set of producer process ids
          Consumers,   \* set of consumer process ids
          Slots,       \* set of slot ids, e.g. 1..Depth
          FIX          \* BOOLEAN: TRUE = fixed ordering, FALSE = PR as written

VARIABLES
    state,   \* state[s] in {"FREE","WRITING","READY","READING"}
    avail,   \* INTEGER model of m_available
    pstate,  \* pstate[p] in {"idle","mid1","mid2"}  (producer program counter)
    pslot,   \* pslot[p]  : slot a producer currently owns (0 = none)
    cstate,  \* cstate[c] in {"idle","scan","read"}   (consumer program counter)
    cslot    \* cslot[c]  : slot a consumer currently owns (0 = none)

vars == <<state, avail, pstate, pslot, cstate, cslot>>

NoSlot == 0   \* sentinel: not a member of Slots (we use Slots = 1..Depth)

TypeOK ==
    /\ state  \in [Slots -> {"FREE","WRITING","READY","READING"}]
    /\ avail  \in Int
    /\ pstate \in [Producers -> {"idle","mid1","mid2"}]
    /\ pslot  \in [Producers -> Slots \cup {NoSlot}]
    /\ cstate \in [Consumers -> {"idle","scan","read"}]
    /\ cslot  \in [Consumers -> Slots \cup {NoSlot}]

Init ==
    /\ state  = [s \in Slots     |-> "FREE"]
    /\ avail  = 0
    /\ pstate = [p \in Producers |-> "idle"]
    /\ pslot  = [p \in Producers |-> NoSlot]
    /\ cstate = [c \in Consumers |-> "idle"]
    /\ cslot  = [c \in Consumers |-> NoSlot]

------------------------------------------------------------------------------
(* -------- Producer -------- *)

\* Claim a FREE slot: FREE -> WRITING.  Atomic, so it models the real CAS:
\* only one producer can win a given slot (TLC fires one action at a time).
PClaim(p) ==
    /\ pstate[p] = "idle"
    /\ \E s \in Slots :
         /\ state[s] = "FREE"
         /\ state'  = [state  EXCEPT ![s] = "WRITING"]
         /\ pslot'  = [pslot  EXCEPT ![p] = s]
    /\ pstate' = [pstate EXCEPT ![p] = "mid1"]
    /\ UNCHANGED <<avail, cstate, cslot>>

\* Middle step A.  FIX=FALSE: publish READY.  FIX=TRUE: increment avail.
PStepA(p) ==
    /\ pstate[p] = "mid1"
    /\ IF FIX
         THEN /\ avail' = avail + 1
              /\ UNCHANGED state
         ELSE /\ state' = [state EXCEPT ![pslot[p]] = "READY"]
              /\ UNCHANGED avail
    /\ pstate' = [pstate EXCEPT ![p] = "mid2"]
    /\ UNCHANGED <<pslot, cstate, cslot>>

\* Middle step B.  FIX=FALSE: increment avail.  FIX=TRUE: publish READY.
PStepB(p) ==
    /\ pstate[p] = "mid2"
    /\ IF FIX
         THEN /\ state' = [state EXCEPT ![pslot[p]] = "READY"]
              /\ UNCHANGED avail
         ELSE /\ avail' = avail + 1
              /\ UNCHANGED state
    /\ pstate' = [pstate EXCEPT ![p] = "idle"]
    /\ pslot'  = [pslot  EXCEPT ![p] = NoSlot]
    /\ UNCHANGED <<cstate, cslot>>

------------------------------------------------------------------------------
(* -------- Consumer -------- *)

\* Fast-path gate: a PEEK at avail, not a reservation.  This is the crux:
\* two consumers can both pass this gate on the same single credit.
CGate(c) ==
    /\ cstate[c] = "idle"
    /\ avail > 0
    /\ cstate' = [cstate EXCEPT ![c] = "scan"]
    /\ UNCHANGED <<state, avail, pstate, pslot, cslot>>

\* Claim a READY slot: READY -> READING, and decrement avail.
CClaim(c) ==
    /\ cstate[c] = "scan"
    /\ \E s \in Slots :
         /\ state[s] = "READY"
         /\ state'  = [state  EXCEPT ![s] = "READING"]
         /\ cslot'  = [cslot  EXCEPT ![c] = s]
    /\ avail'  = avail - 1
    /\ cstate' = [cstate EXCEPT ![c] = "read"]
    /\ UNCHANGED <<pstate, pslot>>

\* Passed the gate but found no READY slot (someone else took it): give up.
\* Models the retry-then-EMPTY path; does not touch avail.
CAbort(c) ==
    /\ cstate[c] = "scan"
    /\ \A s \in Slots : state[s] # "READY"
    /\ cstate' = [cstate EXCEPT ![c] = "idle"]
    /\ UNCHANGED <<state, avail, pstate, pslot, cslot>>

\* Finish reading: READING -> FREE, release the slot.
CFinish(c) ==
    /\ cstate[c] = "read"
    /\ state'  = [state  EXCEPT ![cslot[c]] = "FREE"]
    /\ cslot'  = [cslot  EXCEPT ![c] = NoSlot]
    /\ cstate' = [cstate EXCEPT ![c] = "idle"]
    /\ UNCHANGED <<avail, pstate, pslot>>

------------------------------------------------------------------------------
Next ==
    \/ \E p \in Producers : PClaim(p) \/ PStepA(p) \/ PStepB(p)
    \/ \E c \in Consumers : CGate(c) \/ CClaim(c) \/ CAbort(c) \/ CFinish(c)

Spec == Init /\ [][Next]_vars

------------------------------------------------------------------------------
(* -------- Properties -------- *)

\* THE bug.  Fails on FIX=FALSE (TLC prints the underflow trace);
\* holds on FIX=TRUE.  avail < 0 == the real unsigned wrap to ~4.29e9.
NoUnderflow == avail >= 0

\* The fixed counter is a benign upper bound: never more than one credit
\* per slot outstanding.  Holds on FIX=TRUE.
UpperBound == avail =< Cardinality(Slots)

===============================================================================
