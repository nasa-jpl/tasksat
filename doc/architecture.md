# TaskSAT Architecture

This document describes the implementation architecture, SMT encoding, and internal design of TaskSAT.

## System Overview

TaskSAT transforms high-level scheduling specifications into SMT formulas that Z3 can solve. The pipeline has four main stages:

```
.tn file → Parser → AST → SMT Encoder → Z3 → Schedule/UNSAT
```

## Component Architecture

### 1. Parser (`src/smt/tasknet_parser.py`)

**Technology:** PLY (Python Lex-Yacc)

**Responsibilities:**
- Lexical analysis (tokenization)
- Syntax analysis (parsing)
- Construct Abstract Syntax Tree (AST)

**Key Files:**
- `src/smt/tasknet_parser.py` - Parser implementation
- `src/smt/grammar.txt` - Grammar specification (reference)

**Process:**
1. **Lexer**: Breaks input into tokens (keywords, identifiers, numbers, operators)
2. **Parser**: Applies grammar rules to build AST
3. **Output**: Python objects representing the tasknet structure

**Example token flow:**
```
"battery : rate [-5.0, 5.0] bounds [0.0, 100.0] = 50.0;"
                          ↓
IDENTIFIER(battery) COLON RATE LBRACKET NUMBER(-5.0) COMMA ...
                          ↓
RateTimeline(id='battery', rate_range=[-5.0, 5.0], ...)
```

### 2. Abstract Syntax Tree (`src/smt/tasknet_ast.py`)

**Responsibilities:**
- Define data structures for all AST nodes
- Represent tasknets, timelines, tasks, constraints, impacts

**Key Classes:**
- `TaskNet` - Root node, contains timelines and tasks
- `StateTimeline`, `AtomicTimeline`, `ClaimableTimeline`, `CumulativeTimeline`, `RateTimeline`
- `Task` - Task definition with constraints and impacts
- `ImpactAssign`, `ImpactCumulative`, `ImpactRate` - Impact types
- `Constraint` - Temporal properties

**Design:** Simple dataclasses with no logic, just structure.

### 3. Wellformedness Checker (`src/smt/tasknet_wellformedness.py`)

**Responsibilities:**
- Validate AST for semantic correctness
- Check timeline-impact compatibility
- Verify constraint types match timeline types
- Ensure impact timing is valid

**Key Checks:**
- State/atomic timelines: only assignment in pre/post (not maint)
- Numeric timelines: no assignment, only delta/rate
- Timeline references exist
- Task IDs are unique
- Temporal properties are well-typed

**Example validation:**
```python
# This is INVALID:
task bad {
  impacts {
    maint {
      mode = active;  // ❌ Can't assign state in maint
    }
  }
}

# This is VALID:
task good {
  impacts {
    pre {
      mode = active;  // ✓ Can assign in pre
    }
  }
}
```

### 4. SMT Encoder (`src/smt/tasknet_smt.py`)

**Responsibilities:**
- Transform AST into SMT formulas
- Encode time, tasks, timelines, and constraints as Z3 expressions
- Handle both satisfy and optimize modes

**Core Concepts:**

#### Zone-Based Time Discretization

**Problem:** Time is continuous, but we need discrete reasoning.

**Solution:** Divide time into "zones" - intervals bounded by task start/end times.

**Example:**
```
Timeline: [0 ────────────────────── 100]

Tasks:
  T1: [10 ───────── 30]
  T2:              [30 ──────────── 60]

Zones created:
  Zone 0: (0, 10]    - Before any task
  Zone 1: (10, 30]   - T1 active
  Zone 2: (30, 60]   - T2 active
  Zone 3: (60, 100]  - After all tasks
```

**Encoding:**
- Create zone boundary variables: `z_0, z_1, z_2, ..., z_N`
- Constraint: `z_0 = 0`, `z_N = end`, `z_i < z_{i+1}`
- Task start/end times must align with zone boundaries

**Advantage:** Reduces infinite continuous time to finite discrete zones.

#### Task Variables

For each task `T`:
- `start_T`: Integer variable for start time (which zone boundary)
- `end_T`: Integer variable for end time (which zone boundary)
- `active_T_z`: Boolean variable for each zone (true if T active in zone z)

