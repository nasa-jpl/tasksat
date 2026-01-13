# TaskSAT Performance & Scaling

This document describes performance characteristics, stress test results, and guidelines for understanding problem complexity.

## Summary

TaskSAT's performance depends heavily on:
1. **Problem structure** (constraint patterns)
2. **Number of tasks**
3. **Solver mode** (satisfy vs optimize)
4. **Timeline complexity** (number and types)

**Key finding**: Constraint structure matters more than raw task count. Sequential dependency chains are significantly harder than multi-resource problems.

## Stress Test Results

Comprehensive stress tests are located in `tests/tasknet_files/stress/`.

### Stress Test 1: Mars Rover (Multi-Resource)

**File:** [stress1_mars_rover.tn](../tests/tasknet_files/stress/stress1_mars_rover.tn)

**Configuration:**
- 20 tasks (all required)
- 14 timelines (battery, data, memory, CPU, thermal, etc.)
- 7 temporal properties
- 360 time horizon

**Result:** **SAT in 21 minutes 8 seconds** (optimize mode)

**Analysis:** Complex multi-resource problem with parallel tasks. Despite 20 tasks and many timelines, the problem is solvable because tasks can execute in parallel when resources allow.

### Stress Tests 2-4: Satellite Constellation (Over-Constrained)

**Files:**
- [stress2_satellite_constellation.tn](../tests/tasknet_files/stress/stress2_satellite_constellation.tn) - 30 tasks
- [stress3_satellite_relaxed.tn](../tests/tasknet_files/stress/stress3_satellite_relaxed.tn) - 12 tasks
- [stress4_simple_constellation.tn](../tests/tasknet_files/stress/stress4_simple_constellation.tn) - 15 tasks

**Results:**
- stress2: **UNSAT in 1.48 seconds**
- stress3: **UNSAT in 0.53 seconds**
- stress4: **UNSAT in 0.49 seconds**

**Analysis:** Over-constrained problems are detected very quickly. The SMT solver efficiently finds conflicts even in large problems (30 tasks). This demonstrates that Z3 is excellent at proving unsatisfiability.

### Stress Tests 5-7: Sequential Chain (Challenging)

**Files:**
- [stress5_sequential_chain.tn](../tests/tasknet_files/stress/stress5_sequential_chain.tn) - 30 tasks
- [stress6_sequential_20.tn](../tests/tasknet_files/stress/stress6_sequential_20.tn) - 20 tasks
- [stress7_sequential_15.tn](../tests/tasknet_files/stress/stress7_sequential_15.tn) - 15 tasks

**Results:**

| Test | Tasks | Satisfy Mode | Optimize Mode |
|------|-------|--------------|---------------|
| stress7 | 15 | **SAT in 2:40** | TIMEOUT (28+ min) |
| stress6 | 20 | TIMEOUT (34+ min) | TIMEOUT (15+ min) |
| stress5 | 30 | Not tested | TIMEOUT (2+ hours) |

**Analysis:**
1. **Satisfy mode is much faster than optimize mode** for sequential chains
2. **Non-linear scaling**: 15 tasks (2:40) → 20 tasks (timeout) shows exponential growth
3. **Sequential dependencies are hard**: Even 15 tasks takes longer in optimize mode than 20-task multi-resource problem

**Design:** Each task Ti requires battery >= (i-1)*5 and charges at rate +1.0, forcing sequential ordering T1 → T2 → ... → TN.

## Performance Comparison

| Problem Type | Tasks | Timelines | Mode | Time | Result |
|--------------|-------|-----------|------|------|--------|
| Multi-resource | 20 | 14 | optimize | 21:08 | SAT |
| Sequential chain | 15 | 1 | satisfy | 2:40 | SAT |
| Sequential chain | 15 | 1 | optimize | 28+ min | TIMEOUT |
| Sequential chain | 20 | 1 | satisfy | 34+ min | TIMEOUT |
| Sequential chain | 20 | 1 | optimize | 15+ min | TIMEOUT |
| Over-constrained | 30 | 33 | optimize | 1.48s | UNSAT |

## Scaling Characteristics

### 1. UNSAT Problems Scale Well

**Observation:** Z3 quickly detects infeasibility regardless of problem size.

**Reason:** Conflict detection prunes the search space efficiently.

**Guideline:** If your problem is UNSAT, expect fast results (<5 seconds for most problems).

### 2. Sequential Dependencies Don't Scale

**Observation:** Sequential chain patterns timeout beyond 15 tasks (satisfy mode) or even with 15 tasks (optimize mode).

**Reason:**
- Tight dependencies create exponential search space
- Duration ranges ([1, 6]) multiply possibilities
- Optional tasks increase combinations to explore

**Guideline:** Avoid strict sequential chains with >15 tasks if possible.

### 3. Optimize Mode is Expensive

**Observation:** Optimize mode is 10-20x slower than satisfy mode for same problem.

