---
sidebar_position: 0
sidebar_label: "Introduction"
slug: /
---

# TaskSAT

TaskSAT is a domain-specific language and tool for modeling and verifying task scheduling problems with rich temporal and resource constraints. The system combines a declarative specification language with SMT-based automated reasoning using Z3. TaskSAT supports multiple types of state variables that model discrete states, Boolean flags, and continuous resources with complex dynamics including rate-based evolution. Tasks specify preconditions, invariants, postconditions, and resource impacts (assignments, deltas, cumulative rates, rate assignments) that occur at boundaries or during execution. The verifier encodes specifications into quantifier-free SMT formulas using zone-based time discretization, supporting both satisfiability checking and optimization. Users can express temporal properties using LTL-style operators (always, eventually, until, since) that are verified alongside scheduling constraints.

TaskSAT can be applied to scheduling problems in autonomous systems, such as spacecraft and rover operations.

## Key Features

- **Auto-instantiation**: Automatically creates task instances from taskdefs when type-level dependencies exist, reducing manual specification (e.g., 2 downlinks → 6 tasks total with thermal management)
- **Sequence construct**: Concise syntax for sequential task ordering - `sequence [t1, t2, t3]` desugars to pairwise constraints
- **Automatic visualization**: Gantt charts, timelines, and JSON schedules generated automatically during verification
- **Web UI**: Browse tasknets, view schedules, UNSAT core analysis with raw SMT formulas, console output display, bulk deletion
- **Property verification**: Comprehensive error traces for violated temporal properties with violation zone identification
- **Rich state modeling**: Rate-based continuous resources, discrete states, Boolean flags
- **Temporal logic**: LTL-style properties (always, eventually, until, since) for verification
- **Zone-based encoding**: Efficient SMT encoding using time discretization at task boundaries
- **Optimization**: Find schedules that minimize/maximize objectives (battery usage, priority-weighted completion)
- **MEXEC semantics**: Based on JPL's MEXEC scheduling system

## System Architecture

TaskSAT's verification pipeline: a `.tn` spec is parsed into an AST, auto-instantiated and validated, then encoded as a Z3 SMT formula and solved for a schedule (or a proof of infeasibility).

<img
  src="/img/architecture.png"
  alt="TaskSAT verification pipeline: TaskNet spec → Parser → AST → Transform + Wellformedness → Validated AST → SMT Encoder → Z3 Formula → Z3 Solver → Schedule/UNSAT"
  style="max-width: 100%; width: 900px; display: block; margin: 0 auto;"
/>

<p style="text-align: center; font-size: 0.85em; opacity: 0.75;">
  Diagram source: <a href="https://github.com/nasa-jpl/tasksat/blob/main/doc/architecture.dot"><code>doc/architecture.dot</code></a>.
  Regenerate with <code>dot -Tpng -Gdpi=150 doc/architecture.dot -o doc/architecture.png</code>.
</p>

## Generated Files

TaskSAT organizes all generated files under `.tasksat/` directories:

```
project/
  tasknet.tn
  .tasksat/
    transformed/      # Auto-instantiated tasknets (written automatically when auto-instantiation occurs)
    schedules/        # Generated schedules and visualizations
      <tasknet_name>/
        <timestamp>/  # e.g., 2026-06-10_14-30-15
          metadata.json       # Verification metadata
          schedule.json       # Valid schedule
          timeline.json       # Timeline evolution
          gantt.png           # Gantt chart
          timeline.png        # Timeline visualization
          properties.json     # Property verification results
          unsat_core.json     # UNSAT core analysis (if UNSAT)
          console_output.txt  # Full console output
          errors/             # Error traces for violated properties
            <prop>_schedule.json
            <prop>_timeline.json
            <prop>_timeline.png
```

The `.tasksat/` directory is automatically added to `.gitignore`.

**Transformed tasknets:** When the SMT-based verifier auto-instantiates task instances from taskdefs, it automatically writes the expanded tasknet to `.tasksat/transformed/<filename>_transformed.tn`. This makes it easy to inspect what tasks were created. Use `--transform-only` to generate this file without running verification.

**Web UI:** Start the web interface to browse verification results:

```bash
./start_web.sh
# Open browser to http://localhost:5001
```

The web UI provides:

- Browse all verification results with status indicators
- View Gantt charts and timeline visualizations
- **UNSAT core analysis** with three levels:
  1. Human-readable conflict explanations and suggestions
  2. TaskSAT constraint labels
  3. Raw Z3 SMT formulas (S-expressions)
- **Console output** - Full verifier text output
- Property verification results with error traces
- Open, create, and verify tasknets directly in the browser (edits are saved back to the original file)
- Add a `.tn` file to the list without running it, and cancel a running verification
- **Bulk deletion** of verification reports (source files preserved)

## Running Examples in this Documentation

All examples in this documentation are organized in:

```
tests/tasknet_files/examples
```

Users can run any example, say `rover1.tn` in this documentation as follows:

```
python src/smt/tasknet_verifier.py tests/tasknet_files/examples/rover1.tn --mode satisfy
```

If `--mode ...` is left out it will run in the default `optimize` mode.

## The Role of MEXEC

TaskSAT was created in order to explore an alternative method for analysing and verifying tasknets, which form the inputs to JPL's [MEXEC](https://ai.jpl.nasa.gov/public/projects/mexec/) scheduling system. The constructs of the TaskSAT language are designed as close as possible to the MEXEC tasknet "concepts", with a semantics as close as possible to the perceived semantics of MEXEC tasknets. However, it is not a precise match since (a) on occasions the exact semantics of MEXEC has not been clear to us, (b) we have added some new language features, most importantly temporal logic constraints, (c) the scheduling algorithm is different, based on constraint solving, (d) we have added a verification step, and finally (e) we defined a DSL (Domain-Specific Language) for defining tasknets.

## Next Steps

- **[Getting Started](getting-started/installation.md)** — Quick installation and your first TaskNet in minutes
- **[Tutorial](getting-started/tutorial.md)** — In-depth walkthrough of concepts using an example
- **[Manual](reference/manual.md)** — Complete language reference
- **[Grammar](reference/grammar.md)** — Formal grammar and syntax reference
- **[SMT Encoding](theory/smt-encoding.md)** — Theory behind the SMT encoding
