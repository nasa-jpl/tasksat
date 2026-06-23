# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TaskSAT is a domain-specific language and tool for modeling and verifying task scheduling problems with rich temporal and resource constraints. It combines a declarative specification language with SMT-based automated reasoning using Z3.

**Key concepts:**
- **TaskNet (.tn files)**: DSL for specifying tasks, timelines, constraints, and temporal properties
- **SMT-based verification**: Encodes scheduling problems as quantifier-free SMT formulas solved by Z3
- **Web UI**: Flask-based interface for browsing verification results
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

**Visualize schedules:**
```bash
# SMT verifier: Gantt chart generated automatically during verification
python src/smt/tasknet_verifier.py tasknet.tn
# Output: .tasksat/schedules/<tasknet>_gantt.png
#         .tasksat/schedules/<tasknet>_schedule.json

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

## Architecture

TaskSAT uses SMT-based scheduling:
```
.tn file → Parser → AST → Transformations → Wellformedness → SMT Encoding → Z3 Solver → Schedule/UNSAT
```

### Key Files and Pipeline

**SMT-based pipeline** (`src/smt/`):
- `tasknet_verifier.py` - Entry point
- `tasknet_parser.py` - PLY-based parser (.tn → AST)
- `tasknet_ast.py` - AST node definitions
- `tasknet_transforms.py` - **Critical**: AST transformation pipeline
- `tasknet_wellformedness.py` - Semantic validation
- `tasknet_smt.py` - SMT encoding (zone-based discretization)

### Repository Structure

```
tasksat/
├── src/
│   ├── smt/          # Python SMT-based verifier
│   └── lean/         # Lean validator
├── tests/            # Pytest tests
│   └── tasknet_files/  # Test .tn files
└── doc/              # Documentation (getting-started, tutorial, manual)
```

### Task Instance Ranges

TaskSAT supports compact syntax for creating multiple task instances:
- `task T[min..max]` expands to `min` required tasks + `(max-min)` optional tasks
- `request task T[min..max]` expands to `min` required tasks + `(max-min)` request tasks
- `task T[count]` is shorthand for `task T[0..count]` (all optional)
- Expansion happens in `tasknet_transforms.py:expand_task_ranges()`
- Creates `TaskRange` AST nodes in parser, expands in transform pass (before other transforms)
- Use `--transform-only` to inspect expanded tasks

**Example:**
```tasknet
task science[2..4] : science_def { id 100; }
```
Expands to: `science_0`, `science_1` (required), `science_2`, `science_3` (optional)

## Working with Branches

- **main** - Public repository (github.com/nasa-jpl/tasksat)

**Remote setup:**
```bash
git remote -v
# origin: github.com/nasa-jpl/tasksat (public)
```

## Timeline Semantics

### Atomic Timelines

Atomic timelines enforce mutual exclusion using integer [0,1] values (0 = unclaimed, 1 = claimed).

**Syntax:**
```tasknet
resource : atomic = 0;  // Initialize to 0 (unclaimed), default is 0 if omitted
```

**Impacts:**
- **Only cumulative impacts allowed**: `+= 1` (claim), `-= 1` (release)
- **Assignment impacts rejected**: `= 0`, `= 1` are not allowed - they don't enforce mutual exclusion
- **All timings allowed**: `pre`, `maint`, `post`
- **Most common pattern**: `maint { resource += 1; }` for automatic claim/release

**Constraints:**
- **Use numeric syntax**: `resource = 0`, `resource = 1`, `resource >= 1`, etc.
- **Boolean syntax rejected**: `resource = true/false` is not allowed

**Why cumulative-only?**
Assignment allows conflicts: if Task A does `resource = 1` at time 10 and Task B does `resource = 1` at time 15, both succeed without detecting the conflict (the timeline just stays at 1). Cumulative impacts with [0,1] bounds enforce mutual exclusion via overflow detection: if both tasks try `+= 1`, the value goes to 2, violating the [0,1] constraint.

**Auto-generated task state timelines:**
When you use `active(T)` syntax or reference `__T_active` timelines, the system automatically generates atomic timelines with `maint { __T_active += 1; }` impacts.

### Rate Timeline Value vs Rate Impacts

Rate timelines track both a VALUE (resource level) and a RATE (how fast it changes). Impacts can modify either:

**Value impacts** (write to zone s+1):
```tasknet
impacts {
  pre { battery += 30.0; }    // Adds to value at zone s+1
  maint { battery += 10.0; }  // Adds to value at start (s+1), subtracts at end
}
```

**Rate impacts** (write to zone s):
```tasknet
impacts {
  maint { battery +~ 2.0; }   // Adds to rate at zone s (affects entire execution)
  pre { battery =~ 1.0; }     // Sets rate at zone s
}
```

**Why the difference?**
Rate impacts must write to zone s to affect the entire task execution interval [s, e]. Value impacts write to zone s+1 to maintain the separation between "input state" (zone s) and "execution state" (zone s+1), consistent with all other timeline types.

## Dependencies

**Python:**
- z3-solver - SMT solver
- ply - Parser generator
- matplotlib - Visualization
- flask - Web UI
- pytest - Testing

