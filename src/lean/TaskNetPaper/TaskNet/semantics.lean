/-
Lean 4 + mathlib style skeleton for TaskNet Section 3 (Semantics).

Goal: mirror the paper structure:
  - Mathematical objects (TN, timelines, tasks, impacts)
  - Time, states, traces
  - Fitting schedules
  - Impact denotation (additive) + assignment map
  - Execution trace (base + assignment override)
  - Sat / Valid / Safe

Notes:
  * This file focuses on the semantics of numeric timelines (Real-valued)
    because impacts are numeric in your current semantics section.
  * State/Boolean timelines can be incorporated by letting Value be a sum type
    or by splitting L into typed sets; keep it simple here.

Requires mathlib for Real, Set, etc.
-/

import Mathlib.Data.Real.Basic
import Mathlib.Data.Set.Basic
import Mathlib.Tactic

namespace TaskNet

/- =========================
   Basic types
   ========================= -/

abbrev TimelineId := String
abbrev TaskId     := String

/-- Closed interval membership predicate for "ranges as closed real intervals". -/
def InClosed (x : ℝ) (lo hi : ℝ) : Prop := lo ≤ x ∧ x ≤ hi

/-- Clamp to a closed interval [lo, hi]. -/
def clamp (lo hi : ℝ) (x : ℝ) : ℝ :=
max lo (min hi x)

