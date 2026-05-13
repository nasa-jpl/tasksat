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
# Default (optimize mode)
python src/smt/tasknet_verifier.py tasknet.tn

# Satisfy mode (find any valid schedule)
python src/smt/tasknet_verifier.py tasknet.tn --mode satisfy

# Inspect transformed tasknet (after auto-instantiation)
python src/smt/tasknet_verifier.py tasknet.tn --write-transformed output.json
```

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
# Create Gantt chart (grouped by task type)
python3 jpl/tools/visualize_schedule.py schedule.json --grouped -o gantt.png
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
    return tn
```

**LLM-based pipeline** (`jpl/tools/`):
- `llm_scheduler.py` - Entry point, orchestrates generate-validate loop
- `lean_converter.py` - Converts .tn to Lean JSON format
- `visualize_schedule.py` - Creates Gantt charts
- Lean validator: `src/lean/TaskNetExec/` (compiled separately)

### Auto-Instantiation (Recent Feature)

**Problem**: Tasks can reference taskdefs via `after`/`containedin` but taskdefs are templates, not instances.

**Solution**: `instantiate_from_definitions()` transformation automatically creates task instances from taskdefs when:
- A task instance has type-level dependencies (after/containedin to a taskdef)
- No instances of that taskdef exist in the original tasknet

**Behavior**:
- Creates one instance per dependent task (not one per taskdef)
- Naming: `{taskdef}_auto_0`, `{taskdef}_auto_1`, etc.
- No cascade: only direct dependencies are instantiated
- Only if user provided zero instances (if user provided any, they manage instances manually)

**Example**:
```
taskdef comm_preheat { ... }
task downlink1 { after comm_preheat; }
task downlink2 { after comm_preheat; }

→ Creates: comm_preheat_auto_0, comm_preheat_auto_1
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

## Common Pitfalls

1. **Invariant timing**: TaskSAT checks invariants at (start, end], not [start, end]. PRE impacts at start must take effect before invariants are checked.

2. **Type-level constraints**: When a task references a taskdef (not an instance), auto-instantiation will create instances. Understand when this happens vs when to manually create instances.

3. **Battery SOC ceiling**: If initial value equals upper bound (e.g., initial=95, inv [0, 95]), recharging after t=0 is impossible. Use initial < upper bound.

4. **Atomic timeline maint impacts**: `maint { flag += 1 }` raises flag at task start, lowers at end automatically.

5. **LLM scheduler requires JPL GenAI API**: The genai_api package must be installed and authenticated. Look for it at ~/genai_api or set GENAI_API_PATH.

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
