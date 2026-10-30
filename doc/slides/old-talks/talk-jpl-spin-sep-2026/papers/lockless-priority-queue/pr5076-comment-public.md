I ran some analysis on the `m_available` bookkeeping and there seems to be an issue; details below.

**Defect: The variable `m_available` may transiently wrap to a huge value, and may make a non-blocking `receive` return `EMPTY`** when there is a message in the queue. The defect lies in the `m_available` counter bookkeeping.

**The wrap.** In `send`, `m_count` is correctly incremented before the `READY` publish (line 238), but `m_available` is incremented **after** it (line 244). A slot becomes claimable the instant `READY` is published, so a consumer can win the claim CAS and run `m_available.fetch_sub` (line 329) before the producer's matching `fetch_add` has landed, which increments `m_available`. As a scenario, assume that the buffer contains exactly one message (`m_available == 1`) and that a producer is now adding a new message: the instant `READY` is published (so effectively there are now two messages in the queue), but there is a delay before
the producer increments `m_available` (so it is still 1). Two consumers now consume the two genuinely-`READY` slots, and each decrements `m_available` by 1: `1 → 0 → 4294967295` since `0 - 1` wraps to `4294967295`. The big number only lasts briefly until the producer adds its delayed 1 (4294967295 + 1 = 0). However, a caller reading 
`getMessagesAvailable()` in that window sees the wrapped value.

**The spurious `EMPTY`.** Assume the queue is empty and a producer adds a message, but again delays before incrementing `m_available`. The non-blocking consumer bails out as soon as `m_available == 0` (line 283). Because the credit is added only after the publish, there is a window in which a message is fully published and claimable while `m_available` still reads `0`. A `receive` landing in that window returns `EMPTY` though a message is available.

**Impact.** Neither effect loses or duplicates a message — delivery remains exactly-once, and both readings are transient and self-correct. The exposure is a wrong value observed by a caller reading the counter (telemetry, or any logic that branches on it).

**The fix is one line.** Move the `m_available` increment in `send()` above the `READY` publish, mirroring `m_count`. Every decrement is then strictly preceded by its matching increment, so the counter can never underflow; it becomes a benign upper bound (may briefly exceed the currently-`READY` count, capped at `depth`).

**Why the TSan suite doesn't flag it.** It is a race, but a high-level one across two variables (the `READY` publish and the credit to `m_available`), not a low-level data race on a single location. Each individual atomic access is properly synchronized, so ThreadSanitizer sees nothing; only the ordering of the two operations is wrong, and that surfaces as a logically incorrect counter value. Nothing in the suite asserts `getMessagesAvailable() <= depth`.

**Corroboration.** The defect was analyzed with two independent model checkers (TLC/TLA+ and Spin/Promela), each reproducing the wrap on the current ordering and certifying the invariant holds after the fix, and it was also demonstrated on the real PR code (the wrapped value appears on the shipped ordering; the counter stays at `depth` after the fix).