/-- Discrete time domain {0,1,...,T}. -/
def Time (T : ℕ) := { t : ℕ // t ≤ T }

namespace Time
  variable {T : ℕ}
  def val (t : Time T) : ℕ := t.1
end Time

/-- A state is a valuation of all timelines (here: numeric timelines only). -/
abbrev State (L : Set TimelineId) := TimelineId → ℝ

/-- A trace is a function from time to states. -/
abbrev Trace (T : ℕ) (L : Set TimelineId) := Time T → State L

/- =========================
   Timelines (AST-level objects)
   ========================= -/

/--
Timeline data for a (numeric) timeline:
  Dℓ is ℝ,
  Rℓ is admissible range (closed interval),
  Bℓ is clamping range with B ⊆ R.
We model R,B as (lo,hi) pairs.
-/
structure Timeline where
  id   : TimelineId
  Rlo  : ℝ
  Rhi  : ℝ
  Blo  : ℝ
  Bhi  : ℝ
  /-- bounds within range: B ⊆ R -/
  bounds_in_range : Rlo ≤ Blo ∧ Bhi ≤ Rhi
  /-- well-formed intervals -/
  Rwf : Rlo ≤ Rhi
  Bwf : Blo ≤ Bhi

/-- Membership in the admissible range Rℓ. -/
def Timeline.InRange (ℓ : Timeline) (x : ℝ) : Prop :=
InClosed x ℓ.Rlo ℓ.Rhi

/-- Clamp to bounds Bℓ. -/
def Timeline.clampB (ℓ : Timeline) (x : ℝ) : ℝ :=
clamp ℓ.Blo ℓ.Bhi x

/- =========================
   Tasks and impacts (AST-level objects)
   ========================= -/

/-- When an impact is active. -/
inductive When where
  | pre | maint | post
deriving DecidableEq, Repr

/-- Operator: assignment (=), cumulative (+), rate (~). -/
inductive Op where
  | assign  -- "="
  | add     -- "+"
  | rate    -- "~"
deriving DecidableEq, Repr

/--
Impact AST:
  refers to a timeline by identifier (TimelineId),
  has when, op, and numeric parameter a.
-/
structure Impact where
  tl   : TimelineId
  when : When
  op   : Op
  a    : ℝ

/--
A Task as a tuple (AST-level):
  startR/endR/durR are closed real intervals (lo,hi).
  after/containedin are sets of task identifiers.
  pre/inv/post are predicates over (schedule, trace, time).
  imp is a finite set/list of impacts.
-/
structure Task (T : ℕ) (L : Set TimelineId) where
  id            : TaskId
  startRlo      : ℝ
  startRhi      : ℝ
  endRlo        : ℝ
  endRhi        : ℝ
  durRlo        : ℝ
  durRhi        : ℝ
  after         : Set TaskId
  containedin   : Set TaskId
  pre           : (TaskId → (Time T × Time T)) → Trace T L → Time T → Prop
  inv           : (TaskId → (Time T × Time T)) → Trace T L → Time T → Prop
  post          : (TaskId → (Time T × Time T)) → Trace T L → Time T → Prop
  impacts       : List Impact
  /-- well-formedness of interval endpoints -/
  startRwf : startRlo ≤ startRhi
  endRwf   : endRlo ≤ endRhi
  durRwf   : durRlo ≤ durRhi

/- =========================
   TaskNet (AST-level object)
   ========================= -/

structure TaskNet where
  T : ℕ
  /-- timeline identifiers (domain of the model) -/
  L : Set TimelineId
  /-- task identifiers -/
  K : Set TaskId
  /-- lookup tables from identifiers to objects -/
  timeline : TimelineId → Timeline
  task     : TaskId → Task T L
  /-- initial-state constraint over states at time 0 -/
  I : State L → Prop
  /-- temporal constraint ψ and property φ (over schedule+trace) -/
  ψ : (TaskId → (Time T × Time T)) → Trace T L → Prop
  φ : (TaskId → (Time T × Time T)) → Trace T L → Prop

/- =========================
   Schedules and fitting
   ========================= -/

/-- A schedule maps each task id to (start,end). -/
abbrev Schedule (TN : TaskNet) := TaskId → (Time TN.T × Time TN.T)

/-- Real-interval membership for Nat-valued time points, via coercion. -/
def timeIn (t : ℕ) (lo hi : ℝ) : Prop := InClosed (t : ℝ) lo hi

/--
A schedule is fitting iff it satisfies:
  0 ≤ s < e ≤ T
  s ∈ startR, e ∈ endR, (e-s) ∈ durR
  after constraints: e(k') < s(k)
  containedin constraints: s(k') ≤ s(k) ≤ e(k) ≤ e(k')
-/
def Fitting (TN : TaskNet) (π : Schedule TN) : Prop :=
  ∀ k : TaskId,
    k ∈ TN.K →
    let tk := TN.task k
    let s  := (π k).1.1
    let e  := (π k).2.1
    (s < e) ∧
    timeIn s tk.startRlo tk.startRhi ∧
    timeIn e tk.endRlo tk.endRhi ∧
    timeIn (e - s) tk.durRlo tk.durRhi ∧
    (∀ k' : TaskId, k' ∈ tk.after → (π k').2.1 < (π k).1.1) ∧
    (∀ k' : TaskId, k' ∈ tk.containedin →
        (π k').1.1 ≤ (π k).1.1 ∧ (π k).1.1 ≤ (π k).2.1 ∧ (π k).2.1 ≤ (π k').2.1)

/- =========================
   Impact denotation
   ========================= -/

/--
Additive impact contribution ⟦i⟧(t) : Time → ℝ,
parameterized by the owning task id k (because the rule uses s_k/e_k).
-/
def impactDenote (TN : TaskNet) (π : Schedule TN) (k : TaskId) (i : Impact) : Time TN.T → ℝ :=
  fun t =>
    let s : ℕ := (π k).1.1
    let e : ℕ := (π k).2.1
    let tt : ℕ := t.1
    match i.op, i.when with
    | Op.add,  When.pre   => if tt = s then i.a else 0
    | Op.add,  When.post  => if tt = e then i.a else 0
    | Op.add,  When.maint => if tt = s then i.a else if tt = e then -i.a else 0
    | Op.rate, When.pre   => if s ≤ tt then i.a else 0
    | Op.rate, When.post  => if e ≤ tt then i.a else 0
    | Op.rate, When.maint => if s ≤ tt ∧ tt < e then i.a else 0
    | Op.assign, _        => 0

/--
Assignment map Aπ : (timelineId,time) ↦ assigned value.
We represent it as a relation (Prop) plus a functional consistency condition.
-/
def AssignRel (TN : TaskNet) (π : Schedule TN) : TimelineId → Time TN.T → ℝ → Prop :=
  fun ℓ t a =>
    ∃ k : TaskId,
      k ∈ TN.K ∧
      ∃ i ∈ (TN.task k).impacts,
        i.tl = ℓ ∧ i.op = Op.assign ∧ i.a = a ∧
        ((i.when = When.pre  ∧ t.1 = (π k).1.1) ∨
         (i.when = When.post ∧ t.1 = (π k).2.1))

/-- No conflicting assignments: uniqueness of assigned value at (ℓ,t). -/
def AssignConsistent (TN : TaskNet) (π : Schedule TN) : Prop :=
  ∀ ℓ t a₁ a₂,
    AssignRel TN π ℓ t a₁ →
    AssignRel TN π ℓ t a₂ →
    a₁ = a₂

/- =========================
   Execution trace
   ========================= -/

/--
Base additive evolution for one timeline id ℓ:
  σ⁺(t) = clamp_B( σ0(ℓ) + Σ_{τ=0}^{t-1} Σ_{i∈Iℓ} ⟦i⟧(τ) )
where Iℓ ranges over all additive impacts targeting ℓ across all tasks.
-/
def baseValue (TN : TaskNet) (π : Schedule TN) (σ0 : State TN.L) (ℓid : TimelineId) : Time TN.T → ℝ :=
  fun t =>
    let ℓ := TN.timeline ℓid
    let sumImp : ℝ :=
      (Finset.range t.1).sum (fun n =>
        -- n is τ
        let τ : Time TN.T := ⟨n, Nat.le_trans (Nat.le_of_lt_succ (Nat.lt_succ_self n)) t.2⟩
        -- sum over all tasks and their impacts that target ℓid
        (Finset.univ.filter (fun (k : TaskId) => Decidable.decEq True True)).sum (fun k =>
          -- we cannot finitize TaskId in general; treat this as schematic
          0))
    -- NOTE: the above "sum over tasks" is schematic because TaskId is not finite in Lean by default.
    -- In a real formalization you’d represent K as a finite type or Finset.
    ℓ.clampB (σ0 ℓid + sumImp)

/-
Pragmatic alternative (and what you likely want in Lean):
represent K as a Finset TaskId and impacts as a list; then sums are concrete.
If you want, I’ll rewrite TN with Finset-based K and L to make baseValue definitional.
-/

/--
Execution trace σπ,σ0 is defined pointwise:
  if there is an assignment at (ℓ,t), that value overrides;
  otherwise use σ⁺.
-/
def Exec (TN : TaskNet) (π : Schedule TN) (σ0 : State TN.L) : Trace TN.T TN.L :=
  fun t =>
    fun ℓ =>
      -- override if assigned; otherwise base
      if h : (∃ a, AssignRel TN π ℓ t a) then
        Classical.choose h
      else
        baseValue TN π σ0 ℓ t

/- =========================
   Satisfaction, Sat / Valid / Safe
   ========================= -/

/--
Sat(TN, π, σ0) : π fitting, σ0 satisfies I, ranges hold, task pre/inv/post hold,
and ψ holds on the execution trace.
-/
def Sat (TN : TaskNet) (π : Schedule TN) (σ0 : State TN.L) : Prop :=
  Fitting TN π ∧
  TN.I σ0 ∧
  AssignConsistent TN π ∧
  (∀ ℓid t, (TN.timeline ℓid).InRange ((Exec TN π σ0 t) ℓid)) ∧
  (∀ k : TaskId, k ∈ TN.K →
      let tk := TN.task k
      let s  : Time TN.T := (π k).1
      let e  : Time TN.T := (π k).2
      tk.pre  π (Exec TN π σ0) s ∧
      tk.post π (Exec TN π σ0) e ∧
      (∀ t : Time TN.T, s.1 < t.1 ∧ t.1 < e.1 → tk.inv π (Exec TN π σ0) t)) ∧
  TN.ψ π (Exec TN π σ0)

/-- Valid(TN) : there exists an initial state and schedule yielding Sat. -/
def Valid (TN : TaskNet) : Prop :=
  ∃ π σ0, Sat TN π σ0

/-- Safe(TN) : for all constrained executions, φ holds at time 0 (encoded in φ itself). -/
def Safe (TN : TaskNet) : Prop :=
  ∀ π σ0, Sat TN π σ0 → TN.φ π (Exec TN π σ0)

end TaskNet
