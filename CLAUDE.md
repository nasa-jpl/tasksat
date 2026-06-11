# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TaskSAT is a domain-specific language and tool for modeling and verifying task scheduling problems with rich temporal and resource constraints. It combines a declarative specification language with SMT-based automated reasoning using Z3.

**Key concepts:**
- **TaskNet (.tn files)**: DSL for specifying tasks, timelines, constraints, and temporal properties
- **SMT-based verification**: Encodes scheduling problems as quantifier-free SMT formulas solved by Z3
- **LLM-based scheduler**: Alternative approach for large tasknets (>20 tasks) using Claude + Lean validation
- **MEXEC semantics**: Based on JPL's MEXEC scheduling system

## Running TaskSAT

### Basic Commands

**Run SMT-based scheduler:**
```bash
# Default (optimize mode) - automatically generates Gantt chart and JSON
python src/smt/tasknet_verifier.py tasknet.tn

# Satisfy mode (find any valid schedule)
python src/smt/tasknet_verifier.py tasknet.tn --mode satisfy

# Generate transformed tasknet without verification (useful for inspecting auto-instantiation)
python src/smt/tasknet_verifier.py tasknet.tn --transform-only
```

**Note:** Gantt charts automatically saved to `.tasksat/schedules/<tasknet>_gantt.png` and schedule JSON to `.tasksat/schedules/<tasknet>_schedule.json`

**Note:** When auto-instantiation occurs, the transformed tasknet is automatically written to `.tasksat/transformed/<filename>_transformed.tn` for inspection. Use `--transform-only` to generate this file without running verification.

**Run LLM-based scheduler** (for large tasknets):
```bash
# Basic usage (requires JPL GenAI API access)
python3 jpl/tools/llm_scheduler.py tasknet.tn

# With mission-specific guidance
python3 jpl/tools/llm_scheduler.py tasknet.tn --guidance guidance.txt --max-attempts 20

# Disable auto-visualization
python3 jpl/tools/llm_scheduler.py tasknet.tn --no-visualize
```

**Visualize schedules:**
```bash
# SMT verifier: Gantt chart generated automatically during verification
python src/smt/tasknet_verifier.py tasknet.tn
# Output: .tasksat/schedules/<tasknet>_gantt.png
#         .tasksat/schedules/<tasknet>_schedule.json

# LLM scheduler: Create Gantt chart from schedule JSON (grouped by task type)
python3 jpl/tools/visualize_schedule.py schedule.json --grouped -o gantt.png

# Standalone: Create Gantt chart from schedule JSON
python src/smt/tasknet_gantt.py schedule.json output.png
```

**Web UI:**
```bash
# Start the web interface (browse tasknets, view schedules, property results)
python src/smt/tasknet_web.py

# Open browser to http://localhost:5000
# - Home page shows all tasknets with verification history
# - Click tasknet name to view detailed report
# - View Gantt charts, timelines, property verification results
# - Compare error traces with valid schedules side-by-side
```

### Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_verifier1.py

# Run with verbose output
pytest -v
```

### Building Lean Validator

The Lean validator is used by the LLM scheduler:

```bash
cd src/lean/TaskNetExec
lake build
lake exe tasknet-validate --tasknet tasknet.json --schedule schedule.json
```

## Architecture

### Two Scheduling Approaches

**1. SMT-based TaskSAT** (main approach, best for <20 tasks):
```
.tn file → Parser → AST → Transformations → Wellformedness → SMT Encoding → Z3 Solver → Schedule/UNSAT
```

**2. LLM-based Scheduler** (alternative, scales to 50+ tasks):
```
.tn file → Lean JSON → [LLM generates candidate → Lean validates] → Valid schedule
```

### Key Files and Pipeline

**SMT-based pipeline** (`src/smt/`):
- `tasknet_verifier.py` - Entry point
- `tasknet_parser.py` - PLY-based parser (.tn → AST)
- `tasknet_ast.py` - AST node definitions
- `tasknet_transforms.py` - **Critical**: AST transformation pipeline
- `tasknet_wellformedness.py` - Semantic validation
- `tasknet_smt.py` - SMT encoding (zone-based discretization)

**Transformation pipeline** (`tasknet_transforms.py`):
```python
def apply_transforms(tn):
    tn = desugar_active_predicate(tn)           # active(T) → __T_active = true
    tn = inject_task_state_timelines(tn)        # Auto-create __T_active timelines
    tn = reclassify_constraints(tn)             # Fix after/containedin categorization
    tn = instantiate_from_definitions(tn)       # Auto-create task instances from taskdefs
    tn = reclassify_constraints(tn)             # Reclassify again after instantiation
    # Note: link_auto_instances was removed - SMT encoder resolves at encoding time
    return tn, auto_instantiation_occurred      # Returns (TaskNet, bool)
