/*
 * Spin/Promela model of the Os::Generic::LocklessPriorityQueue `m_available`
 * bug (nasa/fprime PR #5076). This is the cross-check of formal/Lockless.tla
 * requested in report.md section 9 — same abstraction, different tool.
 *
 * Run (from this folder):
 *   spin       -run lockless.pml     # PR as written -> ASSERTION VIOLATED (underflow)
 *   spin -DFIX -run lockless.pml     # the one-line fix -> no errors
 *
 * NOTE the flag order: `spin -run -DFIX` SILENTLY IGNORES -DFIX (Spin 6.5.2),
 * and appears to show the bug surviving the fix. The macro must precede -run.
 *
 * For a short counterexample (depth 11 instead of 236), use breadth-first:
 *   spin -a lockless.pml && gcc -DSAFETY -DBFS -o pan pan.c && ./pan
 *   spin -t -p -g lockless.pml
 *
 * WHAT'S MODELED (matches the TLA+ model):
 *   - a slot carries only its state FREE/WRITING/READY/READING. The message,
 *     its size, priority and sequence number are abstracted away, as is the
 *     ABA tag: the counter does not depend on any of them. So `slot[i]` IS
 *     slot i, as far as this model is concerned.
 *   - `avail` models m_available as a SIGNED int, so going below 0 is observable
 *     as avail < 0 -- in the real (unsigned) field that is the wrap to
 *     0xFFFFFFFF (~4.29 billion).
 *   - CAS transitions are atomic{} (one winner per slot, like the real CAS).
 *   - THE CRUX: in the producer, "publish READY" and "avail++" are SEPARATE
 *     statements (NOT inside one atomic{}). If you wrap them together the bug
 *     vanishes -- which is exactly why the prose argument missed it. Likewise
 *     the consumer's gate (avail>0) is a separate step from the claim.
 */

#define NPROD  2
#define NCONS  2
#define NSLOTS 2

#define FREE    0
#define WRITING 1
#define READY   2
#define READING 3

byte slot[NSLOTS] = FREE;  /* each slot's state -- all we model of a slot */
int  avail = 0;            /* model of m_available; signed so underflow shows as <0 */

active [NPROD] proctype Producer() {
    int myslot;                 /* the slot this producer claimed */
    do
    ::  /* claim a FREE slot: CAS FREE -> WRITING (atomic; blocks until one is free) */
        atomic {
            if
            :: (slot[0] == FREE) -> slot[0] = WRITING; myslot = 0
            :: (slot[1] == FREE) -> slot[1] = WRITING; myslot = 1
            fi
        }
#ifdef FIX
        /* FIX: increment BEFORE publishing READY -- two separate steps */
        avail++;
        assert(avail <= NSLOTS);          /* benign upper bound holds */
        if
        :: (myslot == 0) -> slot[0] = READY
        :: (myslot == 1) -> slot[1] = READY
        fi
#else
        /* PR as written: publish READY, THEN increment -- two separate steps */
        if
        :: (myslot == 0) -> slot[0] = READY
        :: (myslot == 1) -> slot[1] = READY
        fi;
        avail++
#endif
    od
}

active [NCONS] proctype Consumer() {
    int myslot;                 /* the slot this consumer claimed, -1 if none */
    do
    ::  avail > 0 ->                       /* fast-path gate: a PEEK, its own step */
        atomic {                           /* claim a READY slot: CAS + fetch_sub */
            if
            :: (slot[0] == READY) -> slot[0] = READING; myslot = 0; avail--
            :: (slot[1] == READY) -> slot[1] = READING; myslot = 1; avail--
            :: else               -> myslot = -1 /* passed gate but nothing READY: abort */
            fi
        }
        assert(avail >= 0);                /* THE bug: fails on the unfixed model */
        if
        :: (myslot == 0) -> slot[0] = FREE      /* finish: READING -> FREE */
        :: (myslot == 1) -> slot[1] = FREE
        :: (myslot == -1) -> skip
        fi
    od
}