**Constraints:**
- `start_T < end_T` (task has positive duration)
- `start_T >= start_range_min, end_T <= end_range_max` (time windows)
- `end_T - start_T >= duration_min, <= duration_max` (duration bounds)
- Task ordering: `start_T2 >= end_T1` (for `T2 after T1`)

#### Timeline Variables

For each timeline in each zone:
- State/Atomic: `value_tl_z` (integer or boolean)
- Numeric (claim/cumulative/rate): `value_tl_z` (real number)

**Constraints encode:**
- Initial values: `value_tl_0 = initial_value`
- Bounds: `min <= value_tl_z <= max`
- Transitions between zones based on impacts

#### Impact Encoding

**Assignment (state/atomic timelines):**
```python
# pre impact: state = value at task start
If(zone == task_start, new_value, current_value)

# post impact: state = value at task end
If(zone == task_end, new_value, current_value)
```

**Delta (numeric timelines):**
```python
# pre: instant change at start
If(zone == task_start, current + delta, current)

# maint: add at start, subtract at end (temporary)
If(zone == task_start, current + delta,
   If(zone == task_end, current - delta, current))

# post: instant change at end
If(zone == task_end, current + delta, current)
```

**Rate (numeric timelines):**
```python
# Compute delta for zone duration
dt = zone_end_time - zone_start_time
rate_contribution = rate_value * dt

# pre: rate active from start onward
If(zone >= task_start, rate_contribution, 0)

# maint: rate active only during task
If(task_start <= zone < task_end, rate_contribution, 0)

# post: rate active from end onward
If(zone >= task_end, rate_contribution, 0)
```

#### Temporal Property Encoding

**always φ:**
```python
And([φ(z) for z in zones])
```

**eventually φ:**
```python
Or([φ(z) for z in zones])
```

**φ until ψ:**
```python
Or([
  And(ψ(z), And([φ(i) for i in range(z)]))
  for z in zones
])
```

**active(task):**
```python
active_task_z  # The boolean variable
```

### 5. Z3 Interface

**Modes:**

**Satisfy Mode:**
```python
solver = Solver()
solver.add(constraints)
result = solver.check()
if result == sat:
    model = solver.model()
```

**Optimize Mode:**
```python
optimizer = Optimize()
optimizer.add(constraints)
optimizer.minimize(sum_of_optional_tasks)  # Minimize optional tasks
result = optimizer.check()
```

**Output Generation:**
- Extract task start/end times from model
- Extract timeline values in each zone
- Print schedule in human-readable format

## File Organization

```
src/smt/
  tasknet_parser.py      - PLY parser
  tasknet_ast.py         - AST node definitions
  tasknet_wellformedness.py - Semantic validation
  tasknet_smt.py         - SMT encoding
  tasknet_verifier.py    - Main entry point
  grammar.txt            - Grammar reference

tests/tasknet_files/
  valid/                 - Working examples
  invalid/               - Tests for error handling
  stress/                - Performance benchmarks
```

## Key Algorithms

### Zone Computation

**Input:** Set of tasks with start/end variables

**Output:** Ordered sequence of zone boundaries

**Algorithm:**
1. Collect all potential boundaries: task starts, task ends, time 0, time horizon
2. Create variables for each boundary
3. Add ordering constraints: `z_i < z_{i+1}`
4. Let Z3 decide actual boundary positions

### Timeline State Transitions

**For each timeline, for each zone:**
1. Start with previous zone's value
2. Apply all active impacts from tasks
3. Compute new value using If-Then-Else chains
4. Add wellformedness bounds checks

### Optimization Objective

**Goal:** Minimize number of optional tasks included

**Encoding:**
```python
optional_task_indicators = [
  If(task_is_executed, 1, 0)
  for task in optional_tasks
]
optimizer.minimize(Sum(optional_task_indicators))
```

## Performance Considerations

### What Makes Problems Hard?

1. **Many zone boundaries**: More tasks = more zones = more variables
2. **Variable durations**: Wide ranges create large search space
3. **Optional tasks**: Each adds a branch (include or exclude)
4. **Tight constraints**: Less freedom = more backtracking
5. **Sequential dependencies**: Create deep decision trees

### What Z3 is Good At

