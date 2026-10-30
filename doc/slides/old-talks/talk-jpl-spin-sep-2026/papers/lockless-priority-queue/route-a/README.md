# Route A — build & validate inside F′ (checklist)

The real validation: build `Os::Generic::LocklessPriorityQueue` inside a full fprime checkout,
run the author's own tests, and — most importantly — answer the questions Route B *cannot*
(lock-freedom and memory model on the actual target). This is a checklist for whoever has the
fprime build environment; it does not run here.

> Legend: **[R]** = run/verify a fact, **[A]** = add something (test/assert), **[?]** = confirm
> the exact command in your tree — fprime's CMake targets and sanitizer flags vary by version,
> so treat command lines below as the shape, not gospel.

---

## Results obtained on this host (2026-08-27, macOS arm64, Apple clang 21)

We actually executed §1–§4/§7-partial of this checklist on this machine (fresh shallow clone,
not the user's repo). Outcome:

- **PR checkout** — `nasa/fprime` + `pull/5076/head`, HEAD `3216b31` ("Address review:
  receivable-count getMessagesAvailable, empty-receive fast path, …"). This HEAD is the current
  PR revision, i.e. the version whose `m_available` *is* the receivable-count design our review
  flags. Lockless files + `test/ut/LocklessPriorityQueue{Tests,TsanTests}.cpp` all present.
- **Build** — Python venv from the repo's `requirements.txt` resolved `fprime-tools 4.3.0a5` /
  `fprime-fpp 3.3.0a15`; only the `googletest` submodule (4.3 MB) was needed.
- **`LocklessPriorityQueueTest` (functional): 29/29 PASSED** across 7 suites (InterfaceInvalid,
  BasicRules, Blocking, a 10 000-step Random suite, …).
- **`LocklessPriorityQueueTsanTest` (ThreadSanitizer): 15/15 PASSED, zero race reports** (TsanStress
  + Adversarial suites, run with the repo's `tsan-suppressions.txt`).
- **`create()` lock-free asserts (lines 94-99): non-aborting**; `is_lock_free()` = true for
  `uint64_t`/`int32_t`/`uint32_t` **on this host** (arm64). Trivially true on a 64-bit host —
  this only confirms the create path runs; it does NOT answer the flight-target question (§4).

**Crucial interpretation — a green suite does NOT clear the bug.** None of these 44 tests assert
`getMessagesAvailable() <= depth`, so the `m_available` underflow (report §5) survives a fully
green run. This is report §8 demonstrated on the *real* code: the shipped tests pass while the
counter can still wrap. The test that would catch it (§6 below) has **not** been added/run yet.

Friction encountered (host/toolchain only, **not** PR bugs), for reproducibility:
- macOS `/tmp` → `/private/tmp` symlink confuses `fprime-util generate` (settings path resolves
  to `/private/tmp`, CMake source dir to `/tmp`); and the pip `cmake 3.26` from `requirements.txt`
  infinite-recurses in `FindThreads`/`Darwin.cmake` on macOS. Both bypassed by driving the
  **system cmake 4.3.1 directly** with all paths in `/private/tmp` form:
  ```
  cmake -S /private/tmp/fprime-routeA -B .../build-...-ut -G Ninja \
    -DFPRIME_FRAMEWORK_PATH=/private/tmp/fprime-routeA -DFPRIME_PROJECT_ROOT=/private/tmp/fprime-routeA \
    -DFPRIME_SETTINGS_FILE=.../settings.ini -DFPRIME_ENVIRONMENT_FILE=.../settings.ini \
    -DFPRIME_CONFIG_DIR=.../config -DFPRIME_INSTALL_DEST=.../build-artifacts \
    -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Debug
  ninja LocklessPriorityQueueTest
  ```
  TSan used a separate build dir with `-DENABLE_SANITIZER_ADDRESS=OFF
  -DENABLE_SANITIZER_UNDEFINED_BEHAVIOR=OFF -DENABLE_SANITIZER_THREAD=ON` (ASan/UBSan are on by
  default under `BUILD_TESTING` and are mutually exclusive with TSan), then
  `ninja LocklessPriorityQueueTsanTest`.

### Bug provoked in the REAL PR code, and the fix verified in-tree (also executed here)

We then went further and reproduced the underflow in the shipped code itself (not the `route-b`
transcription), and confirmed the one-line fix, all in the same real clone:

- **Instrumentation:** an env-gated seam (`LOCKLESS_SEAM_US`) added to the real
  `Os/Generic/LocklessPriorityQueue.cpp` between the `store(READY, release)` and the
  `m_available.fetch_add` — a `std::this_thread::sleep_for(microseconds)`, marked "TEMPORARY
  REVIEW INSTRUMENTATION (not for merge)". It widens the genuine preemption window; it does not
  manufacture an impossible ordering.
- **Test:** `TEST(AvailableUnderflow, MonitorNeverExceedsDepth)` appended to the already-registered
  `LocklessPriorityQueueTsanTests.cpp`, reusing that file's real `Os::Queue`-based MPMC harness
  (so it drives the **real** `LocklessPriorityQueue`). depth=8, 2 producers × 4000 msgs, 4
  consumers; samples `getMessagesAvailable()` into a 64-bit max and asserts `max <= depth`; also
  tracks per-value delivery.
- **Bug appears (`LOCKLESS_SEAM_US=50`):**
  ```
  [available-underflow] max getMessagesAvailable() observed = 4294967295 (depth = 8)
  Expected: (observed) <= (DEPTH), actual: 4294967295 vs 8
  [  FAILED  ] AvailableUnderflow.MonitorNeverExceedsDepth
  ```
  Delivery-correctness checks did **not** fail (consumed == total, each value received exactly
  once) — only the underflow assertion. Confirms: observability/counter defect, no data loss.
- **One-line fix (statement reorder):** move `m_available.fetch_add(1, acq_rel)` to *before*
  `store(READY, release)`. Same command, seam still at 50µs:
  ```
  [available-underflow] max getMessagesAvailable() observed = 8 (depth = 8)
  [  PASSED  ] 1 test.
  ```
  The counter is now a benign upper bound that never exceeds depth, even with the window forced open.
- **Regression check:** the author's existing `LocklessPriorityQueueTest` still **29/29 PASSED**
  after the fix — it breaks nothing.

The exact diffs are saved as applicable patches in [`repro/`](repro/) — `fix.patch` (the proposed
one-line change), `bug-repro.patch` (apply to clean HEAD to *see* the failure), and
`fixed-with-harness.patch` (apply to see it pass). See [`repro/README.md`](repro/README.md) for
the step-by-step. We keep the patches, not the multi-hundred-MB clone, which is just `nasa/fprime`
at HEAD `3216b31` plus these diffs.

**Still out of scope:** the on-target checks (§4 lock-freedom on the flight CPU, §5 weakly-ordered
+ real ISR) — no flight toolchain here. Everything above ran on a 64-bit host.

---

## 0. Prerequisites

- [ ] **[R]** A working fprime dev environment: the fprime Python venv (`fprime-tools`, giving
      `fprime-util`), CMake ≥ the version fprime requires, and a C++14 host compiler.
- [ ] **[R]** For the target checks in §4–§5: the **cross-compilation toolchain for the actual
      flight CPU** (the fprime "platform"/toolchain files for that board). This is the part that
      actually de-risks the deliverable — without it you only ever test a 64-bit host.

## 1. Get the code

- [ ] **[R]** `gh pr checkout 5076` in an `nasa/fprime` clone (or apply `../pr5076.diff` onto the
      commit the PR targets). Confirm the new files are present under `Os/Generic/`:
      `LocklessPriorityQueue.{hpp,cpp}`, `default/config/LocklessQueueCfg.hpp`, the tests, and
      the SDD.

## 2. Build & run the unit tests on the host

- [ ] **[?]** Generate and build the UT build cache for the Os module, e.g.
      `fprime-util generate --ut` then `fprime-util build --ut` (exact invocation depends on
      where you run it — framework root vs. module dir).
- [ ] **[R]** Run `LocklessPriorityQueueTests` (functional/gtest). Expect pass — these exercise
      the happy path and exactly-once, which our review found **correct**.
- [ ] **[R]** Note: a green run here does **not** clear the bug. The existing suite does not assert
      `getMessagesAvailable() <= depth`, so it passes while the counter can still wrap. See §6.

## 3. Run the concurrency sanitizers on the host

- [ ] **[?]** Build the `Tsan` unit tests with ThreadSanitizer enabled (fprime exposes sanitizer
      build options / a sanitizer toolchain — confirm the flag name in your version).
- [ ] **[R]** Run `LocklessPriorityQueueTsanTests` under TSan. Expect **clean**.
- [ ] **[R]** Understand *why* clean ≠ correct: the `m_available` underflow is a race-free logic
      bug on a synchronized atomic, which TSan cannot see (report §8; we reproduced exactly this
      under TSan in `../route-b/`). Do not treat a clean TSan run as absence of the bug.
- [ ] **[R]** Optionally also run under AddressSanitizer/UBSan for the allocation/teardown paths.

## 4. THE key target check — is it actually lock-free on the flight CPU?

This is the single most important item. The entire ISR-safety premise depends on it.

- [ ] **[R]** The PR already gates this at `create()` (src lines 94–99): it asserts
      `std::atomic<LocklessStateTagType>` (U64), `std::atomic<FwQueuePriorityType>`, and
      `std::atomic<U32>` are all `is_lock_free()`. **Cross-compile for the target and confirm
      `create()` does not assert** on real hardware (or a faithful emulator).
- [ ] **[R]** Independently, compile a one-liner for the target printing
      `std::atomic<uint64_t>{}.is_lock_free()` (and the priority/counter types). On small MCUs a
      64-bit atomic can lower to a **libatomic lock/CAS routine** — i.e. NOT lock-free — which
      would silently reintroduce the ISR deadlock the PR exists to avoid.
- [ ] **[R]** If any probe is not lock-free on the target: the design premise fails there. Record
      it; the fix is not the one-line counter change but a type/target reconsideration.

## 5. Memory-model validation on the target

- [ ] **[R]** Run a producer/consumer/stress test **on the target CPU** (weakly-ordered, e.g. ARM),
      not just the x86/arm64 host. Release/acquire bugs that a strongly-ordered host hides can
      surface here. The author's `Tsan` stress test is a good basis; run it on target.
- [ ] **[R]** Confirm the ISR path for real: exercise `send`/`receive` **from an actual ISR
      context** on the target (the motivating use case), not just threads.

## 6. Add the regression test that catches THIS bug

- [ ] **[A]** Add a test seam: a hook that lets a test force a producer to pause between the
      `store(READY)` (src line 240) and `m_available.fetch_add` (src line 244). `../route-b/`
      shows this reproduces the underflow deterministically.
- [ ] **[A]** With ≥2 concurrent consumers and the seam active, assert the invariant
      **`getMessagesAvailable() <= depth`** holds throughout. This fails on the current code and
      passes after the fix — the regression test the prose argument can't provide.
- [ ] **[A]** Also assert no spurious `EMPTY`: a non-blocking `receive` must not return `EMPTY`
      while a fully-published message is queued (the linearizability symptom, report §5).

## 7. Apply and re-verify the fix

- [ ] **[A]** Apply the one-line fix (report §6): move `m_available.fetch_add(1, acq_rel)` to
      **before** the `store(READY, release)` in `send()`.
- [ ] **[R]** Re-run §2, §3, §6. Expect: functional tests still pass; the new §6 invariant now
      holds; `getMessagesAvailable()` becomes a benign upper bound (over-reports by ≤ depth),
      matching the `route-b/ --fixed` result (max observed == depth) and the TLA+ `UpperBound`
      invariant.

## 8. Secondary findings to check (report §7)

- [ ] **[R]** `FW_ASSERT(storedSize <= capacity)` in `receive` (src line 332) fires **after** the
      slot is claimed and on the ISR path. Decide whether this should be a `SIZE_MISMATCH`
      *status* return instead of an assert/abort. Check what `FW_ASSERT` does in the flight
      config (compiled out? fault handler? abort?).
- [ ] **[R]** Sequence numbers are assigned during `WRITING` (src line 232), not "at publication"
      as the SDD/header state. Harmless for a single producer; confirm the FIFO argument for
      concurrent producers and fix the doc if needed.
- [ ] **[R]** Re-read the `teardown()` contract (header): caller must guarantee no concurrent
      `send`/`receive`/`teardown`. Confirm all framework call sites honor it.

---

### Why these and not just "run the tests"

Running the shipped tests (green) tells you the happy path works — which we already believe.
The items that actually add information beyond this review and the models are the **target**
ones: §4 (lock-freedom) and §5 (memory model + real ISR). If you do nothing else in Route A,
do §4.
