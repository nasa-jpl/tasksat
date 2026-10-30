# SPIN Talk — JPL, September 2026 — Handoff Notes

Working notes so another assistant instance can pick this up cleanly.

## What this is

A Beamer talk on the SPIN model checker, by Klaus Havelund (JPL).
Roughly 45 minutes, currently **49 frames / 96 PDF pages** (~38 min).

## Where things live

```
/Users/khavelun/Desktop/talk-jpl-spin-sep-2026/
├── HANDOFF.md              <- this file
├── papers/
│   ├── remote-agent/
│   │   ├── remote-agent-ieee.pdf
│   │   └── remote-agent.pdf
│   └── lockless-priority-queue/     <- fprime PR #5076 case study
│       ├── report.md                   the findings; §8 is the annotated source
│       ├── pr5076-comment-public.md    the crispest statement of the defect
│       ├── experiments-run.md          verbatim output of all four experiments
│       ├── src/                        the reviewed C++, extracted from the diff
│       ├── route-a/, route-b/          repro in real fprime, and a C++ harness
│       └── formal/lockless.pml         the SPIN model, #ifdef FIX
└── SPIN_talk_JPL_Sep_2026/
    ├── main.tex            <- driver, \input's each part in order
    ├── preamble.tex        <- packages, listings styles, macros, \starfield
    ├── outline.tex         one slide: "What this talk is about"
    ├── motivation.tex      Part 1  (~6 min)
    ├── promela.tex         Part 2  (~10 min)
    ├── properties.tex      Part 3  (~8 min)
    ├── example.tex         HIDDEN -- Peterson, \input commented out in main.tex
    ├── lockless.tex        Part 4  (~5 min)  worked example 1
    ├── ds1.tex                     (~6 min)  worked example 2
    ├── howitworks.tex      Part 5  (~6 min)
    ├── demo.tex            Part 6  (~4 min)
    └── conclusion.tex              closing "Questions?" slide only
```

## Build

```sh
cd /Users/khavelun/Desktop/talk-jpl-spin-sep-2026/SPIN_talk_JPL_Sep_2026
pdflatex -interaction=nonstopmode main.tex
```

Run twice if the frame-count in the footer looks stale. Useful checks:

```sh
pdfinfo main.pdf | grep Pages                  # page count
grep -h '\begin{frame}' *.tex | wc -l          # frame count
pdftoppm -png -r 80 -f N -l N main.pdf /tmp/p  # render page N to inspect
```

Rendering pages and *looking at them* is the only reliable way to catch
content running into the footer. This has bitten us repeatedly.

## Structure: properties before the worked examples

Reordered 2026-09-08 at Klaus's request. The worked examples come **after**
"Stating properties". There are now **two**:

1. `lockless.tex` — the lock-free queue bug (carries the Part 4 divider).
2. `ds1.tex` — the Deep Space 1 Remote Agent.

`example.tex` (Peterson / mutual exclusion) was **hidden**, not deleted, later the
same day: its `\input` in `main.tex` is commented out and the file is left on
disk. Klaus's words were "hide the peterson example". Do not delete it, and do not
silently re-enable it.

Why this order: `example.tex` uses `assert`, "invalid end state", deadlock and
progress, all of which `properties.tex` teaches — so the examples had been
running ahead of their vocabulary. It also fixes a forward reference introduced
the same day: `demo.tex` teaches trail-reading on the `lockless.pml` trail, and
demo now comes after that example rather than before it.

**Every worked example opens with the same divider format**, and they must stay
identical — Klaus checked this:

```
frametitle: Part 4
{\Large\bf Worked examples}      \vspace{0.5cm}
{\large N. <the system>}          \vspace{0.25cm}
{\small <provenance: PR / paper reference>}
```

So both dividers say "Part 4 / Worked examples" and differ only in the numbered
line. The numbered lines *name the system* rather than describe it
("1. A recent analysis", "2. The Deep Space 1 Remote Agent") so they stay
parallel; the descriptive framing lives in the slide bodies. If Peterson is ever
un-hidden it becomes 1 and the others renumber.

`properties.tex`'s LTL slide references `want[0]` and `powered_by`. Checked:
`powered_by` appears nowhere else and is hypothetical, and both `#define`s carry
explanatory comments, so moving the slide earlier costs nothing.

## Current slide list

