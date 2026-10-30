# Route A — reproduce the `m_available` underflow in the REAL PR code

These three patches let anyone reproduce, from a clean checkout, exactly what we did on this host:
provoke the underflow in the shipped `Os::Generic::LocklessPriorityQueue` and confirm the one-line
fix. We store the **patches** (a few KB) rather than the full `nasa/fprime` clone — the clone is
just upstream plus these diffs and is reconstructed with a single `gh pr checkout`.

All three apply cleanly to **PR #5076 at HEAD `3216b31`** ("Address review: receivable-count
getMessagesAvailable, empty-receive fast path, …").

| Patch | For merge? | What it does | Expected result |
|---|---|---|---|
| `fix.patch` | **Yes — this is the proposed change** | The one-line reorder from `report.md` §6: credit `m_available` *before* publishing `READY`. No test, no seam. | `getMessagesAvailable()` becomes a benign upper bound; underflow unreachable. |
| `bug-repro.patch` | No (marked "not for merge") | Adds the `AvailableUnderflow.MonitorNeverExceedsDepth` test **and** an env-gated seam, leaving the **original (buggy) ordering**. | With the seam active the test **FAILS**: reads `getMessagesAvailable() == 4294967295`. |
| `fixed-with-harness.patch` | No (test/seam not for merge) | The same test + seam **with the fix applied** (i.e. `bug-repro` + `fix`, but as one self-contained diff off HEAD). | Same seam active, test **PASSES**: max reading `== 8 == depth`. |

`bug-repro.patch` and `fixed-with-harness.patch` are **alternatives** — apply one *or* the other to a
clean HEAD, not both. `fix.patch` is the isolated real change to send upstream.

## The seam (why it's honest, not a cheat)

The seam is a single `std::this_thread::sleep_for(microseconds)` gated on the `LOCKLESS_SEAM_US`
environment variable, placed between the `READY` publish and the `m_available` increment in
`send()`. A producer descheduled at that exact point — by an interrupt, the RTOS scheduler, or a
lost time slice — is an ordinary event. The seam does **not** create an impossible ordering; it
widens an existing window so two concurrent consumers reliably land in it. Remove it and the same
bug still exists, just far rarer by chance. It is clearly marked "TEMPORARY REVIEW INSTRUMENTATION
(not for merge)" and is not part of the proposed fix.

## Steps (as executed on this host, 2026-08-27)

```bash
# 0. clean checkout of the PR under review
gh repo clone nasa/fprime && cd fprime
gh pr checkout 5076              # HEAD 3216b31

# 1. SEE THE BUG
git apply /path/to/bug-repro.patch
#   ...build the TSan UT (see ../README.md §3 for the exact cmake/ninja lines on macOS)...
LOCKLESS_SEAM_US=50 ./bin/.../LocklessPriorityQueueTsanTest --gtest_filter='AvailableUnderflow.*'
#   -> [available-underflow] max getMessagesAvailable() observed = 4294967295 (depth = 8)
#   -> [  FAILED  ] AvailableUnderflow.MonitorNeverExceedsDepth
#      (delivery still exactly-once: no message lost or duplicated — a counter-only defect)

# 2. CONFIRM THE FIX  (fresh checkout, or `git checkout -- Os/Generic` first)
git apply /path/to/fixed-with-harness.patch
LOCKLESS_SEAM_US=50 ./bin/.../LocklessPriorityQueueTsanTest --gtest_filter='AvailableUnderflow.*'
#   -> [available-underflow] max getMessagesAvailable() observed = 8 (depth = 8)
#   -> [  PASSED  ]

# 3. REGRESSION: author's own functional suite still green after the fix
#   -> LocklessPriorityQueueTest : 29/29 PASSED
```

The test uses depth 8, 2 producers × 4000 messages, 4 consumers, and a monitor thread sampling
`getMessagesAvailable()` into a 64-bit max (so an unsigned wrap to `0xFFFFFFFF` is captured
verbatim, not clamped). It asserts `max <= depth` and, independently, exactly-once delivery.

See [`../README.md`](../README.md) for the full Route A checklist and the host build commands, and
[`../../report.md`](../../report.md) §5–§8 for the mechanism, the fix, and why the shipped TSan
suite cannot catch it.
