# Experiment log — reproducing the `m_available` underflow (nasa/fprime#5076)

**Run date:** 2026-08-29
**Host:** macOS (Darwin 25.6.0), arm64; OpenJDK 11.0.29; Spin 6.5.2; Apple clang (`cc`/`clang++`)
**Purpose:** execute the four corroborating experiments behind [`report.md`](report.md) and record the exact commands, verbatim output, and interpretation for each.

The bug under test: in `send()`, `m_available` is incremented *after* the `READY` publish while `m_count` is incremented *before*. Two consumers can both pass the `m_available > 0` fast-path gate on a single credit and each claim a distinct, genuinely-`READY` slot, so two decrements land against one increment → `1 → 0 → −1`, which in the real code's *unsigned* U32 is the wrap to `4294967295` (`0xFFFFFFFF`). The one-line fix moves the increment *before* the publish.

| # | Experiment | Tool | PR as written | With fix |
|---|---|---|---|---|
| 1 | TLA+ model | TLC 2026.08.21 | `NoUnderflow` VIOLATED (`avail = −1`) | No error found (155 states) |
| 2 | Promela model | Spin 6.5.2 | `errors: 1` (`avail = −1`) | `errors: 0` (1992 states) |
| 3 | Executed C++ harness | clang++ / TSan | underflow → `4294967295`, no TSan race | exactly-once, max avail == depth |
| 4 | Real PR code in fprime | fprime UT / TSan | *not re-run here* — see §4 | *(recorded 2026-08-27)* |

Experiments 1–3 were executed in this session and reproduced below verbatim. Experiment 4 requires a full `nasa/fprime` checkout that is not on disk and an authenticated `gh`; its previously-recorded output is summarized in §4.

---

## Experiment 1 — TLA+ / TLC

Two next-state disjuncts keep "publish `READY`" and "increment `avail`" as separate atomic steps (the whole point; collapsing them hides the bug). `FIX = FALSE` = PR as written; `FIX = TRUE` = the fix. Model size: 2 producers, 2 consumers, 2 slots.

### 1a. PR as written (`Buggy.cfg`)

```bash
cd formal
JAR=$(ls ~/.vscode/extensions/tlaplus.vscode-ide-*/tools/tla2tools.jar | tail -1)
java -XX:+UseParallelGC -cp "$JAR" tlc2.TLC -config Buggy.cfg Lockless.tla
```

Output (final states of the counterexample trace):

```
State 8: <CGate(c2) ...>
/\ state = <<"READY", "READY">>
/\ avail = 1
State 9: <CClaim(c1) ...>
/\ state = <<"READING", "READY">>
/\ avail = 0
State 10: <CClaim(c2) ...>
/\ state = <<"READING", "READING">>
/\ avail = -1
316 states generated, 142 distinct states found, 32 states left on queue.
The depth of the complete state graph search is 10.
```

**Interpretation.** TLC found a 10-step trace violating `NoUnderflow`. Both slots are `READY` while `avail` is still 1 (a producer published its second slot before crediting). Both consumers pass the gate on that single credit (`CGate`), then each claims a distinct real slot (`CClaim`), driving `avail` `1 → 0 → −1`. The `−1` is the signed image of the real code's unsigned wrap to `0xFFFFFFFF`.

### 1b. The fix (`Fixed.cfg`)

```bash
java -XX:+UseParallelGC -cp "$JAR" tlc2.TLC -config Fixed.cfg Lockless.tla
```

Output:

```
Model checking completed. No error has been found.
499 states generated, 155 distinct states found, 0 states left on queue.
The depth of the complete state graph search is 11.
```

**Interpretation.** With the increment moved before the publish, both `NoUnderflow` and `UpperBound` (`0 ≤ avail ≤ #slots`) hold across all 155 reachable states. The fixed counter is a benign upper bound.

---

## Experiment 2 — Spin / Promela

Same system, independent encoding. `FIX` undefined = PR as written; `-DFIX` (applied at `spin -a`, not `spin -run`) = the fix. Asserts `avail >= 0` (and `avail <= NSLOTS` when fixed).

### 2a. PR as written

```bash
cd formal
spin -run lockless.pml
```

Output:

```
State-vector 48 byte, depth reached 236, errors: 1
      289 states, stored
      232 states, matched
      521 transitions (= stored+matched)
```

Counterexample replay (`spin -t -p -g lockless.pml`, filtered to `avail`):

```
226: proc 0 (Producer:1) lockless.pml:60  [avail = (avail+1)]   avail = 1
228: proc 3 (Consumer:1) lockless.pml:68  [((avail>0))]
231: proc 2 (Consumer:1) lockless.pml:68  [((avail>0))]
232: proc 3 (Consumer:1) lockless.pml:71  [avail = (avail-1)]   avail = 0
236: proc 2 (Consumer:1) lockless.pml:72  [avail = (avail-1)]   avail = -1
spin: lockless.pml:76, Error: assertion violated
spin: text of failed assertion: assert((avail>=0))
237: proc 2 (Consumer:1) lockless.pml:76  [assert((avail>=0))]  avail = -1
```

**Interpretation.** One credit (`avail = 1`), both consumers pass the `avail>0` gate (steps 228, 231), then both decrement (steps 232, 236) → `1 → 0 → −1`, tripping `assert(avail>=0)`. This is the identical interleaving TLC found, confirmed by a second, independent tool.

