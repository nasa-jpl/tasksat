# CEGIS for Realizability — Formal Summary

## Problem

Let Φ(x, s, h) be a quantifier-free formula over a theory T (mixed
integer/real arithmetic). *T-sat / T-unsat* below means satisfiable /
unsatisfiable **modulo T**, i.e. with +, ·, ≤ interpreted as actual
arithmetic — what an SMT solver decides. The variables come in three
disjoint vectors:

- **x** — initial-state variables (timeline values at time 0),
- **s** — schedule variables (task start/end times, zone boundaries, inclusion booleans),
- **h** — helper variables (timeline values at later zones; functionally
  determined by x, s through Φ).

Let Init(x) be a quantifier-free formula (the initial region). **Decide:**

>   𝓡  ≡  ∀x . Init(x) → ∃s, h . Φ(x, s, h)

Φ contains nonlinear terms only of the form r·(z′ − z) with z, z′ ∈ s;
hence Φ[s ↦ c] is **linear** for any constant vector c.

## Definitions

A **schedule skeleton** σ is a constant vector for s: concrete numbers for all
task start/end times and zone boundaries, and concrete booleans for all
optional/request inclusions — i.e. one fixed schedule, stripped of everything
else a model contains.

For a skeleton σ, define its **coverage**:

>   Cov(σ)(x)  ≡  ∃h . Φ(x, σ, h)

Cov(σ)(x) reads: *"the fixed schedule σ is valid when started from initial
state x."* It is Φ itself, partially evaluated at s := σ — so satisfying it
means every original constraint holds, by construction, not by testing.

Three remarks:

- **Why h stays quantified.** The helpers are functions of x (e.g.
  battery-after-task = x + 20). Substituting their model values, which
  belong to one particular x, would pin x to that single point; leaving them
  ∃-bound lets them track x, so Cov(σ) describes the full region σ handles.
- **Why it is linear.** Φ's only nonlinear terms are r·(z′ − z) with
  z, z′ ∈ s; under s := σ these become r·c. Quantified linear arithmetic is
  decidable, so Cov(σ) is cheap for the solver.
- **Soundness direction.** Cov(σ)(x) implies ∃s, h . Φ(x, s, h) (take
  s := σ): every covered x is schedulable. The converse is *not* claimed —
  an x outside Cov(σ) may be schedulable by a different skeleton; later
  iterations find it.

## Algorithm

Maintain a list of blocking formulas B = β₁, …, βₖ (initially empty), one per
skeleton found so far, each βᵢ = Cov(σᵢ).

Each iteration makes exactly two SAT (SMT) calls; each call's two outcomes
are handled together:

> **Call 1** — check Init(x) ∧ ¬β₁(x) ∧ … ∧ ¬βₖ(x):
> - T-unsat ⇒ **return HOLDS**
> - T-sat with model x★, i.e. Init(x★) ∧ ¬β₁(x★) ∧ … ∧ ¬βₖ(x★) true in T
>
> **Call 2** — check Φ(x★, s, h):
> - T-unsat ⇒ **return VIOLATED(x★)**
> - T-sat with model (σ, η), i.e. Φ(x★, σ, η) true in T
>   ⇒ add Cov(σ) to B; repeat from Call 1

Notation: x★, σ, η denote *concrete values* returned by the solver as a model
(satisfying assignment) — as opposed to x, s, h, which are variables. Call 1
asks for an initial state in Init not yet covered by any found skeleton;
Call 2 is the ordinary planning query pinned to x★.

Call 2 is quantifier-free; Call 1 is quantifier-free ground plus the
quantified *linear* clauses ¬βᵢ (decidable). Resource bounds (iteration cap,
wall clock) yield **UNKNOWN** on exhaustion.

## Correctness

**Lemma 1 (soundness of VIOLATED).** If Call 2 is unsat, then
¬∃s, h . Φ(x★, s, h), and Init(x★) holds (from Call 1's model), so x★
falsifies 𝓡. ∎

**Lemma 2 (soundness of HOLDS).** Invariant: every β ∈ B equals Cov(σ) for
some skeleton σ, and Cov(σ)(x) → ∃s, h . Φ. If Call 1 is unsat, then
Init(x) → ⋁ { β(x) : β ∈ B } is T-valid, hence every x ∈ Init satisfies some
Cov(σ), hence 𝓡 holds. The set {σ₁, …, σₖ} is a finite piecewise Skolem
witness for ∃s. ∎

**Lemma 3 (progress).** When Call 2 is sat, (x★, σ, η) ⊨ Φ, so η witnesses
Cov(σ)(x★); therefore x★ is excluded by the new clause and no candidate
repeats. ∎

**Non-termination.** Over ℝ, Init may require unboundedly many coverage
regions; hence the procedure is a sound **semi-decision procedure**, made
total by resource bounds (returning UNKNOWN). Each Cov(σ) is a
full-dimensional polyhedral region (not a point), which is what makes
convergence typical in practice.

## Why not a direct quantified query

¬𝓡 is ∃x ∀s, h . ¬Φ — a quantifier alternation over hundreds of variables of
a **nonlinear** mixed formula; no decision procedure exists for this fragment
and solvers typically return unknown. The algorithm above poses only
(i) quantifier-free queries and (ii) quantified **linear** queries, obtained
by instantiating exactly the variables (s) that occur in nonlinear terms.
Leaving h quantified inside Cov (rather than instantiating it) is essential:
h depends on x, so instantiating it would shrink coverage to the single
point x★.

## Context

The loop is an instance of counterexample-guided synthesis (CEGIS,
Solar-Lezama et al. 2006) in its exists-forall SMT form (CEGQI, Reynolds et
al. 2015); the partial instantiation after Call 2 is model-based projection.
Implementation: [tasknet_realizability.py](../src/smt/tasknet_realizability.py);
encoding details: [smt-encoding.md](smt-encoding.md) §7.4.
