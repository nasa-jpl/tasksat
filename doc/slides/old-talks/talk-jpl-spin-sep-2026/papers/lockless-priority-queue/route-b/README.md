# Route B — standalone executable harness

A self-contained C++14 program that **executes** the queue algorithm (not a model) and
**provokes the `m_available` underflow in real running code** by inserting one honest piece of
instrumentation. This complements the model checkers in [`../formal/`](../formal/): the models
*prove* the bug over all interleavings; this shows it *happening* in compiled C++.

> This is Route B from [`../report.md`](../report.md) §1 / the review discussion. It is a
> **quick experiment, not a substitute for Route A** (building inside a full fprime checkout,
> ideally cross-compiled to the flight target). See "What this does NOT tell you" below.

## Files

| File | What it is |
|---|---|
| `harness.cpp` | `send()`/`receive()` transcribed faithfully from `../src/LocklessPriorityQueue.cpp` (lines ~197–354), with F' types stubbed (`FW_ASSERT`→`assert`, allocator→`new[]`, priority→`int32_t`, state-tag→`uint64_t`). Threads + exactly-once tracking + a telemetry-style monitor. |
| `run.sh` | Builds and runs the three scenarios below, then removes the binaries. |

## The instrumentation (and why it's honest)

The **only** added instrumentation is `hookAfterPublish()` — a `sleep_for` inserted at the exact
seam between the `READY` store and the `m_available.fetch_add` (src lines 240→244):

```cpp
slot.m_stateTag.store(packStateTag(READY, ...), std::memory_order_release); // publish
hookAfterPublish();                    // <-- a producer preempted HERE is normal
m_available.fetch_add(1, std::memory_order_acq_rel);                        // then count
```

A producer being descheduled between those two instructions — by an interrupt, the RTOS
scheduler, or simply losing its time slice — is an ordinary event. The delay does **not** create
an impossible ordering; it widens a window that already exists so the natural race between two
consumers reliably lands in it. Remove the delay and the same bug still exists, it just takes far
longer to hit by chance. Nothing else about the algorithm is altered, and the fixed ordering
(`--fixed`) reorders exactly the one line the report recommends.

## How to run

```bash
./run.sh
# or by hand:
clang++ -std=c++14 -O2 -pthread -o harness harness.cpp
./harness --delay-us 50          # PR as written  -> underflow
./harness --fixed --total 300000 # the fix         -> exactly-once, available <= depth
```

Flags: `--fixed`, `--delay-us N`, `--total N`, `--depth N`.

## Results obtained (2026-08-27, clang, Apple Silicon / arm64)

1. **PR as written** → underflow within a handful of messages; the telemetry monitor observes
   `getMessagesAvailable() == 4294967295 (0xFFFFFFFF)` — the same value the model checkers
   predicted. Delivery stays correct up to the stop point (no duplicate tripped the exactly-once
   assert).
2. **`--fixed`** → 300 000 messages delivered **exactly once** (missing=0, dup=0) and the max
   `available` ever observed was **16 == depth**: the fixed counter is a benign upper bound,
   empirically matching report §6 and the TLA+ `UpperBound` invariant.
3. **ThreadSanitizer build** (`-fsanitize=thread`) → underflow still reproduced, and TSan emits
   **no data-race warning**. This is the point of report §8: the bug is a race-free logic error
   on a correctly-synchronized atomic, so a race detector cannot see it.

## What this does NOT tell you (why Route A still matters)

- **Lock-freedom on the real target.** This ran on a 64-bit host where the atomics are lock-free.
  Whether `std::atomic<U64>` is lock-free on the actual flight MCU — the entire ISR-safety
  premise — can only be answered by building for that target (Route A, cross-compiled). If it
  isn't lock-free, the premise collapses regardless of algorithm correctness.
- **The real memory model.** Release/acquire reasoning only bites on weakly-ordered CPUs; a
  host run is not the target CPU.
- **Integration.** This tests the class in isolation, not the `Os::QueueInterface`/`Os::Delegate`
  wiring, `MemAllocatorRegistry` path, placement new/destruct, or teardown.
- **The real types/config and `FW_ASSERT` behavior**, which affect e.g. the secondary
  `FW_ASSERT(storedSize <= capacity)` finding.
- **It tests this transcription, not the author's exact file.** Route A runs the real code under
  the author's own `Tests`/`TsanTests`.

Bottom line: Route B is a fast, convincing demonstration that the underflow is real and that the
one-line fix removes it. Route A on the flight target is what actually de-risks the deliverable.