### 2b. The fix

```bash
spin -DFIX -a lockless.pml && cc -O2 -DSAFETY -o pan pan.c && ./pan
```

Output:

```
State-vector 48 byte, depth reached 1097, errors: 0
     1992 states, stored
```

**Interpretation.** `errors: 0` across 1992 states: both `avail >= 0` and `avail <= NSLOTS` hold. Same verdict as TLA+.

---

## Experiment 3 — executed C++ harness (`route-b`, incl. ThreadSanitizer)

A standalone transcription of `send`/`receive` with one honest instrumentation point (a delay at the publish→increment seam — an ordinary preemption). Built and run via `route-b/run.sh`.

```bash
cd route-b
bash run.sh
```

Output:

```
== 1) PR AS WRITTEN: expect underflow to 4294967295 ==
mode          : PR AS WRITTEN (increment after publish)
depth         : 16
seam delay    : 50 us
messages recvd: 6
max available observed by 'telemetry' : 2
>>> UNDERFLOW DETECTED: m_available wrapped; getMessagesAvailable() would read 4294967295 (0xFFFFFFFF)
>>> (delivery itself stayed correct up to the stop point: no duplicate fired the assert)

== 2) FIXED: expect exactly-once (missing=0 dup=0) and max available <= depth ==
mode          : FIXED (increment before publish)
depth         : 16
seam delay    : 50 us
messages recvd: 300000
max available observed by 'telemetry' : 16
no underflow observed. exactly-once: missing=0 dup=0; max available (<= depth expected) = 16

== 3) ThreadSanitizer: expect underflow BUT no data-race warning ==
(confirmed: no ThreadSanitizer data-race warning)
```

**Interpretation.**
- **(1)** On the shipped ordering, `getMessagesAvailable()` wraps to `4294967295` in real executed code.
- **(2)** With the fix, 300 000 messages are delivered exactly-once (`missing=0 dup=0`) and the counter never exceeds `depth` (max = 16 = depth) — the benign upper bound the models predicted.
- **(3)** Under ThreadSanitizer the underflow still occurs but **no data race is reported** — demonstrating why the PR's TSan suite structurally cannot catch this: every `m_available` access is a correct atomic op; the defect is the *ordering across two functions*, not a low-level data race.

---

## Experiment 4 — real PR code inside a full `nasa/fprime` checkout (`route-a`)

**Not re-run in this session.** Unlike experiments 1–3, `route-a` is not a self-contained script: it needs a full `nasa/fprime` clone at PR HEAD `3216b31` plus the fprime build environment. By design the repo stores only the applicable patches (`route-a/repro/*.patch`), "not the multi-hundred-MB clone." At run time:

- the prior checkout (`/tmp/fprime-routeA`, 2026-08-27) is no longer on disk — only a loose stray copy of `LocklessPriorityQueue.cpp` remains, not a tree;
- `gh` is unauthenticated (expired token), so `gh pr checkout 5076` cannot reconstruct it here.

To run it: re-auth (`gh auth login -h github.com`), `gh repo clone nasa/fprime && gh pr checkout 5076`, generate/build the UTs (the README documents the macOS `/tmp`↔`/private/tmp` and pip-cmake workarounds), then apply `bug-repro.patch` / `fixed-with-harness.patch` and run the TSan UT with `LOCKLESS_SEAM_US=50`.

### Previously recorded output (2026-08-27, this host)

Bug provoked in the shipped code (seam at 50 µs), via `TEST(AvailableUnderflow, MonitorNeverExceedsDepth)` on the real `Os::Queue` MPMC harness (depth 8, 2 producers × 4000 msgs, 4 consumers):

```
[available-underflow] max getMessagesAvailable() observed = 4294967295 (depth = 8)
Expected: (observed) <= (DEPTH), actual: 4294967295 vs 8
[  FAILED  ] AvailableUnderflow.MonitorNeverExceedsDepth
```

Delivery-correctness checks did **not** fail (consumed == total, each value received exactly once) — a counter-only defect, no data loss.

One-line fix applied (`m_available.fetch_add` moved before `store(READY, release)`), same seam:

```
[available-underflow] max getMessagesAvailable() observed = 8 (depth = 8)
[  PASSED  ] 1 test.
```

Regression: the author's own `LocklessPriorityQueueTest` still **29/29 PASSED**; the shipped suites also pass green as delivered (functional 29/29, TSan 15/15, no races), which does not clear the bug since none assert `getMessagesAvailable() <= depth`.

**Interpretation.** The defect is present in the real PR code, not just the transcription; the one-line fix caps the counter at `depth` in-tree; and a fully green test suite is consistent with the bug being present. Full details and commands: [`route-a/README.md`](route-a/README.md) and [`route-a/repro/README.md`](route-a/repro/README.md).

---

## Bottom line

Two model checkers (TLA+/TLC, Spin/Promela) and an executed C++ harness — run live in this session — all reproduce the `m_available` underflow on the PR as written and certify the one-line fix; ThreadSanitizer confirms the defect is invisible to it. The real-code reproduction (route-a), recorded earlier on this host, reaches the same verdict in-tree. Every result above is actual tool output, not an assertion.
