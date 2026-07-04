# CEGIS for Realizability — Formal Summary

## Problem

Let $\Phi(x, s, h)$ be a quantifier-free formula over a theory $T$ (mixed
integer/real arithmetic), with disjoint variable vectors:

- $x$ — **initial-state variables** (timeline values at time 0),
- $s$ — **schedule variables** (task start/end times, zone boundaries, inclusion booleans),
- $h$ — **helper variables** (timeline values at later zones; functionally
  determined by $x, s$ through $\Phi$).

Let $\mathit{Init}(x)$ be a quantifier-free formula (the initial region).
**Decide:**

$$\mathcal{R} \;\equiv\; \forall x\, .\ \mathit{Init}(x) \rightarrow \exists s, h\, .\ \Phi(x, s, h)$$

$\Phi$ contains nonlinear terms only of the form $r \cdot (z' - z)$ with
$z, z' \in s$; hence $\Phi[s \mapsto c]$ is **linear** for any constant vector $c$.

## Definitions

For a constant vector $\sigma$ (a *schedule skeleton*), define its **coverage**:

$$\mathit{Cov}(\sigma)(x) \;\equiv\; \exists h\, .\ \Phi(x, \sigma, h)$$

a quantified **linear** formula in $x$. Note $\mathit{Cov}(\sigma)(x)$ implies
$\exists s,h.\ \Phi(x,s,h)$ (witness $s := \sigma$).

## Algorithm

Maintain a set $B$ of blocking formulas, initially $\emptyset$.

$$
\begin{array}{ll}
1. & \text{if } \mathit{Init}(x) \wedge \bigwedge_{\beta \in B} \neg\beta(x)
     \text{ is } T\text{-unsat} \;\Rightarrow\; \textbf{return HOLDS} \\
2. & \text{else take a model } x^* \\
3. & \text{if } \Phi(x^*, s, h) \text{ is } T\text{-unsat}
     \;\Rightarrow\; \textbf{return VIOLATED}(x^*) \\
4. & \text{else take a model } (\sigma, \eta);\quad
     B := B \cup \{\mathit{Cov}(\sigma)\};\quad \text{goto } 1
\end{array}
$$

Steps 1 and 3 are the only solver calls: step 3 is quantifier-free; step 1 is
quantifier-free ground plus quantified *linear* clauses (decidable). Resource
bounds (iteration cap, wall clock) yield **UNKNOWN** on exhaustion.

## Correctness

**Lemma 1 (soundness of VIOLATED).** If step 3 is unsat, then
$\neg\exists s,h.\ \Phi(x^*,s,h)$ and $\mathit{Init}(x^*)$ (from step 2), so
$x^*$ falsifies $\mathcal{R}$. ∎

**Lemma 2 (soundness of HOLDS).** Invariant: every $\beta \in B$ equals
$\mathit{Cov}(\sigma)$ for some skeleton $\sigma$, and
$\mathit{Cov}(\sigma)(x) \rightarrow \exists s,h.\Phi$. If step 1 is unsat, then
$\mathit{Init}(x) \rightarrow \bigvee_{\beta\in B} \beta(x)$ is $T$-valid, hence
every $x \in \mathit{Init}$ satisfies some $\mathit{Cov}(\sigma)$, hence
$\mathcal{R}$ holds. The set $\{\sigma_i\}$ is a finite piecewise Skolem
witness for $\exists s$. ∎

**Lemma 3 (progress).** In step 4, $(x^*, \sigma, \eta) \models \Phi$, so
$\eta$ witnesses $\mathit{Cov}(\sigma)(x^*)$; therefore $x^*$ is excluded by
the new clause and no candidate repeats. ∎

**Non-termination.** Over $\mathbb{R}$, $\mathit{Init}$ may require unboundedly
many coverage regions; hence the procedure is a sound **semi-decision
procedure**, made total by resource bounds (returning UNKNOWN). Each
$\mathit{Cov}(\sigma)$ is a full-dimensional polyhedral region (not a point),
which is what makes convergence typical in practice.

## Why not a direct quantified query

$\neg\mathcal{R}$ is $\exists x \forall s, h\, .\ \neg\Phi$ — a quantifier
alternation over hundreds of variables of a **nonlinear** mixed formula; no
decision procedure exists for this fragment and solvers typically return
unknown. The algorithm above poses only (i) quantifier-free queries and
(ii) quantified **linear** queries, obtained by instantiating exactly the
variables ($s$) that occur in nonlinear terms. Leaving $h$ quantified inside
$\mathit{Cov}$ (rather than instantiating it) is essential: $h$ depends on
$x$, so instantiating it would shrink coverage to the single point $x^*$.

## Context

The loop is an instance of counterexample-guided synthesis (CEGIS,
Solar-Lezama et al. 2006) in its exists-forall SMT form (CEGQI, Reynolds et
al. 2015); the partial instantiation of step 4 is model-based projection.
Implementation: [tasknet_realizability.py](../src/smt/tasknet_realizability.py);
encoding details: [smt-encoding.md](smt-encoding.md) §7.4.
