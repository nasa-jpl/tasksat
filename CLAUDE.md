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

### Auto-Instantiation

TaskSAT automatically creates task instances when taskdefs are referenced in type-level dependencies (`after` or `containedin` constraints).

**Key behavior:**
- **One instance per dependent task** (MEXEC semantics): Each task depending on a taskdef gets its own instance
- **Naming**: Auto-created instances are `{taskdef}_auto_0`, `{taskdef}_auto_1`, etc.
- **Skipped if manual instances exist**: If you create ANY instance of a taskdef manually, auto-instantiation is skipped
- **Transform pass**: Happens in `tasknet_transforms.py:instantiate_from_definitions()`
- **View with**: `--transform-only` flag writes `.tasksat/transformed/<filename>_transformed.tn`

**Example:**
```tasknet
taskdef predrive { duration 300; }
taskdef drive { after predrive; }  // Type-level dependency

task drive1 : drive {}
task drive2 : drive {}
```
Creates: `predrive_auto_0` (for drive1), `predrive_auto_1` (for drive2)

**Why one-per-dependent?** Allows independent scheduling - each drive can have its predrive at different times, potentially overlapping.

### Parameters

TaskSAT supports parameters at three scopes: tasknet-level, taskdef-level, and task-level. Parameters allow you to define reusable values and avoid magic numbers in your specifications.

**Syntax:**
```tasknet
// TaskNet-level parameters (global scope)
tasknet Example {
  param GLOBAL_DURATION = 10;
  param GLOBAL_RATE = 0.5;
  
  // TaskDef-level parameters (inherited by instances)
  taskdef work {
    param {
      DURATION = GLOBAL_DURATION;  // Can reference global params
    }
    duration DURATION;
  }
  
  // Task-level parameters (highest priority)
  task t1 : work {}  // Uses DURATION=10 from taskdef
  
  task t2 : work {
    param {
      DURATION = 20;  // Override to 20
    }
  }
  
  task t3 {
    duration GLOBAL_DURATION;  // Direct reference to global param
  }
}
```

**Resolution order (highest to lowest priority):**
1. Task-level params
2. TaskDef-level params (for tasks instantiated from taskdefs)
3. TaskNet-level params

**Implementation:**
- Parsed as `ParamDecl` and `ParamRef` AST nodes (tasknet_parser.py)
- Resolved in `resolve_parameters()` transform (tasknet_transforms.py)
- Resolution happens FIRST, before all other transforms
- Unresolved parameter references in constraint formulas are treated as state names

**Use cases:**
- Avoid magic numbers: `param SAFE_BATTERY = 20.0;` instead of hardcoded values
- Reusable task definitions with configurable defaults
- Global constants for duration, capacity, thresholds
- Overriding defaults per task instance

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

## Language Features

### Mutex Syntax

TaskSAT supports concise mutex syntax for expressing mutual exclusion between tasks:

```tasknet
constraints {
  mutex [science1, science2];  // Within-group: no two tasks can overlap
  mutex [drive1, drive2] with [science1, science2];  // Between-group: cross-product exclusion
}
```

**Implementation:**
- Parsed as `TLMutex` AST node (tasknet_parser.py)
- Desugared to task boundary comparisons in `desugar_mutex()` transform (tasknet_transforms.py)
- Desugars BEFORE `desugar_active_predicate()` to avoid creating `__task_active` timelines
- More efficient than `always (active(A) -> not active(B))` syntax

### Unnamed Constraints

Both named and unnamed constraints are supported:

```tasknet
constraints {
  prop my_constraint: mutex [A, B];  // Named
  mutex [C, D];  // Unnamed (auto-named as "mutex_C_D")
  always (battery >= 20.0);  // Unnamed (auto-named as "constraint_1")
}
```

**Auto-naming:**
- `mutex [A, B]` → `"mutex_A_B"`
- `sequence [A, B]` → `"sequence_A_B"`
- Generic formulas → `"constraint_N"` (counter-based)

### Time-Constrained Dependencies

TaskSAT supports optional time range parameters on `after` and `containedin` dependencies to express temporal gaps and offsets.

**After dependencies** (with optional gap):
- `after A` - No gap: `B.start >= A.end` (immediate succession allowed)
- `after A [min, max]` - Full range: `B.start ∈ [A.end + min, A.end + max]`
- `after A num` - Shorthand for `[0, num]`: `B.start ∈ [A.end, A.end + num]`

**Containedin dependencies** (with optional offsets):
- `containedin A` - No offsets: `A.start <= child.start AND child.end <= A.end` (exact containment)
- `containedin A [s_min, s_max] [e_min, e_max]` - Full ranges:
  - Start offset: `child.start ∈ [A.start + s_min, A.start + s_max]`
  - End offset: `child.end ∈ [A.end - e_max, A.end - e_min]`
