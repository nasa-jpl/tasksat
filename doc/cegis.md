# CEGIS for Realizability — Formal Summary

## Problem

Let Φ(x, s, h) be a quantifier-free formula over a theory T (mixed
integer/real arithmetic), with disjoint variable vectors:

- **x** — initial-state variables (timeline values at time 0),
- **s** — schedule variables (task start/end times, zone boundaries, inclusion booleans),
- **h** — helper variables (timeline values at later zones; functionally
  determined by x, s through Φ).

Let Init(x) be a quantifier-free formula (the initial region). **Decide:**

>   𝓡  ≡  ∀x . Init(x) → ∃s, h . Φ(x, s, h)

Φ contains nonlinear terms only of the form r·(z′ − z) with z, z′ ∈ s;
hence Φ[s ↦ c] is **linear** for any constant vector c.

## Definitions

For a constant vector σ (a *schedule skeleton*), define its **coverage**:

>   Cov(σ)(x)  ≡  ∃h . Φ(x, σ, h)

a quantified **linear** formula in x. Note Cov(σ)(x) implies
∃s, h . Φ(x, s, h) (witness s := σ).

## Algorithm

Maintain a set B of blocking formulas, initially ∅.

> 1. if Init(x) ∧ ⋀ { ¬β(x) : β ∈ B } is T-unsat  ⇒  **return HOLDS**
> 2. else take a model x*
> 3. if Φ(x*, s, h) is T-unsat  ⇒  **return VIOLATED(x*)**
> 4. else take a model (σ, η);  B := B ∪ { Cov(σ) };  goto 1

Steps 1 and 3 are the only solver calls: step 3 is quantifier-free; step 1 is
quantifier-free ground plus quantified *linear* clauses (decidable). Resource
bounds (iteration cap, wall clock) yield **UNKNOWN** on exhaustion.

## Correctness

**Lemma 1 (soundness of VIOLATED).** If step 3 is unsat, then
¬∃s, h . Φ(x*, s, h), and Init(x*) holds (from step 2), so x* falsifies 𝓡. ∎

**Lemma 2 (soundness of HOLDS).** Invariant: every β ∈ B equals Cov(σ) for
some skeleton σ, and Cov(σ)(x) → ∃s, h . Φ. If step 1 is unsat, then
Init(x) → ⋁ { β(x) : β ∈ B } is T-valid, hence every x ∈ Init satisfies some
Cov(σ), hence 𝓡 holds. The set {σ₁, …, σₖ} is a finite piecewise Skolem
witness for ∃s. ∎

**Lemma 3 (progress).** In step 4, (x*, σ, η) ⊨ Φ, so η witnesses
Cov(σ)(x*); therefore x* is excluded by the new clause and no candidate
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
point x*.

## Context

The loop is an instance of counterexample-guided synthesis (CEGIS,
Solar-Lezama et al. 2006) in its exists-forall SMT form (CEGQI, Reynolds et
al. 2015); the partial instantiation of step 4 is model-based projection.
Implementation: [tasknet_realizability.py](../src/smt/tasknet_realizability.py);
encoding details: [smt-encoding.md](smt-encoding.md) §7.4.
