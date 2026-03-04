# TaskNet Benchmark Suite

## Overview

The benchmark suite provides synthetic test cases for:
1. **Performance evaluation** - Measure solver performance across different problem types
2. **Regression testing** - Detect performance regressions after code changes
3. **Demonstrating scaling characteristics** - Show how different patterns scale
4. **Validating constraint patterns** - Test various TaskNet features

All benchmarks are located in `tests/tasknet_files/benchmark/` and can be run individually or as a suite using the automated runner.

## Benchmark Types

### 1. Sequential Chain (seq_*.tn)

**Purpose:** Test performance on strict sequential dependencies

**Pattern:** Tasks must execute sequentially T1 → T2 → ... → TN, enforced by resource constraints:
- Battery timeline starts at 0.0
- Task Ti requires battery >= 5.0*(i-1)
- Each task charges battery at rate +1.0/time during execution
- This creates a strict ordering dependency

**Variants:**
- `seq_5.tn` - 5 tasks (fast baseline, <1s)
- `seq_10.tn` - 10 tasks (moderate, ~1-5s)
- `seq_15.tn` - 15 tasks (challenging, may be slow)
- `seq_20.tn` - 20 tasks (very hard, likely timeout)

**Expected Results:**
- Result: SAT (valid schedule exists)
- Satisfy mode: scales up to ~15 tasks
- Optimize mode: struggles beyond 10 tasks
- Performance degrades exponentially with task count

**Design Notes:**
- Each benchmark includes ~70% required tasks, ~30% optional tasks
- Variable durations [1, 6] increase search space
- Tests solver's ability to handle sequential dependency chains

---

### 2. Parallel Resource (par_*.tn)

**Purpose:** Test multi-resource scheduling with concurrency

**Pattern:** Concurrency counter pattern using cumulative timelines:
- Multiple independent timelines (round-robin task assignment)
- Each timeline allows up to N concurrent tasks
- Tasks use pre/post impacts to increment/decrement counters
- **Precondition**: `counter <= N-1` (can start if less than N tasks running)
- **Invariant**: `counter <= N` (allows increment during task)
- **Impact (pre)**: `counter += 1.0` (increment on start)
- **Impact (post)**: `counter += -1.0` (decrement on end)

**Variants:**
- `par_5_2.tn` - 5 tasks, 2 timelines, parallelism=3
- `par_10_3.tn` - 10 tasks, 3 timelines, parallelism=3
- `par_20_5.tn` - 20 tasks, 5 timelines, parallelism=3
- `par_30_10.tn` - 30 tasks, 10 timelines, parallelism=3

**Expected Results:**
- Result: SAT
- Scales better than sequential patterns (parallelism helps)
- Should solve relatively quickly even for larger sizes
- Maximum theoretical parallelism: `num_timelines × parallelism_per_timeline`

**Design Notes:**
- Tasks distributed round-robin across timelines
- Demonstrates benefit of parallel execution opportunities
- Tests cumulative timeline impacts (pre/post)

---

### 3. Sequential Force (seqforce_*.tn)

**Purpose:** Test combined resource + temporal reasoning

**Pattern:** Sequential chain (like seq_*) PLUS time window constraints:
- Same battery resource constraints as seq_* benchmarks
- **Additional**: start_range and end_range for each task
- Dual enforcement of sequential ordering (both resources AND temporal windows)
- Tests solver's ability to combine multiple constraint types

**Variants:**
- `seqforce_5.tn` - 5 tasks with windows
- `seqforce_10.tn` - 10 tasks with windows
- `seqforce_15.tn` - 15 tasks with windows
- `seqforce_20.tn` - 20 tasks with windows (likely timeout)

**Expected Results:**
- Result: SAT
- More constrained than seq_* alone
- Tests combined resource + temporal reasoning
- May be slower than seq_* due to additional constraints

**Design Notes:**
- Combines two orthogonal constraint mechanisms
- Useful for testing solvers that treat different constraint types differently
- Time windows add temporal reasoning on top of resource dependencies

---

### 4. Property Verification (prop_*.tn)

**Purpose:** Measure property verification overhead

**Pattern:** Deliberately simple scheduling + many temporal properties:
- **Simple task structure**: identical durations (15), minimal constraints
- **Abundant resources**: tl1 starts at 50, only drops to ~20
- **No forced ordering**: tasks can run in any order or parallel
- **Focus**: Property verification cost, not scheduling complexity
- SMT solver finds valid schedule quickly (<1 second)

**Variants:**
- `prop_5_10.tn` - 5 tasks, 10 properties (fast, <5s total)
- `prop_10_20.tn` - 10 tasks, 20 properties (moderate, ~10-30s)
- `prop_10_50.tn` - 10 tasks, 50 properties (slow, 1-3 minutes)
- `prop_15_100.tn` - 15 tasks, 100 properties (very slow, likely timeout)

