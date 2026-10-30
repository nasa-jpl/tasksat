# Correctness Review — `Os::Generic::LocklessPriorityQueue` (nasa/fprime PR #5076)

**Reviewer:** Klaus Havelund's verification group
**Date:** 2026-08-27
**Subject:** [nasa/fprime#5076](https://github.com/nasa/fprime/pull/5076) — a lock-free, ISR-safe priority queue for F′
**Source under review:** `src/` in this folder (extracted verbatim from the PR diff, also kept as `pr5076.diff`)

---

## 0. Verdict

The core algorithm is **sound**: no message is lost, duplicated, or corrupted; there is no data race; the ABA defense and the release/acquire pairings are correct. We found **one bug**, confined to an auxiliary counter. `m_available` — the value returned by the public `getMessagesAvailable()` — can transiently **underflow to 4 294 967 295** (`0xFFFFFFFF`) under two or more concurrent consumers, because it is incremented *after* the `READY` publish while `m_count` is incremented *before*. The same asymmetry lets a non-blocking `receive` return `EMPTY` while a fully-published message is queued — a linearizability violation. Both symptoms are transient and self-healing; delivery is unaffected. The fix is a one-line reorder.

This is a **race-free logic error on a correctly-synchronized atomic** — the exact class of defect the PR's ThreadSanitizer suite cannot detect. We reached it by static reading, then confirmed it with two model checkers (TLA+/TLC and Spin/Promela, `formal/`), reproduced it in executed C++ (`route-b/`), and finally reproduced it in the real PR code inside a `nasa/fprime` checkout, where a new test reads `getMessagesAvailable() == 4294967295` on the shipped code and passes (max `== depth`) once the fix is applied (`route-a/`).

---

## 1. Context: what it is and why it exists

F′ components communicate over message queues. The stock queue, `Os::Generic::PriorityQueue`, guards its state with a mutex. That is unusable from an interrupt service routine (ISR): if a thread holds the mutex and an ISR fires on the same core and tries to take it, the ISR spins waiting for a thread that cannot run until the ISR returns — deadlock. This PR replaces the lock with atomics and compare-and-swap (CAS), so a producer or consumer can run inside an ISR.

To avoid the difficulty of a lock-free *sorted* structure, the queue is a flat array of `depth` slots (tens, in practice), scanned linearly to find the highest-priority message. Bounded, predictable scan time is exactly what flight software wants.

---

## 2. How the algorithm works

The queue is an array of `depth` **slots**, each holding one message and a packed atomic word `m_stateTag = (tag << 2) | state`. The **state** (2 bits) cycles `FREE → WRITING → READY → READING → FREE`; the **tag** (remaining bits) increments on *every* transition (the ABA defense: a stale view of the word can never compare-equal at a claim CAS).

- **FREE** — empty; any producer may claim it.
- **WRITING** — a producer owns it and is copying its message in.
- **READY** — published; a consumer may claim it.
- **READING** — a consumer owns it and is copying the message out.

**`send`** scans for a `FREE` slot, CASes it `FREE → WRITING`, writes the payload/size/priority/sequence, then CASes `WRITING → READY` (the publish — the linearization point). **`receive`** scans `READY` slots for the best (highest priority, then lowest sequence = FIFO), CASes that slot `READY → READING`, copies the message out, then CASes `READING → FREE`. The claiming CAS is what confers ownership: two consumers can eye the same `READY` slot, but only one's CAS succeeds, so no message is delivered twice.

### The two counters

Alongside the slots the queue keeps two atomic tallies:

| Counter | Purpose | Incremented | Decremented |
|---|---|---|---|
| `m_count` | occupancy → high-water mark | **before** publish | before freeing the slot |
| `m_available` | receivable count returned by `getMessagesAvailable()` | **after** publish | at the claiming CAS (`READY → READING`) |

The asymmetry in the "incremented" column is the entire bug (§3). `m_count` increments *before* publish, so a decrement can never outrun it and it never underflows. `m_available` increments *after* publish, deliberately — the author wanted `getMessagesAvailable() > 0` to imply a message is truly `READY`. That is the choice that breaks.

`m_available` exists purely for O(1) performance, not correctness: `getMessagesAvailable()` is called every dispatch cycle, and the `receive` fast-path (line 283) skips the whole scan when it reads 0. It is an O(1) cache of a property — "is any slot `READY`?" — that is otherwise smeared across all slots (this queue has no head/tail pointer to consult, by design, since a shared head/tail would be the contention and ABA hotspot a lock-free queue is trying to avoid). The bug is a cache-coherence defect between that counter and the authoritative slot array.

### Pseudocode

Stripped of the retry loops, with helpers hiding the slot machine:

```
send(m):
    slot = claimFreeSlot()      # scan FREE, CAS FREE→WRITING
    write(slot, m)
    publish(slot)               # CAS WRITING→READY   ← message now visible
    available += 1              # ⚠️ AFTER publish — the bug (§3)

receive():
    if available == 0:          # (a) fast-path PEEK — a hint, NOT a reservation
        return EMPTY
    slot = claimBestReady()     # (b) the REAL gate: whoever wins this CAS owns the message
    if slot == null:
        return EMPTY
    m = read(slot); free(slot)  # CAS READING→FREE
    available -= 1              # (c) decrement, authorized by (b) — not by the peek (a)
    return m
```

Both `+=`/`-=` are single atomic read-modify-writes, so no increment is lost and no torn value is read — this is *not* a lost-update data race. The defect is the ordering *across* the two functions: `publish` makes the slot claimable before its `+1` lands, and the decrement at `(c)` is gated by the claim `(b)`, not by the peek `(a)`. So a consumer can claim a just-published slot and run `-1` before the producer's matching `+1` has landed — a decrement executing before its own increment, dipping the count below zero.

---

## 3. The bug: `m_available` underflows to ~4.29 billion

Because of the §2 asymmetry, a decrement can precede its matching increment. Two consumers can both pass the `!= 0` peek at `m_available == 1`, both win the claim CAS on two *different* real `READY` slots, and both decrement — while only one producer's `+1` has landed: `1 → 0 → 0xFFFFFFFF`. It is *unsigned*, so "below zero" wraps to `2³² − 1 = 4 294 967 295`.

The defect is **transient and self-healing**: arithmetic is modulo 2³², so the lagging producer's `fetch_add` (`0xFFFFFFFF + 1 ≡ 0`) restores the correct value. The bogus reading lasts only from the second consumer's decrement to that increment. (A *signed* counter would show `−1` instead — the same "decrement outran its increment" defect and the same contract violation, just less alarming than a 4.29-billion telemetry spike.)

### Concrete interleaving

Setup: `depth ≥ 2`, producers P1/P2, consumers C1/C2. Time flows down.

| Step | Actor | Action | `m_available` | Slot states |
|---|---|---|---|---|
| 1 | P1 | send M1 → slot 0, publish READY, **increment** | **1** | s0=READY |
| 2 | P2 | send M2 → slot 1, publish READY … | 1 | s0=READY, s1=READY |
| 3 | P2 | *…preempted right before its increment* | 1 | s0=READY, s1=READY |
| 4 | C1 | peek: sees 1 → proceed | 1 | — |
| 5 | C2 | peek: also sees 1 → proceed | 1 | — |
| 6 | C1 | claims a READY slot, **decrement** | **0** | one READING |
| 7 | C2 | claims the *other* READY slot, **decrement** | **0 − 1 → 0xFFFFFFFF** ⚠️ | both READING |
| 8 | P2 | resumes, finally **increments** | back to 0 | — |

Between steps 7 and 8, `getMessagesAvailable()` returns 4 294 967 295. Both consumers received genuine, distinct messages — delivery is correct; only the counter lies. The interleaving needs only one producer preempted between publish and increment, plus two consumers — entirely reachable on any preemptive scheduler, and multi-consumer queues are a supported, tested configuration.

### The dual symptom: spurious `EMPTY`

The same asymmetry has a mirror effect. If the queue is otherwise empty and a producer has published (`READY`) but not yet incremented, a non-blocking consumer peeks the gate, sees `m_available == 0`, skips the scan, and after `MAX_RETRY_PASSES` returns `EMPTY` — even though a fully-published message was in the queue the whole time. There is no instant during the call at which the queue was truly empty, so this is a **linearizability violation**, not merely "spurious under contention."

### Why it matters

`getMessagesAvailable()` should sit in `0..depth`. The wrap breaks even that sanity bound. In F′ the value feeds queue-health monitoring and can be downlinked as telemetry, where a 4.29-billion sample reads as corrupt or trips a false overflow alarm. We checked the two internal callers, and both degrade gracefully: `ActiveComponentBase::dispatch()` only tests `== 0` (a wrapped value is `!= 0`, so it dispatches once); `QueuedComponentBase::dispatchAvailableMessages()` uses it as a loop bound but `break`s the moment the queue drains, so the huge bound is self-limiting. The real exposure is therefore the **direct read / downlinked telemetry**, not a hang or data loss.

### Where the bug came from: a regression from an earlier fix

This is the part worth pausing on. **`m_available` did not exist in the original PR**, and neither did this bug. Both were introduced by a fix to an earlier review comment:

1. Originally `getMessagesAvailable()` returned `m_count`. A reviewer, assisted by Claude Fable, correctly noted that `m_count` is occupancy ("claimed-or-queued"), not a receivable count.
2. The recommended fix, verbatim: *"Increment a separate `m_available` **on the READY release** and decrement it on the successful READING CAS"* — i.e. increment *after* publish.
3. The author implemented exactly that in commit `3216b31` (*"Address review: receivable-count getMessagesAvailable, empty-receive fast path"*), documenting an "under-report only, never over-report" property in SDD §8. **`3216b31` is the revision this report reviews.**

So the increment-after-publish our bug depends on is the fix that was requested, faithfully implemented — and the underflow to 4.29 billion is the most dramatic *over*-report imaginable, falsifying the very property the fix set out to establish. The companion "empty-receive fast path" is the `m_available == 0` gate behind the second symptom.

---

## 4. The fix (one line)

Move the `m_available` increment to **before** the publish, matching what `m_count` already does:

```cpp
// in send(), after filling the slot:
this->m_handle.m_available.fetch_add(1, std::memory_order_acq_rel);   // ← moved UP
slot.m_stateTag.store(packStateTag(LOCKLESS_SLOT_READY, tagOf(desired) + 1),
                      std::memory_order_release);                     // publish
```

Now every decrement is strictly preceded by its matching increment (the same argument that protects `m_count`), so **underflow is unreachable**. It also fixes the spurious `EMPTY`: once the increment precedes the publish, `m_available == 0` soundly implies "no `READY` slot exists," so skipping the scan is safe.

**The trade-off is deliberate and worth stating.** With two separate atomics and a decrement that can race a lagging increment, you cannot have both "never over-report" *and* "never underflow" — one must give:

- Increment *after* publish (the author's choice) → never over-reports, but **underflows** to 4.29 billion.
- Increment *before* publish (our fix) → never underflows, but **over-reports by ≤ depth** while a producer has incremented but not yet published.

The fix's over-report is benign because the gate is only a hint: a consumer that passes it still runs the real scan, finds nothing, and returns `EMPTY` — which is linearizable, since at that instant no message was receivable. The cost is at most a wasted scan. This consciously gives back the "never over-report" property the earlier review round asked for; we judge that correct because the framework's actual uses (an `== 0` test, and a loop bound that breaks on drain) tolerate a small over-count but are badly misled by a full 32-bit wrap. If "never over-report" is truly required, a single racing counter cannot deliver it safely — the count should be *derived* by scanning instead.

---

## 5. Why the existing tests don't catch it

The PR ships a strong ThreadSanitizer suite, but TSan finds **data races** — two threads touching the same *non-atomic* memory without synchronization. This is a logic error on a properly-synchronized atomic: every access to `m_available` is a correct atomic op, so TSan sees nothing. The stress tests also assert exactly-once delivery, which genuinely holds, so they pass while the counter misbehaves. Nothing asserts `getMessagesAvailable() <= depth`.

We confirmed this on this host. Built inside a fresh `nasa/fprime` checkout at PR HEAD `3216b31`, the author's suites pass green: **`LocklessPriorityQueueTest` 29/29**, **`LocklessPriorityQueueTsanTest` 15/15 with zero race reports** — fully consistent with the bug being present.

A catching test must (a) stall a producer between publish and increment, (b) have two consumers claim concurrently, and (c) assert `getMessagesAvailable() <= depth` throughout — a window narrow enough to need a test seam, not luck under load. We demonstrated it two ways:

- **`route-b/`** transcribes `send`/`receive` faithfully with one instrumentation point (a delay at the publish→increment seam — an ordinary scheduling event). Built with TSan, it **reproduces the underflow** (`4294967295`) with **no race reported**; in `--fixed` mode it delivers 300 000 messages exactly-once with `available` never exceeding `depth`.
- **`route-a/`** provokes the same bug in the **real PR code**: with the identical env-gated seam (marked "not for merge") and a new test sampling `getMessagesAvailable()` under 2 producers × 4 consumers, the shipped code reads **`4294967295` and fails** while delivery stays exactly-once. The one-line fix drops the max reading to **`8 == depth`** and the test passes; the author's 29 functional tests still pass. See `route-a/README.md`.

---

## 6. Secondary observations

1. **`FW_ASSERT(storedSize <= capacity)` in `receive`** aborts on a condition other `Os::Queue` backends report as the `SIZE_MISMATCH` status — and it sits on the ISR-safe path, where an abort is especially undesirable. Consider returning a status instead.
2. **Doc/impl mismatch on sequence numbers.** The SDD and header say sequence numbers are assigned "at publication time"; the code assigns them during `WRITING`. Harmless for a single producer (still monotonic), but it slightly weakens the FIFO argument for concurrent producers.
3. **`teardown()` thread-safety** is documented in the header (caller must ensure no concurrent `send`/`receive`/`teardown`) — noted here because it's easy to miss when integrating.

---

## 7. How this was verified

- Source extracted verbatim from `pr5076.diff` into `src/` (line counts match the PR).
- Reviewed by static reasoning over the C++11 memory model and the slot state machine, then confirmed mechanically by two independent model checkers (TLA+/TLC and Spin/Promela, `formal/`), reproduced in executed C++ (`route-b/`, incl. under TSan), and reproduced in the real PR code inside a `nasa/fprime` checkout (`route-a/`): a new test reads `getMessagesAvailable() == 4294967295` and fails on the shipped code; the one-line fix drops it to `8 == depth` and the author's 29 functional tests still pass. The author's suites also pass green as shipped (29/29 functional, 15/15 TSan, no races), which does not clear the bug since none assert `available <= depth`.
- The same `m_available` finding was reached independently by a separate Claude-based review on another platform, which agrees on the counter, the interleaving, and the fix. **No claim here rests on an agent's unverified assertion**; every executed result above is actual command output. The instrumentation added to the real code is a temporary, clearly-marked review seam, *not* part of the proposed fix. What remains untested is the on-target lock-freedom/memory-model question (§1); full flight assurance rests on that.

---

## 8. Appendix: the annotated source (`send` and `receive`)

The authoritative source (`src/LocklessPriorityQueue.cpp`), with comments only on the parts that are
not self-evident — the atomics, the memory orderings, the ABA tagging, and the one bug. Cosmetic
abbreviations only, meaning unchanged: `this->m_handle.X` → `X`; `std::memory_order_*` →
`acquire`/`release`/`acq_rel`/`relaxed`; loop-index declarations elided. Verbatim, unabridged
source: `send` = lines 197–265, `receive` = lines 267–354.

### `send` — publish a message

```cpp
Status LocklessPriorityQueue::send(const U8* buffer, FwSizeType size,
                                   FwQueuePriorityType priority,
                                   BlockingType blockType) {
    FW_ASSERT(m_slots != nullptr);   // programming-error checks, NOT input
    FW_ASSERT(m_data  != nullptr);   // validation: behavior on violation is
    FW_ASSERT(buffer  != nullptr);   // whatever the flight build's FW_ASSERT
                                     // is configured to do (§6.1)
    if (size > m_messageSize)
        return Status::SIZE_MISMATCH;      // only graceful early return

    const bool blocking = (blockType == BlockingType::BLOCKING);

    // Progress contract: non-blocking gives up after MAX_RETRY_PASSES
    // (returns FULL); a blocking caller loops forever, backing off.
    for (pass = 0; blocking || pass < MAX_RETRY_PASSES; pass++) {
        for (i = 0; i < depth; i++) {
            LocklessSlot& slot = m_slots[i];
            packed = slot.m_stateTag.load(acquire);
            if (stateOf(packed) != LOCKLESS_SLOT_FREE) continue;

            // Claim FREE->WRITING. The +1 on the tag is the ABA defense:
            // a stale view of this word can never compare-equal here
            // again. Losing the CAS => keep scanning (lock-free progress).
            desired = packStateTag(LOCKLESS_SLOT_WRITING, tagOf(packed) + 1);
            if (!slot.m_stateTag.compare_exchange_strong(
                    packed, desired, acq_rel, relaxed)) continue;

            // Slot is now privately owned. m_size is plain/non-atomic (safe:
            // only the owner touches it). priority/sequence use relaxed
            // because the release-store below orders them ahead of any
            // consumer's acquire. sequence comes from a global fetch_add,
            // a monotonic FIFO tiebreaker.
            if (size > 0) memcpy(m_data + i*m_messageSize, buffer, size);
            slot.m_size = size;
            slot.m_priority.store(priority, relaxed);
            slot.m_sequence.store(m_sequence.fetch_add(1, relaxed), relaxed);

            // Occupancy count BEFORE publish. Safe: a consumer's matching
            // m_count-- can only run after it observes READY (below), so it
            // can never overtake this ++  ->  m_count cannot underflow.
            const U32 nextCount = m_count.fetch_add(1, acq_rel) + 1;

            // PUBLISH -- the linearization point. WRITING->READY; this
            // release pairs with the consumer's acquire load of the same
            // word, so every write above is visible before the claim.
            slot.m_stateTag.store(
                packStateTag(LOCKLESS_SLOT_READY, tagOf(desired) + 1),
                release);

            // *** THE BUG (§3) *** receivable count incremented AFTER the
            // publish -- the mirror-opposite of m_count above. Between the
            // publish and this line the slot is claimable but uncredited, so
            // a consumer can claim AND decrement in the gap: two consumers,
            // two READY slots, only one +1 landed -> 1, 0, wrap to
            // 4,294,967,295 (heals when the +1 arrives). The same gap also
            // reads 0 past a real message -> spurious EMPTY. Fix (§4): move
            // this one line ABOVE the publish, exactly like m_count.
            m_available.fetch_add(1, acq_rel);

            // Raise the high-water mark. Bounded (ISR-safe, §7): each failed
            // CAS reloads a strictly larger prevMark, the mark only rises and
            // is capped at depth -> at most depth iterations.
            U32 prevMark = m_highMark.load(relaxed);
            for (markPass = 0;
                 markPass < depth && nextCount > prevMark; markPass++)
                if (m_highMark.compare_exchange_strong(
                        prevMark, nextCount, relaxed, relaxed)) break;
            return Status::OP_OK;
        }
        if (blocking) Task::delay(BACKOFF);   // no FREE slot this pass
    }
    return Status::FULL;
}
```

### `receive` — claim the best-priority message

Selection and claiming are **two separate steps**; only the second (a CAS) confers ownership.

```cpp
Status LocklessPriorityQueue::receive(U8* destination, FwSizeType capacity,
                                      BlockingType blockType,
                                      FwSizeType& actualSize,
                                      FwQueuePriorityType& priority) {
    FW_ASSERT(m_slots != nullptr);   // same programming-error checks as send
    FW_ASSERT(m_data  != nullptr);
    FW_ASSERT(destination != nullptr);

    const bool blocking = (blockType == BlockingType::BLOCKING);

    for (pass = 0; blocking || pass < MAX_RETRY_PASSES; pass++) {
        // Fast-path PEEK, not a reservation -- only decides "worth scanning."
        // Because send credits m_available AFTER publishing, this can read 0
        // while a published message waits, so a non-blocking caller can
        // wrongly return EMPTY right here (§3). A wrapped 4.29e9 just reads
        // as "very non-zero" and harmlessly forces the scan.
        if (m_available.load(acquire) == 0) {
            if (blocking) Task::delay(BACKOFF);
            continue;
        }

        // Selection pass: pick the best (highest priority, then smallest
        // sequence = FIFO). Mutates and claims nothing, so many consumers
        // can run it at once on the same slots.
        FwSizeType bestIndex = depth;   // + bestPriority/Sequence/Packed
        for (i = 0; i < depth; i++) {
            LocklessSlot& slot = m_slots[i];
            packed = slot.m_stateTag.load(acquire);
            if (stateOf(packed) != LOCKLESS_SLOT_READY) continue;
            candPriority = slot.m_priority.load(relaxed);
            candSequence = slot.m_sequence.load(relaxed);
            // Re-read the tag: priority/sequence were read relaxed, so if
            // the slot was recycled between the loads they may belong to a
            // different message -- discard if the tag moved.
            if (packed != slot.m_stateTag.load(acquire)) continue;
            if (bestIndex == depth ||
                isCandidatePreferred(candPriority, candSequence,
                                     bestPriority, bestSequence)) {
                bestIndex = i;               bestPacked   = packed;
                bestPriority = candPriority; bestSequence = candSequence;
            }
        }
        if (bestIndex == depth) {            // nothing READY found this pass
            if (blocking) Task::delay(BACKOFF);
            continue;
        }

        // Claim READY->READING demanding the EXACT (READY, tag) seen during
        // selection. THIS CAS is the real gate that confers ownership -- two
        // consumers eyeing one slot can't both win (no double-delivery); a
        // slot changed since selection fails here and we rescan.
        desired = packStateTag(LOCKLESS_SLOT_READING, tagOf(bestPacked) + 1);
        if (m_slots[bestIndex].m_stateTag.compare_exchange_strong(
                bestPacked, desired, acq_rel, relaxed)) {
            // Decrement gated by the winning claim above -- NOT by the peek.
            // So it always pairs with a real, exclusively-claimed message; it
            // only underflows because on the buggy ordering a claim can
            // happen before the +1 credit has landed.
            m_available.fetch_sub(1, acq_rel);

            LocklessSlot& slot = m_slots[bestIndex];
            const FwSizeType storedSize = slot.m_size;  // race-free: owned
            // (§6.1) hard abort on the ISR path; other Os::Queue backends
            // return SIZE_MISMATCH as a status instead.
            FW_ASSERT(storedSize <= capacity);
            if (storedSize > 0)
                memcpy(destination,
                       m_data + bestIndex*m_messageSize, storedSize);
            actualSize = storedSize;
            priority   = slot.m_priority.load(relaxed);

            // m_count-- BEFORE releasing to FREE (mirror of send's
            // before-publish ++).
            m_count.fetch_sub(1, acq_rel);
            slot.m_stateTag.store(
                packStateTag(LOCKLESS_SLOT_FREE, tagOf(desired) + 1),
                release);
            return Status::OP_OK;
        }
        if (blocking) Task::delay(0);   // lost the claim CAS -> yield, rescan
    }
    return Status::EMPTY;
}
```

**The one-line difference, seen whole.** The entire report reduces to one question: *which side of the
`release`-store publish does the `fetch_add` sit on?* `m_count` increments **before** publish (safe: a
decrement can never outrun it). `m_available` increments **after** publish (unsafe: a claim, and its
decrement, can slip into the gap). Move that one line up and both the underflow and the spurious
`EMPTY` disappear. Every other line above — the ABA tagging, the release/acquire pairing, the
exact-tag claim CAS, the bounded loops — is correct as written.