1. **Conflict detection**: Quickly proves UNSAT
2. **Linear arithmetic**: Efficient SMT theory
3. **Boolean reasoning**: Fast SAT solving core
4. **Incremental solving**: Can add constraints and re-solve

### Optimization Opportunities

**Current encoding is straightforward but not optimized. Potential improvements:**

1. **Symmetry breaking**: Add constraints to eliminate equivalent solutions
2. **Zone minimization**: Pre-compute minimal zone set
3. **Lazy constraint generation**: Add constraints on-demand
4. **Custom propagators**: Domain-specific reasoning in Z3
5. **Parallel solving**: Run multiple Z3 instances with different strategies

## Extending TaskSAT

### Adding a New Timeline Type

1. **Define AST node** in `tasknet_ast.py`:
```python
@dataclass
class MyTimeline(Timeline):
    # ... fields
```

2. **Add parser rules** in `tasknet_parser.py`:
```python
def p_timeline_kind_my(p):
    "timeline_kind : MYTYPE ..."
    p[0] = MyTimeline(...)
```

3. **Add wellformedness** checks in `tasknet_wellformedness.py`

4. **Add SMT encoding** in `tasknet_smt.py`:
```python
def _encode_my_timeline(self, tl):
    # Create variables
    # Add constraints
```

### Adding a New Impact Type

Similar process: AST → Parser → Wellformedness → SMT encoding

### Adding a New Temporal Operator

1. **Add to AST** (`tasknet_ast.py`)
2. **Add parser rule** (`tasknet_parser.py`)
3. **Add encoding** in `tasknet_smt.py`:
```python
def _encode_temporal_my_operator(self, formula, zone):
    # Return Z3 expression
```

## Testing

**Test structure:**
- `tests/tasknet_files/valid/` - Should parse and solve
- `tests/tasknet_files/invalid/` - Should reject with errors
- `tests/tasknet_files/stress/` - Performance benchmarks

**Run tests:**
```bash
pytest tests/
```

**Add new test:**
1. Create `.tn` file in appropriate directory
2. Run verifier to check it works
3. Document expected behavior in comments

## Debugging

### Parser Errors

**Symptom:** Syntax error message

**Debug:**
1. Check grammar in `grammar.txt`
2. Verify token names match
3. Look for typos in keywords
4. Run with verbose mode (if available)

### Wellformedness Errors

**Symptom:** Semantic error message

**Debug:**
1. Check timeline types match impact types
2. Verify all referenced timelines exist
3. Check impact timing (pre/maint/post) is valid
4. Look at `tasknet_wellformedness.py` for specific checks

### UNSAT Results

**Symptom:** No solution found, but expected SAT

**Debug:**
1. Use `--mode satisfy` for unsat core (if implemented)
2. Simplify problem: remove constraints one-by-one
3. Check timeline bounds are realistic
4. Increase time horizon (`end = ...`)
5. Check for conflicting impacts

### Timeout

**Symptom:** Solver runs forever

**Debug:**
1. Try `--mode satisfy` instead of optimize
2. Reduce optional tasks
3. Fix durations instead of ranges
4. See [performance.md](performance.md) for guidelines

## Future Directions

### Short Term
- Better error messages with line numbers
- Unsat core generation
- Schedule visualization (Gantt charts)
- More temporal operators

### Medium Term
- Hierarchical tasknets (subproblem decomposition)
- Probabilistic constraints
- Cost/utility functions beyond optional task count
- Multi-objective optimization

### Long Term
- Custom SMT theory for scheduling
- Constraint Learning from previous solves
- Interactive solving (add constraints during search)
- Integration with planning systems (PDDL, ANML)

## References

- **Z3 SMT Solver**: https://github.com/Z3Prover/z3
- **PLY (Python Lex-Yacc)**: https://www.dabeaz.com/ply/
- **SMT-LIB**: http://smtlib.cs.uiowa.edu/
- **Scheduling Problems**: Pinedo, "Scheduling: Theory, Algorithms, and Systems"

## Contributing

To contribute to TaskSAT:

1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Ensure all tests pass
5. Submit a pull request

**Areas that need work:**
- Better documentation of SMT encoding details
- More example tasknets
- Performance optimization
- Extended language features