```

**LLM-based pipeline** (`jpl/tools/`):
- `llm_scheduler.py` - Entry point, orchestrates generate-validate loop
- `lean_converter.py` - Converts .tn to Lean JSON format
- `visualize_schedule.py` - Creates Gantt charts
- Lean validator: `src/lean/TaskNetExec/` (compiled separately)

### Auto-Instantiation

**Problem**: Tasks can reference taskdefs via `after`/`containedin` but taskdefs are templates, not instances.

**Solution**: `instantiate_from_definitions()` transformation automatically creates task instances from taskdefs when:
- A task instance has type-level dependencies (after/containedin to a taskdef)
- No instances of that taskdef exist in the original tasknet

**Behavior**:
- Creates one instance per dependent task (not one per taskdef)
- Naming: `{taskdef}_auto_0`, `{taskdef}_auto_1`, etc.
- No cascade: only direct dependencies are instantiated
- Only if user provided zero instances (if user provided any, they manage instances manually)
- **Auto-writes transformed file**: When auto-instantiation occurs, the expanded tasknet is automatically written to `.tasksat/transformed/<name>_transformed.tn`

**Resolution**: The SMT encoder resolves inherited type-level dependencies to specific auto-instances at encoding time:
- Task instances inherit type-level constraints from their taskdefs
- When encoding, the encoder checks if a specific auto-instance exists for that task
- If found, uses that specific instance; otherwise uses OR semantics over all available instances
- This avoids duplicate constraints and maintains clean inheritance

**Example**:
```
taskdef comm_preheat { ... }
task downlink1 { after comm_preheat; }
task downlink2 { after comm_preheat; }

→ Creates: comm_preheat_auto_0, comm_preheat_auto_1
→ downlink1 inherits "after comm_preheat" which resolves to comm_preheat_auto_0
→ downlink2 inherits "after comm_preheat" which resolves to comm_preheat_auto_1
```

### Repository Structure

```
tasksat/
├── src/
│   ├── smt/          # Python SMT-based verifier
│   └── lean/         # Lean validator (for LLM scheduler)
├── jpl/              # JPL-internal code (LLM scheduler, MEXEC)
│   ├── tools/        # LLM scheduler, converters, visualizers
│   ├── doc/          # LLM scheduler documentation
│   └── mexec/        # MEXEC tasknets and guidance files
├── tests/            # Pytest tests
│   └── tasknet_files/  # Test .tn files
└── doc/              # Documentation (getting-started, tutorial, manual)
```

## Working with Branches

- **main** - Public repository (github.com/nasa-jpl/tasksat)
- **jpl-internal** - Internal repository (github.jpl.nasa.gov/pass/tasksat)
  - Contains jpl/ folder with LLM scheduler and JPL-specific code
  - Periodically merged to main

**Remote setup:**
```bash
git remote -v
# origin: github.com/nasa-jpl/tasksat (public)
# internal: github.jpl.nasa.gov/pass/tasksat (JPL-internal)
```

## Key Design Decisions

### Task Kinds
- `DEFINITION` - Template (taskdef), not scheduled
- `INSTANCE` - Required task, must be scheduled
- `OPTIONAL` - Included only if needed (minimized by optimizer)
- `REQUEST` - Optional but desirable (maximized by optimizer)

### Constraint Types
- **Instance-level**: Reference specific task IDs (e.g., `after task1`)
- **Type-level**: Reference taskdef IDs (e.g., `after TaskDef1`)
  - Existential semantics: need at least one instance of the taskdef

### SMT Encoding
- **Zone-based time discretization**: Time divided into zones at task boundaries
- **State evolution**: Checked at zone boundaries, not continuously
- **Invariants**: Checked at (s, e] not [s, e] (critical for atomic pattern)

### LLM Scheduler Semantics
- **MEXEC dynamic instances**: LLM creates task instances from taskdefs (planning + scheduling)
- **Guidance files**: Natural language mission-specific requirements
- **Validation**: Polynomial-time check vs NP-hard search

## Recent Improvements (2026)

### Web UI (June 2026)
Added Flask-based web interface for browsing tasknets and viewing verification results:

**Features:**
- Browse all tasknets with verification history
- View detailed verification reports with Gantt charts and timelines
- Property verification results with error traces
- Side-by-side comparison of valid schedules vs counterexamples
- Responsive design with interactive visualizations

**Usage:**
```bash
python src/smt/tasknet_web.py
# Open browser to http://localhost:5000
```

**Output structure:**
```
.tasksat/schedules/
└── <tasknet_name>/
    └── <timestamp>/          # e.g., 2026-06-10_14-30-15
        ├── metadata.json     # Verification metadata
        ├── schedule.json     # Valid schedule
        ├── timeline.json     # Timeline evolution data
        ├── gantt.png         # Gantt chart
        ├── timeline.png      # Timeline visualization
        ├── properties.json   # Property verification summary
        └── errors/           # Error traces for violated properties
            ├── <prop>_schedule.json
            ├── <prop>_timeline.json
            └── <prop>_timeline.png
