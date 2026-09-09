---
sidebar_position: 0
sidebar_label: "Introduction"
slug: /
---

# TaskSAT

TaskSAT is a domain-specific language and tool for modeling and verifying task scheduling problems with rich temporal and resource constraints. The system combines a declarative specification language with SMT-based automated reasoning using Z3. TaskSAT supports multiple types of state variables that model discrete states, Boolean flags, and continuous resources with complex dynamics including rate-based evolution. Tasks specify preconditions, invariants, postconditions, and resource impacts (assignments, deltas, cumulative rates, rate assignments) that occur at boundaries or during execution. The verifier encodes specifications into quantifier-free SMT formulas using zone-based time discretization, supporting both satisfiability checking and optimization. Users can express temporal properties using LTL-style operators (always, eventually, until, since) that are verified alongside scheduling constraints.

TaskSAT can be applied to scheduling problems in autonomous systems, such as spacecraft and rover operations.

## What TaskSAT checks

A specification says what the tasks are, what they need, and what they consume. TaskSAT
answers four questions about it, differing only in how they quantify over initial states
`i` and schedules `s`. Write `valid(i, s)` for "every constraint holds".

| | question | formally |
|---|---|---|
| **Validity** (∃∃) | Is there any way to run this? This is the **planning problem** — a positive answer *is* the schedule. | `∃i ∃s . valid(i,s)` |
| **Property verification** (∀∀) | Can it go wrong? Checked against *every* valid schedule, not just the one found above. Properties use LTL-style operators (`always`, `eventually`, `until`, `since`). | `∀i ∀s . valid(i,s) ⇒ sat(i,s,φ)` |
| **Realizability** (∀∃) | Does a schedule exist for *every* initial state the spec allows? Validity only asks for one. | `∀i ∃s . valid(i,s)` |
| **Compositional** | Does it hold for *any* number of repetitions of a repeating block `S`? You supply a predicate `P` on the state; TaskSAT verifies once that one repetition preserves it, at a cost independent of N. Needs both **property verification** and **realizability** over that `P`: the former alone is vacuously true wherever no schedule exists. | `{P} S {P} ⇒ ∀N . {P} Sᴺ {P}` |

## System Architecture

TaskSAT's verification pipeline: a `.tn` spec is parsed into an AST, auto-instantiated and validated, then encoded as a Z3 SMT formula and solved for a schedule (or a proof of infeasibility).

![TaskSAT verification pipeline: TaskNet spec → Parser → AST → Transform + Wellformedness → Validated AST → SMT Encoder → Z3 Formula → Z3 Solver → Schedule/UNSAT](/img/architecture.png)

## The Role of MEXEC

TaskSAT was created in order to explore a method for analysing and verifying tasknets, which form the inputs to JPL's [MEXEC](https://ai.jpl.nasa.gov/public/projects/mexec/) scheduling system. The constructs of the TaskSAT language are designed as close as possible to the MEXEC tasknet "concepts", with a semantics as close as possible to the perceived semantics of MEXEC tasknets. We have added some new language features, most importantly temporal logic constraints, (c) the scheduling algorithm is different, based on constraint solving, (d) we have added a verification step, and finally (e) we defined a DSL (Domain-Specific Language) for defining tasknets.
