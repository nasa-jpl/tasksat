# Formal models — `m_available` underflow (TLA+ **and** Spin)

Two independent model-checker encodings of the `LocklessPriorityQueue` counter bug. They turn
the prose argument in [`../report.md`](../report.md) §5–§6 into a mechanical, reproducible
result: each *finds the bug* on the PR as written and *certifies the one-line fix*. Modeling
the same system in two different tools (TLA+/TLC and Spin/Promela) is a deliberate cross-check —
they agree.

> Status: initial study. The models deliberately abstract the queue down to the counter bug
> (see "What's modeled" below). Neither is yet a full linearizability spec.

## Files

| File | What it is |
|---|---|
| `Lockless.tla` | **TLA+** spec. One knob, `FIX`: `FALSE` = PR as written (increment `avail` *after* publishing `READY`); `TRUE` = the fix (increment *before* publishing). |
| `Buggy.cfg` | `FIX = FALSE`, 2 producers, 2 consumers, 2 slots. Checks `NoUnderflow`. |
| `Fixed.cfg` | `FIX = TRUE`, same size. Checks `NoUnderflow` **and** `UpperBound`. |
| `lockless.pml` | **Spin/Promela** model of the same system. `FIX` undefined = PR as written; `-DFIX` = the fix. Asserts `avail >= 0` (and `avail <= NSLOTS` when fixed). |

## How to run — TLA+ / TLC

Any TLC works. Using the jar shipped with the VS Code TLA+ extension:

```bash
JAR=$(ls ~/.vscode/extensions/tlaplus.vscode-ide-*/tools/tla2tools.jar | tail -1)
cd formal

# PR as written — expect a NoUnderflow VIOLATION with a counterexample trace:
java -XX:+UseParallelGC -cp "$JAR" tlc2.TLC -config Buggy.cfg Lockless.tla

# The fix — expect "No error has been found":
java -XX:+UseParallelGC -cp "$JAR" tlc2.TLC -config Fixed.cfg Lockless.tla
```

(Or just open `Lockless.tla` in the VS Code TLA+ extension and run each `.cfg` as a model.)

## How to run — Spin / Promela

```bash
cd formal

# PR as written — expect "assertion violated (avail>=0)" with a trail:
spin -run lockless.pml
spin -t -p -g lockless.pml          # replay the counterexample trace

# The fix. NOTE: `spin -run -DFIX` sends -DFIX to the C compiler, NOT to the
# Promela preprocessor, so it will NOT select the fix. Apply the define at the
# `spin -a` stage instead:
spin -DFIX -a lockless.pml && cc -O2 -DSAFETY -o pan pan.c && ./pan
                                     # expect "errors: 0"
rm -f pan pan.* lockless.pml.trail   # clean up generated verifier
```

## Results obtained (2026-08-27)

**TLA+ / TLC 2026.08.21:**
- **`Buggy.cfg` → `NoUnderflow` VIOLATED** at depth 10. `avail` reaches **-1**, which in the
  real code's *unsigned* field is the wrap to `0xFFFFFFFF` (~4.29 billion) described in the
  report. TLC's minimal trace: one producer publishes a second `READY` slot before doing its
  `avail` increment, so two slots are `READY` while `avail` is still 1; both consumers pass the
  `avail > 0` gate on that single credit and each claims a distinct real slot, driving
  `avail` 1 → 0 → -1.
- **`Fixed.cfg` → No error found** across all 155 reachable states: both `NoUnderflow` and
  `UpperBound` (`0 ≤ avail ≤ #slots`) hold. So the fixed counter is a benign upper bound.

**Spin / Promela 6.5.2 (independent cross-check — same conclusion):**
- **PR as written → `assertion violated (avail>=0)`** at depth 236; the replayed trail shows
  both consumers passing the `avail>0` gate, then each claiming a distinct `READY` slot, driving
  `avail` 1 → 0 → **-1** (289 states explored).
- **`-DFIX` → errors: 0** across 1992 states: the `avail >= 0` and `avail <= NSLOTS` assertions
  both hold.

Two tools, two encodings, one verdict: the bug is real on the current code and the one-line
reordering removes it.

## What's modeled (and what's abstracted)

- **Modeled:** the 4-state slot machine (FREE/WRITING/READY/READING) as atomic CAS transitions;
  `avail` as an unbounded integer so underflow is directly observable; the consumer fast-path
  gate as a *peek* separate from the claim; producer publish and increment as **two separate
  atomic steps** (this separation is the whole point — collapsing them hides the bug).
- **Abstracted away on purpose:** the 62-bit ABA tag (the counter bug is independent of it, and
  ABA was verified correct by inspection — see report §4), message payloads/sizes, priorities
  and sequence numbers (the underflow is priority-agnostic), and the C++ memory-order fences
  (modeled coarsely as step interleaving).

## TLA+ vs Spin, in practice

Both tools found this bug with essentially the same abstraction, which underlines that the
choice is a *preference*, not a capability gap (see report §9). The one non-obvious modeling
rule is identical in each: **keep "publish `READY`" and "increment `avail`" as two separate
steps** — in TLA+ that's two next-state disjuncts; in Promela it's two statements *not* wrapped
in one `atomic{}`. Collapse them and the bug disappears in either tool.

## Natural next steps (not yet done)

- Model the **spurious-`EMPTY`** symptom as a temporal/linearizability property, not just the
  counter invariant.
- Sweep larger configs (3 slots, 3 consumers) to confirm the fix scales in-bound.
- ~~Re-encode in Promela/Spin as a cross-check.~~ **Done** — see `lockless.pml` above.
