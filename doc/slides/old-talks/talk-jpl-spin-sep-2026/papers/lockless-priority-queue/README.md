# Case study: Lockless Priority Queue (nasa/fprime PR #5076)

A correctness review of a proposed **lock-free, ISR-safe priority queue** for the F′
framework, contributed as [nasa/fprime#5076](https://github.com/nasa/fprime/pull/5076).

This is **not** an F′ application (no components/topology), nor is it part of the
`fprime-verification-kit` (which holds instructions for standing up the F^ checking
infrastructure). It is a review of a piece of the F′ *framework* (`Os/Generic/`), so it
lives in the repo-level `case-studies/` collection.

## Why we looked at it

A colleague asked whether the algorithm is correct. Traditional F′ priority queues use
a mutex, which can deadlock if taken from an interrupt service routine (ISR); this PR
replaces the lock with compare-and-swap (CAS) and atomics so a producer/consumer can run
inside an ISR. The question was simply: **is it correct?**

## What's here

| Path | Contents |
|---|---|
| `report.md` | **Start here.** Full findings: the algorithm, the bug, the fix, and a formal-methods recommendation. |
| `pr5076.diff` | The complete PR diff (13 files, 2354 lines), saved verbatim. |
| `src/` | The reviewed source, extracted verbatim from the diff (see below). |
| `formal/` | Runnable **TLA+** *and* **Spin** models that both **reproduce** the underflow on the current code and **certify** the one-line fix. See `formal/README.md` for commands and results. |
| `route-b/` | A standalone C++ **harness that executes the algorithm** and provokes the underflow in real running code (telemetry reads `4294967295`), shows the fix delivers exactly-once with `available <= depth`, and shows ThreadSanitizer can't see the bug. See `route-b/README.md`. |
| `route-a/` | Checklist for the real validation inside a full fprime checkout — **partly executed on this host**: the PR builds in F′ and the author's tests pass (functional 29/29, TSan 15/15, no races), which does *not* clear the bug. We then **provoked the underflow in the real PR code** (a new test reads `getMessagesAvailable() == 4294967295` with a seam) and **verified the one-line fix in-tree** (max reading drops to `8 == depth`; author's 29 tests still pass). The on-target checks (lock-free on the flight CPU; weakly-ordered + real ISR) remain out of scope. See `route-a/README.md`. |
| `route-a/repro/` | Three small **applicable patches** (against PR HEAD `3216b31`) that reproduce the above from a clean `gh pr checkout`: `fix.patch` (the proposed one-line change), `bug-repro.patch` (→ test fails, `4294967295`), `fixed-with-harness.patch` (→ passes). We store the patches, not the full clone. See `route-a/repro/README.md`. |

## `src/` inventory (extracted from `pr5076.diff`)

| File | Lines | Role |
|---|---|---|
| `LocklessPriorityQueue.cpp` | 369 | **The core algorithm** — `send`/`receive`, the slot state machine, the counters. The bug is here. |
| `LocklessPriorityQueue.hpp` | 311 | Slot struct, handle, class declaration. |
| `sdd-lockless-queue.md` | 511 | The author's software design document (ABA, memory ordering, counter claims). |
| `LocklessPriorityQueueTests.cpp` | 292 | Unit tests. |
| `LocklessPriorityQueueTsanTests.cpp` | 613 | ThreadSanitizer stress tests. |
| `LocklessQueueCfg.hpp` | 46 | Configuration constants. |
| `DefaultLocklessPriorityQueue.cpp` | 14 | Default wiring. |

## Bottom line

Core algorithm is sound (ABA defense, memory ordering, exactly-once delivery all correct).
One real bug: the public `getMessagesAvailable()` counter (`m_available`) can transiently
**underflow to ~4.29 billion** under ≥2 concurrent consumers, and the same root cause lets
a non-blocking `receive` spuriously return `EMPTY`. **One-line fix.**

Notably, this counter and its bug are a **regression from an earlier review round**: `m_available`
was *added* (commit `3216b31`) to fix a reviewer's finding that the old counter reported occupancy
instead of receivable count — and the recommended "increment after publish" ordering is exactly
what introduces the underflow. The fix for the first problem created this one.

`report.md` opens with a one-paragraph verdict (§0), then works through the algorithm, the bug and
its concrete interleaving, the one-line fix, and the model-checking results.