```

### Property Verification Enhancements (June 2026)
Comprehensive property verification reporting with error traces:

**Features:**
- Per-property verification results (holds/violated/unknown)
- Violation zone identification for `always` formulas
- Error trace generation for violated properties
- Timeline visualizations highlighting violation zones
- Timing breakdown per property

**Output format** (`properties.json`):
```json
[
  {
    "name": "battery_safe",
    "status": "violated",
    "duration_sec": 0.027,
    "formula": "always (battery >= 20.0)",
    "violation_zones": [0, 2, 4]
  },
  {
    "name": "battery_ok",
    "status": "holds",
    "duration_sec": 0.006,
    "formula": "always (battery >= 0.0)"
  }
]
```

**Error traces** (when property violated):
- Counterexample schedule showing violation
- Timeline with violation zones highlighted in red
- Side-by-side comparison with valid schedule in web UI

### Schedule Visualization (June 2026)
SMT verifier now **automatically generates** Gantt charts and JSON schedules:
```bash
# Verification automatically creates visualization and JSON
python src/smt/tasknet_verifier.py tasknet.tn

# Output files in .tasksat/schedules/<tasknet>/<timestamp>/:
#   - gantt.png           # Visual Gantt chart
#   - schedule.json       # Machine-readable schedule
#   - timeline.png        # Timeline evolution
#   - properties.json     # Property verification results
```

**Standalone tool** creates Gantt charts from schedule JSON:
```bash
# Explicit output path
python src/smt/tasknet_gantt.py schedule.json output.png

# Auto-generate output filename
python src/smt/tasknet_gantt.py schedule.json
```

**JSON format**: Simple dict mapping task_id → [start, end]:
```json
{
  "task1": [10, 20],
  "task2": [30, 40]
}
```

**Also fixed:** `tasknet_visualize.py` now works correctly (fixed import errors for `ImpactRateCumulative` and `ImpactRateAssignment`).

### Duplicate Property Name Validation (June 2026)
The wellformedness checker now detects duplicate constraint and property names:
```
constraints {
  prop order1: battery >= 30.0;
  prop order1: battery >= 40.0;  // Error: Duplicate constraint name
}

properties {
  prop check1: battery >= 20.0;
  prop check1: battery >= 10.0;  // Error: Duplicate property name
}
```
Helps catch copy-paste errors and ensures property names are unique within their scope.

### Empty Blocks Allowed (June 2026)
All block types can now be empty, useful for incremental development:
```
task t1 {
  constraints { }      // empty constraints
  impacts { }          // empty impacts
  constraints {
    pre { }            // empty pre/inv/post
    inv { }
    post { }
  }
  impacts {
    pre { }            // empty impact groups
    maint { }
    post { }
  }
}

constraints { }        // empty top-level constraints
properties { }         // empty properties
```

### Implies Keyword (June 2026)
Added support for `implies` keyword as an alternative to `->` for implication in temporal logic formulas:
```
properties {
  # Both syntaxes are equivalent
  prop arrow: battery >= 40.0 -> battery >= 30.0;
  prop keyword: battery >= 40.0 implies battery >= 30.0;
}
```
More readable for users familiar with logical notation. Both syntaxes can be mixed in the same file.

### Sequence Construct (June 2026)
Added `sequence [task1, task2, ...]` syntax for sequential task ordering:
```
constraints {
  prop ordering: sequence [preheat_0, downlink_0, preheat_1, downlink_1];
}
```
Desugars to pairwise `.end <= .start` constraints. More concise and less error-prone than manual ordering constraints.

### Comment Syntax (June 2026)
Both `#` and `//` are supported for line comments:
```
# Hash-style comment
// C-style comment (useful for block commenting with Cmd+/ in editors)
```

