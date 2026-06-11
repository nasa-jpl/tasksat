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

## Working with Branches

- **main** - Public repository (github.com/nasa-jpl/tasksat)

**Remote setup:**
```bash
git remote -v
# origin: github.com/nasa-jpl/tasksat (public)
```

## Dependencies

**Python:**
- z3-solver - SMT solver
- ply - Parser generator
- matplotlib - Visualization
- flask - Web UI
- pytest - Testing