**Expected Results:**
- Result: SAT
- Schedule found in <1 second
- Time dominated by property verification (Phase 2)
- Scales approximately linearly with property count
- Each property check requires a separate SMT solver call

**Property Types Tested:**
- Temporal logic formulas (G, F, U operators)
- Timeline value constraints
- Task ordering constraints
- State transitions

**Design Notes:**
- Isolates property verification cost from scheduling cost
- Demonstrates that property verification is independent workload
- Useful for profiling property checking performance

---

### 5. UNSAT Tests (unsat_*.tn)

**Purpose:** Test infeasibility detection speed

**Pattern:** Deliberately over-constrained problems with no valid schedule

**Conflict Types:**
1. **Resource conflict** - Tasks require more resources than available
   - Single atomic resource (only 1 task can use at a time)
   - Total task durations exceed time horizon
   - Example: 10 tasks × 13 time units each = 130 > 100 time horizon

2. **Dependency conflict** - Circular or impossible task dependencies
   - Tasks have contradictory ordering constraints
   - Example: T1 after T2, T2 after T3, T3 after T1 (circular)

3. **Temporal conflict** - Impossible time window constraints
   - Task time windows don't allow any valid schedule
   - Example: T1 must end before 50, T2 must start after 100, but T2 depends on T1

**Variants:**
- `unsat_10_resource.tn` - 10 tasks, resource conflict
- `unsat_10_dependency.tn` - 10 tasks, impossible dependencies
- `unsat_10_temporal.tn` - 10 tasks, impossible time windows
- `unsat_20_resource.tn` - 20 tasks, resource conflict
- `unsat_25_dependency.tn` - 25 tasks, dependency conflict
- `unsat_30_temporal.tn` - 30 tasks, temporal conflict

**Expected Results:**
- Result: UNSAT (no valid schedule exists)
- Should detect infeasibility quickly (<5 seconds)
- Z3 excels at conflict detection and early pruning
- Larger UNSAT problems often solve as fast as smaller ones

**Design Notes:**
- Demonstrates Z3's efficiency at proving unsatisfiability
- Important for validating that solver correctly rejects invalid problems
- Fast UNSAT detection is crucial for interactive use

---

## Running Benchmarks

### Run Single Benchmark

Test a specific benchmark manually:
```bash
python src/smt/tasknet_verifier.py tests/tasknet_files/benchmark/seq_5.tn --mode satisfy
```

With optimize mode:
```bash
python src/smt/tasknet_verifier.py tests/tasknet_files/benchmark/par_10_3.tn --mode optimize
```

### Run Full Benchmark Suite

Run all benchmarks with automated collection:
```bash
python tools/run_benchmarks.py --output results/benchmark_results.json
```

This will:
- Run all benchmarks in `tests/tasknet_files/benchmark/`
- Test both `--mode satisfy` and `--mode optimize`
- Apply 5-minute timeout per benchmark
- Generate JSON and CSV result files

### Run with Custom Settings

Shorter timeout (1 minute):
```bash
python tools/run_benchmarks.py --output results/quick_results.json --timeout 60
```

Test only satisfy mode:
```bash
python tools/run_benchmarks.py --output results/satisfy_results.json --mode satisfy
```

Test specific directory:
```bash
python tools/run_benchmarks.py --output results/stress_results.json --benchmark-dir tests/tasknet_files/stress
```

### Output Format

The runner produces two files:

**JSON format** (`results/benchmark_results.json`):
```json
{
  "run_timestamp": "2026-03-04T10:30:00",
  "total_benchmarks": 44,
  "benchmarks": [
    {
      "benchmark_name": "seq_5",
      "mode": "satisfy",
      "result": "SAT",
      "validity_time": 0.15,
      "property_time": 0.02,
      "total_time": 0.27,
      "properties_hold": 1,
      "properties_violated": 0,
      "properties_unknown": 0,
      "timeout": false
    },
    ...
  ]
}
```

**CSV format** (`results/benchmark_results.csv`):
```
benchmark_name,mode,result,validity_time,property_time,total_time,timeout,...
seq_5,satisfy,SAT,0.15,0.02,0.27,false,...
seq_5,optimize,SAT,0.28,0.02,0.41,false,...
...
```

---

## Benchmark Results

*Note: Run `python tools/run_benchmarks.py --output results/benchmark_results.json` to generate current results. Results will vary based on hardware and Z3 version.*

### Performance Categories

- **< 1 second**: Very fast, suitable for regression testing
- **1-10 seconds**: Fast, good for CI/CD pipelines
- **10-60 seconds**: Moderate, acceptable for development
- **1-5 minutes**: Slow, use for occasional stress testing
- **> 5 minutes**: Very slow or timeout, documents solver limits

### Expected Performance Summary