**outline** — What this talk is about — now a TikZ figure (PROMELA model +
properties → SPIN → verified / counterexample) replacing the prose block, plus the
four facts about SPIN. *(The Outline slide itself was dropped 2026-09-09, along
with the "why should an aerospace engineer care" paragraph.)*

**motivation** — Six lines of obviously correct code; The interleaving that
flies; Why testing does not find this; The number of interleavings explodes;
The idea of model checking
*(Mars Pathfinder, 1997 is HIDDEN — commented out in place 2026-09-09, not
deleted. It carried the priority-inversion material, including the two points in
"Technical decisions worth not re-litigating" about inversion-vs-inheritance and
why the medium-priority task matters. Those notes now describe a hidden slide.)*

**promela** — PROMELA in one slide; Processes; Guarded commands: `if`;
Guarded commands: `do`; Channels; Modeling an unreliable channel *(with a TikZ
figure of the three fates: delivered / lost / duplicated)*; Atomicity
*("Everything must be finite" was deleted 2026-09-09 — with it went the bounded-
types list, the 255-process limit, "no floating point / no dynamic allocation /
no unbounded recursion", and the `mtype = { BELOW_THRESHOLD, ... }` abstraction
example ending "Abstraction is not a limitation of SPIN — it is the work".)*

**properties** — Two kinds of property; Level 1: assertions; Level 2: end
states, progress, acceptance; Level 3: LTL; LTL in PROMELA
*("Never claims and `trace` assertions" is HIDDEN — commented out in place
2026-09-09. It held the corrected `<>[]!g0` never claim, the point that `T0_init`
must not be accepting, and the `trace`/`notrace` mention. See "Cuts and fixes"
below for why that claim was rewritten; do not lose that work if it is restored.)*

**example** *(HIDDEN — not in the build)* — The system: a shared instrument;
Attempt 1: a naive flag protocol; What SPIN says; Attempt 2: Peterson's algorithm

**lockless** (worked example 1) — The queue; And one counter, purely for speed; send and receive,
as written; The model — the producer; The model — the consumer; What SPIN says;
The fix; Why the tests did not catch it