### Time Variable and Task Boundaries (June 2026)
Added `time` variable and `task.start`/`task.end` references for more efficient temporal constraints:

```
constraints {
  # Task ordering without active() - more efficient!
  prop order: T1.start >= T2.end;
  
  # Time windows
  prop early: task1.start < 100;
  
  # Current time comparisons
  prop before_task: always (time < task1.start -> battery > 50.0);
}
```

**Key semantics:**
- `time`, `task.start`, `task.end` are constants (Z3 Int variables), not functions of time
- More efficient than `active()` - no additional timelines created
- **Conditional on optional/request tasks**: `optional_task.start >= X` evaluates to `true` if `optional_task` is not scheduled
- This matches `active()` semantics: doesn't force optional tasks to be scheduled
- Use for ordering; use `active()` for "during execution" checks

### Temporal Logic Constants (June 2026)
Added `true` and `false` constants to temporal logic formulas:
```
properties {
  prop always_true: always true;
  prop never_false: always (not false);
  prop conditional: true -> (battery >= 0.0);
}
```

### Auto-Write Transformed Files (June 2026)
When auto-instantiation creates task instances, the verifier automatically writes the expanded tasknet to `.tasksat/transformed/<name>_transformed.tn`. Use `--transform-only` to generate this file without running verification.

### Fixed Auto-Instance Resolution (June 2026)
Fixed duplicate constraint bug in auto-instantiation:
- **Problem**: Adding explicit instance-level constraints conflicted with inherited type-level constraints
- **Solution**: SMT encoder now resolves inherited type-level dependencies to specific auto-instances at encoding time
- **Result**: Clean inheritance without duplicate constraints

### XML to TaskSAT Converter Improvements (June 2026)
- Optional output path: `python jpl/mexec/xml_to_tasksat.py input.xml` (defaults to `.tasksat/tn/`)
- Organized output: Converted files go to `.tasksat/tn/`, transformed files to `.tasksat/transformed/`
- Avoids nested `.tasksat/.tasksat/` directories

## Common Pitfalls

1. **Invariant timing**: TaskSAT checks invariants at (start, end], not [start, end]. PRE impacts at start must take effect before invariants are checked.

2. **Type-level constraints**: When a task references a taskdef (not an instance), auto-instantiation will create instances. Understand when this happens vs when to manually create instances.

3. **Battery SOC ceiling**: If initial value equals upper bound (e.g., initial=95, inv [0, 95]), recharging after t=0 is impossible. Use initial < upper bound.

4. **Atomic timeline maint impacts**: `maint { flag += 1 }` raises flag at task start, lowers at end automatically.

5. **Numeric equality on rate timelines**: The syntax `battery = 50.0` is interpreted as state equality (for state timelines with numeric state names like "0", "1"). For numeric equality on rate/cumulative timelines, use range syntax: `battery >= 50.0` and `battery <= 50.0`, or use `battery in [50.0, 50.0]`.

6. **LLM scheduler requires JPL GenAI API**: The genai_api package must be installed and authenticated. Look for it at ~/genai_api or set GENAI_API_PATH.

7. **Task boundary efficiency**: Use `task.start`/`task.end` instead of `active(task)` for ordering constraints. The former is more efficient (no timeline creation) and has clearer semantics for specifying task orderings.

## Dependencies

**Python:**
- z3-solver - SMT solver
- ply - Parser generator
- matplotlib - Visualization
- pytest - Testing
- requests - HTTP (for LLM scheduler)

**Lean:**
- Lean 4 toolchain
- lake - Lean build tool

**JPL GenAI API** (for LLM scheduler):
- Internal JPL package at ~/genai_api or $GENAI_API_PATH
- Provides Claude API access via JPL's managed service

## Related Documentation

- [README.md](README.md) - Project overview and high-level architecture
- [jpl/doc/README.md](jpl/doc/README.md) - LLM scheduler complete guide
- [doc/getting-started.md](doc/getting-started.md) - Quick start tutorial
- [doc/manual.md](doc/manual.md) - TaskNet language reference
- [doc/smt-encoding.md](doc/smt-encoding.md) - Theory behind SMT encoding
- [jpl/doc/SEMANTIC-RULES.md](jpl/doc/SEMANTIC-RULES.md) - Scheduling semantics reference