| Benchmark Type | Small (5-10 tasks) | Medium (15-20 tasks) | Large (30+ tasks) |
|----------------|-------------------|---------------------|-------------------|
| Sequential (satisfy) | < 5s | 1-5 min | Timeout |
| Sequential (optimize) | < 30s | Timeout | Timeout |
| Parallel (satisfy) | < 1s | < 10s | < 60s |
| Parallel (optimize) | < 5s | < 30s | 1-5 min |
| Properties (10-20) | < 10s | < 60s | - |
| Properties (50-100) | 1-3 min | Timeout | - |
| UNSAT (all) | < 5s | < 5s | < 5s |

---

## Interpretation Guide

### Key Findings

1. **UNSAT detection is very fast** - Z3 quickly finds conflicts regardless of problem size
2. **Sequential chains don't scale well** - Strict dependencies create exponential search space
3. **Parallel patterns scale better** - Opportunities for parallel execution reduce search complexity
4. **Optimize mode is 5-20× slower** - Finding optimal solutions requires exploring more of the search space
5. **Property verification scales linearly** - Each property requires independent SMT check

### When to Use Which Mode

**Use `--mode satisfy`:**
- Initial validation of a TaskNet model
- Quick feedback during development
- CI/CD pipelines
- When any valid schedule is acceptable

**Use `--mode optimize`:**
- When you need optimal resource usage
- For final mission planning
- When schedule quality matters more than computation time
- After validating with satisfy mode first

### Performance Tips

If a benchmark times out:
1. **Try satisfy mode first** - Much faster than optimize
2. **Reduce optional tasks** - Each optional task multiplies search space
3. **Fix task durations** - Remove `duration_range` flexibility where possible
4. **Relax time windows** - Wider `start_range`/`end_range` helps solver
5. **Break sequential chains** - Allow more parallelism where feasible

---

## Comparison with Stress Tests

The benchmark suite complements stress tests (see [performance.md](performance.md)):

| Aspect | Benchmarks | Stress Tests |
|--------|-----------|--------------|
| **Purpose** | Systematic performance testing | Absolute capability limits |
| **Scale** | Small to medium (5-30 tasks) | Large (15-30 tasks) |
| **Patterns** | Synthetic, focused patterns | Realistic mission scenarios |
| **Automation** | Fully automated via runner | Manual execution |
| **Use Case** | Regression testing, CI/CD | Understanding solver limits |

**Use benchmarks for:**
- Regular performance monitoring after code changes
- Regression detection
- Demonstrating specific constraint patterns
- Quick validation (<5 minutes total)

**Use stress tests for:**
- Understanding maximum problem size
- Real-world scenario validation
- Longer-running experiments
- Identifying bottlenecks

---

## Development Workflow

### After Code Changes

1. **Quick sanity check** - Run fast benchmarks:
   ```bash
   python tools/run_benchmarks.py --output results/quick.json --mode satisfy --timeout 60
   ```

2. **Full validation** - Run complete suite:
   ```bash
   python tools/run_benchmarks.py --output results/full.json
   ```

3. **Compare results** - Check for performance regressions

### Adding New Benchmarks

Generate new benchmarks using `tools/generate_benchmark.py`:

```bash
# Sequential chain with 8 tasks
python tools/generate_benchmark.py --output tests/tasknet_files/benchmark/seq_8.tn sequential --tasks 8

# Parallel with 15 tasks, 4 timelines
python tools/generate_benchmark.py --output tests/tasknet_files/benchmark/par_15_4.tn parallel --tasks 15 --timelines 4

# Property verification with 8 tasks, 30 properties
python tools/generate_benchmark.py --output tests/tasknet_files/benchmark/prop_8_30.tn properties --tasks 8 --properties 30

# UNSAT test
python tools/generate_benchmark.py --output tests/tasknet_files/benchmark/unsat_15_resource.tn unsat --tasks 15 --conflict-type resource
```

Then run the benchmark suite to include the new benchmarks.

---

## Future Enhancements

Potential improvements to the benchmark suite:

1. **Parameterized benchmarks** - Generate benchmarks on-the-fly with various parameters
2. **Performance tracking** - Store historical results to detect regressions over time
3. **Statistical analysis** - Multiple runs with confidence intervals
4. **Profiling integration** - Identify bottlenecks within benchmarks
5. **Comparison mode** - Compare results between different Z3 versions or TaskSAT versions
6. **Filtering options** - Run subsets (e.g., only fast benchmarks, only SAT benchmarks)

---

## Conclusion

The TaskNet benchmark suite provides:
- **Systematic testing** across different problem patterns
- **Automated execution** with timeout handling
- **Performance baselines** for regression detection
- **Documentation** of scaling characteristics

Key takeaways:
- Start with small benchmarks (5-10 tasks) for quick validation
- Sequential patterns are hardest to solve
- Parallel patterns scale better
- UNSAT detection is consistently fast
- Property verification cost scales with property count

For more details on performance characteristics and optimization strategies, see [performance.md](performance.md).