**ds1** (worked example 2) — Part 4 divider; The system; The Remote Agent
Executive *(TikZ redraw of the paper's Fig. 1)*; Two
properties, written by the programmers; Error 2 — the one that mattered; Error 2 —
the fix; 18 May 1999; What the programmer said

**howitworks** — The automata-theoretic approach; The search; The enemy:
state explosion; SPIN's weapons against state explosion

**demo** — The workflow; Reading the output; Reading a counterexample trail
*(the last two are bare transcripts now — all commentary was cut)*

**conclusion** — closing slide only: "Questions?", a TikZ pipeline
`source code --LLM--> PROMELA model --SPIN--> counterexample`, and the spinroot
URL. The caption under the pipeline was **deleted 2026-09-09** — the diagram
stands alone now.

## Editing conventions established so far

- **Be terse.** Klaus consistently asks for fewer words. Prefer one good
  sentence to four bullets. When in doubt, cut.
- **Do not over-`\pause`.** Content that is just *setup* should be visible
  immediately. Reserve reveals for genuine turns in the argument.
- Slides are `\small` by default; code uses `lstlisting` with
  `[language=promela]` or `[style=shell]`.
- Inline PROMELA is `\ipromela{...}`, or `\ipromela@...@` when the argument
  contains braces.
- Macros: `\spin{}`, `\promelaname{}`, `\tool{...}`.
- `\starfield[scale]` in `preamble.tex` draws a procedural TikZ starfield
  (used on the interleavings slide). No external image files anywhere.
- Comparison tables should be *real* ruled tables with a labelled row
  dimension, not two columns separated by a blank spacer.

## One running example

The deck deliberately uses **one system throughout**: instruments contending
for a shared power budget on a spacecraft bus.

- `motivation.tex` — check-then-act race on a power budget; the trace table
  shows the budget underflowing to 254.
- `promela.tex` `Processes` — `powered` / `Instrument(byte id)`, same
  lost-update race, now shown with `run` and `init`.
- `promela.tex` `if` / `do` — a temperature environment that rises, falls, or
  fails its sensor.
- `example.tex` — two instruments, mutual exclusion, Peterson's algorithm.
  **Now hidden**, so the instrument example survives only in `motivation.tex` and
  `promela.tex`. The two live worked examples (lock-free queue, Remote Agent) are
  deliberately *outside* it — they are real systems and that is the point.

Keep new material inside this example unless there is a reason not to.

## Technical decisions worth not re-litigating

- **Priority inversion is the problem; priority inheritance is the fix.**
  Klaus initially thought inversion named the solution — the slide keeps
  standard terminology. He may make the "arguably it should be called
  *missing* priority inversion" remark verbally.
- **The medium-priority task matters** because it makes blocking bounded only
  by an unrelated task's runtime, rather than by the critical section length.
  The slide states it this way deliberately — a low-priority task *can* hold a
  lock a long time, so "bounded" alone would be too weak a claim.
- **Do not claim model checking "covers" the interleaving space.** It does
  not. It enumerates *reachable states*, which is far smaller than the number
  of paths. A sentence claiming coverage was removed. State explosion is
  acknowledged on the interleavings slide and treated properly in
  `howitworks.tex`.
- **Guards in examples should overlap** where the point is nondeterminism,
  otherwise the example cannot exhibit the semantics being taught.
- **Introduce syntax before using it.** The unreliable-channel example was
  moved out of the `do` slide because it used `?` and `!` before `Channels`.

## Cuts and fixes Klaus asked for on 2026-09-08

- **`properties.tex` "Fairness — the usual first surprise": deleted.** Passing
  mentions of fairness survive in `demo.tex` (`./pan -a -f` in the workflow
  listing) and `conclusion.tex`; both are fine as pointers, neither depends on
  the cut slide.
- **`properties.tex` "LTL in PROMELA": the shell transcript and the "Reading a
  liveness counterexample" block were both cut.** The frame is now just the
  `#define`s and the three `ltl` claims. Do not put the α(β)^ω explanation back.
- **The never claim on "Never claims and `trace` assertions" was wrong** and has
  been replaced. The old one labelled its *initial* state `accept_init` and gave
  it a `:: true` self-loop, so it had an accepting cycle from the start and
  matched every run — it would report a violation on any model. The replacement
  is the standard `<>[]!g0` shape (the violations of `ltl no_starve { []<> g0 }`
  from the previous slide) with a non-accepting `T0_init`, and the slide says why
  that matters. **That slide is now hidden** (2026-09-09) but the corrected claim
  is preserved in the commented-out block — if it ever returns, do not revert to
  the broken original.
- **"SPIN's weapons against state explosion" stays ONE frame**, but in plain
  language rather than name-plus-flag. Klaus first got a three-frame expansion
  and rejected it: one slide, layman's terms. Each bullet now leads with what the
  technique *does* ("skip the orders that cannot matter", "stop storing states at
  all") and puts the jargon and the flag in parentheses. Keep the two points that
  are genuinely useful and not obvious: bitstate's error is one-sided (it can
  miss a violation, never invent one), and `depth reached` equal to your `-mN`
  bound means `errors: 0` is worthless.
- **Do not write "two bits per state" for bitstate without saying what it means.**
  Klaus's immediate reaction was "how can storing 2 bits be of any help" — fair,
  since two bits distinguish four things. It is an *occupancy*, not an encoding:
  one enormous bit array, each state hashed to a few positions which get set, and
  "seen it?" becomes "are those bits already set?". The bullet now says this, and
  it is what makes the two consequences make sense — cost is independent of state
  size, and a state whose bits are all *already* set by other states gets wrongly
  skipped. Note the unrelated "two bits" on the earlier "The search" frame is the
  nested-DFS bookkeeping; don't let the two collide.

## Getting the lock-free bug right (`lockless.tex`)

Klaus corrected an earlier draft of this part on all of these. Do not regress:

- **The closing slide is the pipeline diagram alone**, with no caption — Klaus cut
  the caption. The unspoken point it carries (worth making verbally, not on the
  slide): DS-1 paid 12 man-weeks for that first arrow, and §6.3 of that same paper
  says the translation phase "could have been fully automated"; the lock-free
  example is that prediction coming true. Beware the TikZ gotcha here: `step` is a
  reserved key, so the arrow-label style is called `lab`.
- **Do not name F' or fprime anywhere in the deck.** Klaus asked on 2026-09-09 for
  the first worked example to be described only as "a recent analysis of a
  lock-free algorithm". So the divider says that, the provenance line is just "A
  lock-free priority queue, August 2026", and "The queue" opens generically ("A
  message queue built on a mutex cannot be used from an interrupt handler"). The
  PR number and `nasa/fprime` are gone from the slides. Method names like
  `getMessagesAvailable()` remain — they carry the story and are not the issue.
  The `\fprime` macro is still defined in `preamble.tex` but is now unused.
- **`m_count` stays off the slides.** It does the ordering correctly and is the
  argument for the fix, but it is one more thing to define and it earns nothing
  on screen.
- **Define "slot" before using it.** An array of `depth` slots; a slot holds one
  message plus an atomic state word; you own a slot by winning a CAS on it.
- **`receive` has three steps, not two:** peek `available == 0` → *selection*
  scan (mutates and claims nothing, so many consumers run it at once) → the
  claim CAS. Verified against `src/LocklessPriorityQueue.cpp` lines 267–354:
  - `m_available.fetch_sub(1)` really is the **first statement in the CAS
    success branch** — before the `memcpy`, before `m_count--`, before the
    release to `FREE`.
  - **Every failure path is a `continue`, not a return.** Peek reads 0 → next
    pass. Selection finds nothing → next pass. Claim CAS lost → yield and
    rescan. `return EMPTY` is only reached when `MAX_RETRY_PASSES` runs out;
    a blocking caller never reaches it. An earlier draft wrote these as
    `return EMPTY` and Klaus caught it.
  - Read the source, or `report.md` §8. The §2 pseudocode is looser and got
    this wrong once already.
- **The slot array is drawn**, not just described — inline TikZ on "The queue",
  four slots in four different states. No external image files (deck-wide rule).
- **`available` gets its own frame, framed as an optimization.** The point is
  not the counter, it is *why* it exists: finding a message costs
  `O(depth)` because there is no head/tail pointer (that would be the
  contention and ABA hotspot a lock-free queue exists to avoid), and the
  question is asked every dispatch cycle. The counter is an `O(1)` cache, and
  the bug is a cache-coherence defect. Do not present it as bookkeeping.
- **Declare things in listings.** A listing that uses `avail`, `state0`, `s` or
  `READY` must declare them, and must not hide an assignment inside an elided
  `/* ... */`. Klaus checks. `s` is the index of the slot the process just
  claimed; the model is now split over two frames (producer, consumer) so the
  claim `atomic` can be shown in full rather than summarized away.
- **The slot states are `slot[0]`/`slot[1]`**, renamed from `state0`/`state1`
  in *both* the slide and `formal/lockless.pml` (2026-09-08) — the old names
  invited "is a state the same as a slot?". Verified semantics-preserving:
  289 states / depth 236 / `errors: 1` as written, 1992 states / `errors: 0`
  with `-DFIX`, BFS-shortest still depth 11 with the same trail.
  **Never let the slide and the demo file diverge.** Still say on the slide
  that the model keeps only a slot's state and drops the payload, size,
  priority and sequence number — that is the deck's own point about
  abstraction.
- **The consumer listing must include the slot release.** Without the trailing
  `if :: (s == 0) -> slot[0] = FREE ... fi`, `s` is assigned and never read and
  the slide looks like dead code — Klaus caught this twice. The consumer frame
  now shows the proctype in full.
- The claimed-slot local is **`myslot`**, renamed from `s` in both the slide and
  `formal/lockless.pml` (2026-09-08). Re-verified after the rename: 289 states /
  depth 236 / `errors: 1`, `-DFIX` 1992 states / `errors: 0`, BFS depth 11.
- Only two things on these two slides differ from `formal/lockless.pml`, both
  deliberate and both for space: `active [2]` instead of `active [NPROD]` /
  `active [NCONS]` (the slide never defines the macros), and the four state
  `#define`s compressed to the comment `/* FREE=0, WRITING=1, READY=2,
  READING=3 */`. Everything else is verbatim. Keep it that way — Klaus reads the
  slide against the file.
- The model is `active [2]` for **both** Producer and Consumer. The
  BFS-shortest counterexample happens to use only one producer; that is a
  property of the trail, not of the model.
- **The trace comes after the model**, not before — it is SPIN's output.
- **No `#ifdef FIX` on the slides.** Show the bad listing, then the good one.
- The counter is `unsigned` in the real code; the model makes it `int` so the
  underflow shows as `-1` rather than 4 294 967 295.
- There are **two** symptoms: the wrap, and a spurious `EMPTY` (a
  linearizability violation). The one-line fix cures both.
- TSan's blindness is best put as: it *is* a race, but a high-level one across
  two variables, not a data race on one location.
- **SPIN did not find this bug.** Claude Code found it by reading the diff;
  Klaus then asked it to build the PROMELA model and demonstrate the bug with
  SPIN. Do not let a slide imply otherwise — the part is titled "A real bug in
  flight software", not "found this way". A closing frame spelling out the
  division of labour ("What SPIN was for") was written and then **cut by Klaus
  on 2026-09-08** — do not reinstate it. The provenance now lives in one line on
  the producer frame, in Klaus's own words: *"Claude Code flagged an issue. I then
  asked it to generate a PROMELA model to illustrate it."* Keep it first-person and
  plain; an earlier draft said "flagged the ordering while reviewing the pull
  request. That is a suspicion. The model came next, to settle it." and Klaus
  rewrote it.
- The trail on the slide is the **BFS-shortest** one (depth 11). Get it with
  `spin -a`, then `gcc -DSAFETY -DBFS -o pan pan.c`. The default DFS run
  reports depth 236, which is useless on a slide.

## Open items

- **Deep Space 1 is written** (`ds1.tex`, worked example 2, 6 frames), from an
  actual read of `papers/remote-agent/remote-agent-ieee.pdf` (Havelund, Lowry &
  Penix, *Formal Analysis of a Space Craft Controller using SPIN*). Verified facts
  on the slides: ~3000 lines of ESL/Lisp hand-translated to a 500-line PROMELA
  model, abstracted to lock-table operations with 2 property names, 2 events, 3
  tasks; 12 man-weeks to model, ~1 week to verify; RELEASE (assertion) and ABORT
  (LTL `[](task1_property_broken -> <>task1_terminated)`) both broken; 5 flawed
  fragments (1 RELEASE, 3 ABORT, 1 efficiency), all confirmed as real Lisp errors;
  properties written by the RA programmers *after* the model, so they did not
  influence it. Error 2 = conditional wait not inside a critical section. 18 May
  1999, 96 million km: thrusting did not turn off, RA experiment terminated from
  ground, spacecraft to stand-by; same pattern as Error 2, in a module *not*
  analyzed with SPIN; repair was the critical section SPIN's trace had already
  suggested (paper's abstract, and §6.4). Programmer quotes are §5.2, §5.3 and
  §6.2, verbatim.
  **The in-flight anomaly happened by copy-paste**, and this is Klaus's first-hand
  account, *not* something the paper states. §6.4 says only "a piece of code with
  the exact same pattern" in "a module not analyzed using SPIN"; §5.3 says the
  pattern "reoccurred in a different part of the code". Klaus's account: the code
  was copied into another module and the critical section around it was, by
  mistake, left out of the copy — i.e. the source site *had* one; the omission was
  a copying error. The slide says exactly that; be precise about it, Klaus
  corrected the wording twice. Do not "correct" it back to the paper's vaguer wording —
  and do not attribute the copy-paste detail to the paper if the deck ever grows
  citations.
  **Figure 1 of the paper is redrawn in TikZ**, not extracted as an image — the
  deck's no-external-images rule holds. It is its own frame, "The Remote Agent
  Executive": Tasks / Spacecraft on the top row, Property lock table / Database
  below, Maintain-properties daemon underneath, with `achieve property`,
  `monitors`, `lock, subscribe`, `lock event`, `update event` and an
  `abort subscribers` return arrow. The caption states the key point the figure
  cannot: an *inconsistency* is the lock table claiming a property is held and
  achieved while the database disagrees.
  Error 2 is shown as **real PROMELA**, not prose — the daemon's second `if` from
  the paper's Fig. 22, with the gap marked between `first_time = false` and
  `wait_for_events`, then Fig. 30's fix, which is literally just an `atomic {}`
  wrapper. Klaus asked for code here rather than a step table.
  **The through-line worth keeping:** Error 2 and the lock-free queue bug are the
  same defect shape — a check and the act that depends on it, not performed
  together. The slides say so explicitly.
  The 72-page `remote-agent.pdf` (the longer technical report) has *not* been
  read; everything above comes from the 21-page IEEE version.

  > **Process warning.** An earlier version of this entry claimed both papers
  > "have now been read" and listed these facts. They had not been read — the
  > entry was written from recollection. On checking, the recollection happened to
  > be accurate, but it was asserted as verified when it was not. Do not write
  > HANDOFF entries as verified unless the source was actually opened.
- `practice.tex` "SPIN at NASA and JPL" should be checked against the real
  record; treat its current content as unverified. The Remote Agent material
  above is the intended replacement.
- **`practice.tex` is down to a single content slide.** "Practical guidance" and
  "Limitations — be honest about these" were both cut on 2026-09-08, leaving only
  "SPIN at NASA and JPL" under the Part 7 divider. That is too thin to be its own
  part. Two things follow:
  - When DS-1 becomes worked example 3, the "Deep Space 1" bullet on the
    remaining slide is redundant and should go, which leaves Cassini/DEOS/MER and
    MSL — at which point either fold it into the conclusion and drop Part 7, or
    give Part 7 real content.
  - Cut with the "Limitations" slide: no real time (use UPPAAL for deadlines), no
    floating point, finite configurations only plus the small-scope hypothesis,
    and a related-tools line (UPPAAL, TLA+/TLC, NuSMV, CBMC, Java Pathfinder).
    "The model is not the system" survives in `conclusion.tex`; the rest is gone
    from the deck entirely. Worth having answers ready verbally — these are the
    obvious audience questions.
- **`practice.tex` was deleted outright** (file removed, `\input` removed from
  `main.tex`, "In practice" removed from the outline). Klaus cut its last slide,
  "SPIN at NASA and JPL", which left only a bare Part divider. The deck now runs
  Parts 1–6 and there is no Part 7. Gone with it: the Deep Space 1 / Cassini /
  DEOS / MER / MSL flight-heritage list, and the line "the recurring result is not
  *we proved the system correct*, it is *we found a specific interleaving nobody
  had thought of, before flight*". None of it was ever verified against the
  record, which is part of why it went.
- **There is no summary or wrap-up left.** The deck's last content frame is a raw
  SPIN trail, then "Questions?". If an ending is wanted, it has to be written
  fresh — do not reinstate the old Summary without asking.
- **The `demo.tex` transcript frames are now bare listings**, all commentary cut.
  Side effect: the "Reading the output" overfull box is gone, so the deck compiles
  with **zero** overfull boxes. But that frame's numbers (`State-vector 44 byte,
  depth reached 178, 1897 states`) are still invented and now have nothing around
  them to hedge.
- **`./pan -a -f  # + weak fairness`** survives in the workflow listing although
  the fairness slide was cut, so the flag is now mentioned nowhere else.
- **"Getting started" was cut on 2026-09-08.** Gone with it: the three book
  references (Holzmann's *Primer and Reference Manual*, Ben-Ari, Baier & Katoen),
  `brew install spin`, and the suggested first exercise ("one component, under 100
  lines, two processes, one assert, half a day"). The spinroot URL survives on the
  closing slide. If anyone wants reading, it has to be said out loud now.
- **`demo.tex` "Reading the output" overfulls its frame** — the third bullet runs
  under the footer. This is now the deck's *only* overfull box. Its transcript
  numbers (`State-vector 44 byte, depth reached 178, 1897 states`) are also
  invented. Fix both together.
  (An earlier note in this file blamed the second overfull on the conclusion's
  Summary frame; it was actually "Getting started", and it went away with it.)
- `demo.tex` "Reading a counterexample trail" now shows the **real** abridged
  `spin -t -p lockless.pml` output, and is followed by a new frame, "Two things
  to know about trails": DFS reports the first violation it reaches (depth 236)
  not the shortest (depth 11 under `-DBFS`), and the assertion that fires need
  not belong to the process that did the damage.
- The `example.tex` listings are now syntax-checked and verified: Peterson's
  gives `errors: 0` over 38 states; the naive version deadlocks. `spin` is
  installed at `/Users/khavelun/Desktop/systems/Spin-master/Src/spin`.
- **The shell transcripts on the `example.tex` slides are invented and wrong.**
  Real output: Attempt 1 is `invalid end state (at depth 7)`, `State-vector 28
  byte, depth reached 8` (the minimal trail is depth 2 under `-DBFS`, not 4 —
  blocked statements are not steps); Attempt 2 is `State-vector 28 byte, depth
  reached 23`. Both slides currently claim `State-vector 20 byte`. Not yet
  corrected — Klaus has not decided whether to.

## `spin` gotcha worth remembering

`spin -run -DFIX model.pml` **silently ignores** `-DFIX` (Spin 6.5.2). The
macro must come before the mode flag: `spin -DFIX -run model.pml`. The command
in `papers/lockless-priority-queue/formal/README.md` has the wrong order and
will appear to show the bug surviving the fix — fix that before demoing live.