- `containedin A num1 num2` - Shorthand for `[0, num1] [0, num2]`
- `containedin A num` - Shorthand for `[0, num] [0, num]`
- **Mixed per-offset**: Can mix range/shorthand for individual offsets:
  - `containedin A 10 [20,30]` → `containedin A [0,10] [20,30]`
  - `containedin A [10,20] 30` → `containedin A [10,20] [0,30]`

**Example:**
```tasknet
taskdef predrive { duration_range [10, 10]; }
taskdef drive { 
  after predrive [50, 100];  // Start 50-100 time units after predrive ends
  duration_range [30, 30]; 
}

taskdef warmup { duration_range [50, 50]; }
taskdef science {
  containedin warmup [5, 10] [5, 10];  // Start 5-10 after warmup starts, end 5-10 before warmup ends
  duration_range [30, 30];
}

task drive1 : drive {}
task warmup1 : warmup {}
task science1 : science {}
```

**Behavior:**
- Auto-instantiates `predrive_auto_0` for `drive1`
- `drive1.start ∈ [predrive_auto_0.end + 50, predrive_auto_0.end + 100]`
- `science1.start ∈ [warmup1.start + 5, warmup1.start + 10]`
- `science1.end ∈ [warmup1.end - 10, warmup1.end - 5]`

**Implementation:**
- AST: `AfterDependency` and `ContainedinDependency` dataclasses in [tasknet_ast.py](src/smt/tasknet_ast.py)
- Parser: Extended grammar in [tasknet_parser.py](src/smt/tasknet_parser.py) supports all syntax variants
- SMT: Gap and offset constraints in [tasknet_smt.py](src/smt/tasknet_smt.py)
- Transforms: Dependency object handling in [tasknet_transforms.py](src/smt/tasknet_transforms.py)
- Printer: Smart formatting in [tasknet_printer.py](src/smt/tasknet_printer.py)

### Initial and Final Blocks

TaskSAT has two symmetric blocks describing timeline state at the boundaries of a
schedule. They share the same body grammar (`tlcon` statements: `timeline = value;`
or `timeline in v1, [lo,hi], ...;`) but differ fundamentally in meaning.

**`initial {...}` — a hard constraint.** Sets/constrains timeline state at time 0
(zone 0). Added to the SMT solver; it restricts which schedules are valid.

```tasknet
initial {
  battery = 50.0;
  mode = idle;
}
```

**`final {...}` — a checked property.** Asserts that *for every valid schedule*,
the terminal state satisfies the constraints. It is **not** a constraint (it never
restricts scheduling); it is verified like a `properties {...}` entry. If some
schedule ends in a violating state, that schedule is reported as a counterexample.
It appears in the property results (console, `properties.json`, web UI) under the
name `final`.

```tasknet
final {
  battery in [55.0, 100.0];   // must hold at the end of every schedule
  mode = idle;
}
```

**Checkpoint = makespan, not horizon.** The final state is evaluated *right after
the last scheduled task ends* (the makespan `M = max(end)`), which may be earlier
than the horizon `end`. This is the right-limit of each timeline at `M`:
- **Rate timelines**: read the VALUE at time `M` (continuous), i.e. before any
  drift over the remaining `[M, end]` tail.
- **State / atomic / cumulative / claimable timelines**: read the post-task value
  (post-impacts of the last task applied), which is constant through to the horizon.
- Caveat: a value-`+=` post-impact on a *rate* timeline by the last task is not
  reflected in the final read (rate finals read the pre-post-impact value at `M`).

**`final within initial {...}` — extension sugar.** The final constraints are the
initial block's constraints plus the ones listed. Convenient for "end where we
started, and also ...". The block is optional: `final within initial;` means
exactly the initial constraints. Note this includes initial's constraints
literally, so `initial { battery = 50; }` + `final within initial { battery in
[55,100]; }` is contradictory (can never hold).

```tasknet
initial { mode = idle; }
final within initial { battery in [55.0, 100.0]; }  // mode = idle AND battery in [55,100]
```

```tasknet
initial { mode = idle; battery = 50.0; }
final within initial;   // every schedule must end exactly as it started
```

**Implementation:**
- AST: `TaskNet.final_constraints` / `final_extends_initial` + `effective_final_constraints()` in [tasknet_ast.py](src/smt/tasknet_ast.py)
- Parser: `final_block` productions (`final {...}`, `final within initial {...}`, `final within initial;`) in [tasknet_parser.py](src/smt/tasknet_parser.py)
- SMT: `_encode_final_holds()` / `_final_makespan()` / `_final_zone_index()`, checked (negated) in `check_temporal_properties()` in [tasknet_smt.py](src/smt/tasknet_smt.py)
- Wellformedness / Transforms / Printer: mirror the `initial` handling for `final`

## Dependencies

**Python:**
- z3-solver - SMT solver
- ply - Parser generator
- matplotlib - Visualization
- flask - Web UI
- pytest - Testing