**Reason:** Must explore multiple solutions to find the optimal one.

**Guideline:**
- Use `--mode satisfy` for initial validation
- Use `--mode optimize` only when needed
- Minimize number of optional tasks

### 4. Multi-Resource Problems Scale Better

**Observation:** 20-task multi-resource problem solves faster than 15-task sequential chain.

**Reason:** Parallel execution opportunities reduce search space.

**Guideline:** If possible, structure problems to allow parallelism.

### 5. Timeline Count Matters Less Than Structure

**Observation:** stress1 (14 timelines) solves faster than stress7 (1 timeline) despite more complexity.

**Reason:** Number of timelines adds variables, but constraint structure determines search difficulty.

**Guideline:** Don't worry about timeline count; focus on constraint patterns.

## Complexity Guidelines

### Problem is Likely Tractable If:

✅ Tasks can execute in parallel
✅ Optional tasks < 10
✅ Total tasks < 20
✅ Constraints allow flexibility
✅ Using satisfy mode

### Problem May Be Hard If:

⚠️ Tasks form long sequential chains
⚠️ Many optional tasks (>10)
⚠️ Variable durations with wide ranges
⚠️ Total tasks > 20 with tight constraints
⚠️ Using optimize mode

### Problem is Very Hard If:

❌ Sequential chain with >20 tasks
❌ Optimize mode with >15 optional tasks
❌ Highly interdependent constraints
❌ Narrow time windows with many tasks

## Optimization Strategies

If your problem is timing out, try these strategies:

### 1. Use Satisfy Mode First

```bash
# Fast: Just find any solution
python src/smt/tasknet_verifier.py problem.tn --mode satisfy
```

If satisfy mode times out, the problem is fundamentally hard. If it succeeds quickly but optimize times out, the optimization is the bottleneck.

### 2. Reduce Optional Tasks

Instead of:
```tasknet
optional task bonus1 { ... }
optional task bonus2 { ... }
optional task bonus3 { ... }
// ... 20 optional tasks
```

Try:
```tasknet
optional task bonus1 { ... }
optional task bonus2 { ... }
// Keep only high-priority optional tasks
```

### 3. Fix Task Durations

Instead of:
```tasknet
task t1 {
  duration_range [1, 100];  // 100 possibilities!
}
```

Try:
```tasknet
task t1 {
  duration 50;  // Fixed duration
}
```

### 4. Relax Time Windows

Instead of:
```tasknet
task t1 {
  start_range [10, 15];  // Very narrow
  end_range [50, 55];
}
```

Try:
```tasknet
task t1 {
  start_range [0, 50];  // More flexibility
}
```

### 5. Break Sequential Chains

Instead of:
```tasknet
task t1 { after t0; }
task t2 { after t1; }
task t3 { after t2; }
// ... long chain
```

Try using resource constraints that implicitly order tasks, allowing solver more flexibility in scheduling.

### 6. Simplify Constraints

Remove unnecessary temporal properties. Every property adds constraints that the solver must check.

### 7. Increase Time Horizon

If tasks are packed tightly, increasing `end` value may help solver find solutions.

## Benchmarking Your Problem

To understand your problem's complexity:

1. **Run satisfy mode** with timing:
```bash
time python src/smt/tasknet_verifier.py problem.tn --mode satisfy
```

2. **Check result:**
   - <1 second: Very easy problem
   - 1-60 seconds: Moderate problem
   - 1-5 minutes: Hard problem
   - 5+ minutes: Very hard problem
   - Timeout: Problem may be too complex or UNSAT

3. **If satisfy works, try optimize:**
```bash
time python src/smt/tasknet_verifier.py problem.tn --mode optimize
```

4. **Compare times:**
   - 2-5x slower: Normal
   - 10x+ slower: Many optional tasks or complex objective
   - Timeout: Too many optional tasks or optimization search space too large

## Future Improvements

Potential areas for performance enhancement:

1. **Better zone discretization heuristics** - Smarter initial zone boundaries
2. **Incremental solving** - Reuse solutions for similar problems
3. **Parallelization** - Explore search space in parallel
4. **Custom SMT theories** - Domain-specific optimizations for scheduling
5. **Symmetry breaking** - Reduce equivalent solutions
6. **Preprocessing** - Simplify problems before encoding

## Conclusion

TaskSAT handles moderate-sized problems (15-20 tasks) well, especially when:
- Using satisfy mode
- Allowing parallel task execution
- Minimizing optional tasks
- Avoiding strict sequential dependencies

For larger problems (>20 tasks) or complex sequential patterns, consider:
- Decomposing into smaller subproblems
- Using satisfy mode only
- Fixing more parameters (durations, start times)
- Simplifying constraint structure

The stress tests demonstrate that **problem structure matters more than size** - a 20-task multi-resource problem solves faster than a 15-task sequential chain.
