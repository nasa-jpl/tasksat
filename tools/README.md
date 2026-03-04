# TaskNet Benchmark Generator

A command-line tool for generating synthetic TaskNet benchmarks with predictable behavior for performance evaluation and testing.

## Overview

The generator creates `.tn` files using generic names (T1, T2, ..., tl1, tl2, ...) that don't need to make realistic domain sense but have known characteristics useful for testing.

## Installation

No installation required. The script uses only Python standard library.

```bash
# Make executable (already done)
chmod +x tools/generate_benchmark.py
```

## Usage

```bash
python tools/generate_benchmark.py <mode> [options] --output <file>
```

### Modes

#### 1. Sequential Chain

Generates tasks with resource dependencies forcing sequential execution.

```bash
python tools/generate_benchmark.py sequential \
  --tasks 15 \
  --optional-freq 3 \
  --duration-min 1 \
  --duration-max 6 \
  --charge-rate 1.0 \
  --requirement-step 5.0 \
  --horizon 150 \
  --output tests/tasknet_files/benchmark/seq_15.tn
```

**Parameters:**
- `--tasks N`: Number of tasks (default: 15)
- `--optional-freq K`: Make every Kth task optional (default: 3)
- `--duration-min MIN`: Minimum duration (default: 1)
- `--duration-max MAX`: Maximum duration (default: 6)
- `--charge-rate R`: Battery charge rate (default: 1.0)
- `--requirement-step K`: Battery requirement step size (default: 5.0)
- `--horizon H`: Time horizon (default: N*10)

**Pattern:**
- Tasks T1-TN with T_i requiring battery >= (i-1)*K
- Each task charges battery at rate R during execution
- Forces sequential execution: T1 → T2 → ... → TN
- Variable durations create exponential search space

**Expected behavior:**
- SAT with sequential schedule
- Timing: ~2-3 minutes for 15 tasks in satisfy mode
- TIMEOUT in optimize mode for 15+ tasks

#### 2. Parallel Resources

Generates tasks that can execute in parallel across multiple resource timelines.

```bash
python tools/generate_benchmark.py parallel \
  --tasks 20 \
  --timelines 5 \
  --parallelism 3 \
  --horizon 200 \
  --output tests/tasknet_files/benchmark/par_20_5.tn
```

**Parameters:**
- `--tasks N`: Number of tasks (default: 20)
- `--timelines M`: Number of resource timelines (default: 5)
- `--parallelism P`: Target parallelism factor 1-10 (default: 3)
- `--horizon H`: Time horizon (default: max(200, N*10))

**Pattern:**
- M timelines (tl1, tl2, ..., tlM) with mixed types (rate, claim, cumul, state)
- Tasks distributed across timelines
- Allows ~N/P concurrent task execution

**Expected behavior:**
- SAT with parallel schedule
- Should complete faster than sequential chains
- Good for testing parallel scheduling performance

#### 3. Over-Constrained UNSAT

Generates deliberately unsatisfiable problems to test conflict detection.

```bash
python tools/generate_benchmark.py unsat \
  --tasks 30 \
  --conflict-type resource \
  --horizon 200 \
  --output tests/tasknet_files/benchmark/unsat_30.tn
```

**Parameters:**
- `--tasks N`: Number of tasks (required)
- `--conflict-type TYPE`: Type of conflict (default: resource)
  - `resource`: Over-subscribe shared resource
  - `temporal`: Impossible time windows
  - `dependency`: Circular dependencies via resources
  - `mixed`: Combination of conflicts
- `--horizon H`: Time horizon (default: 200)

**Pattern:**
- Creates conflicting constraints that make the problem unsatisfiable
- Different conflict types test different UNSAT detection paths

**Expected behavior:**
- UNSAT (no valid schedule exists)
- Quick conflict detection (<5 seconds for most problems)
- Tests Z3's conflict analysis capabilities

#### 4. Property Verification

Generates tasks with many temporal properties to stress-test verification.

```bash
python tools/generate_benchmark.py properties \
  --tasks 10 \
  --properties 50 \
  --horizon 200 \
  --output tests/tasknet_files/benchmark/prop_10_50.tn
```

**Parameters:**
- `--tasks N`: Number of tasks (default: 10)
- `--properties P`: Number of temporal properties (default: 20)
- `--horizon H`: Time horizon (default: 200)

**Pattern:**
- Simple task structure (easy to find valid schedule)
- Many temporal properties (safety, liveness, implications)
- Mix of `always`, `eventually`, and implication patterns

**Expected behavior:**
- SAT with valid schedule
- Property verification time scales with number of properties
- Good for measuring average time per property

## Examples

### Generate Sequential Chain (15 tasks)

```bash
python tools/generate_benchmark.py sequential --tasks 15 \
  --output tests/tasknet_files/benchmark/seq_15.tn
```

Should produce similar performance to `stress7_sequential_15.tn` (~2:40 in satisfy mode).

### Generate Parallel Resource Test (20 tasks, 5 timelines)

```bash
python tools/generate_benchmark.py parallel --tasks 20 --timelines 5 \
  --output tests/tasknet_files/benchmark/par_20_5.tn
```

### Generate UNSAT Test (30 tasks)

```bash
python tools/generate_benchmark.py unsat --tasks 30 \
  --output tests/tasknet_files/benchmark/unsat_30.tn
```

Should detect UNSAT quickly (<5 seconds).

### Generate Property Verification Test (10 tasks, 50 properties)

```bash
python tools/generate_benchmark.py properties --tasks 10 --properties 50 \
  --output tests/tasknet_files/benchmark/prop_10_50.tn
```

Good for measuring property verification performance.

## Testing Generated Benchmarks

After generating a benchmark, test it with the verifier:

```bash
# Test in satisfy mode
python src/smt/tasknet_verifier.py tests/tasknet_files/benchmark/seq_15.tn --mode satisfy

# Test in optimize mode
python src/smt/tasknet_verifier.py tests/tasknet_files/benchmark/par_20_5.tn --mode optimize
```

## Output Format

Generated files include:
1. **Header comments** with:
   - Generator command used
   - Expected behavior (SAT/UNSAT, timing estimates)
   - Key characteristics (tasks, timelines, properties)
2. **TaskNet definition** with generic names
3. **Proper formatting** and indentation

Example header:
```
# Generated by: python tools/generate_benchmark.py sequential --tasks 15
#
# Sequential Chain Benchmark
#
# Configuration:
# - 15 tasks (11 required, 4 optional)
# - 1 timeline (battery)
# - Sequential chain pattern: T1 → T2 → ... → T15
# - Variable durations [1, 6]
#
# Expected behavior:
# - Tasks must execute sequentially
# - T_i requires battery >= 5.0*(i-1)
# - Each task charges battery at +1.0/time
```

## Use Cases

### 1. Performance Evaluation

Generate benchmark suites for papers:
```bash
# Sequential chains at different scales
for n in 10 15 20; do
  python tools/generate_benchmark.py sequential --tasks $n \
    --output tests/tasknet_files/benchmark/seq_$n.tn
done

# Parallel resources at different scales
for n in 10 20 30; do
  python tools/generate_benchmark.py parallel --tasks $n --timelines 5 \
    --output tests/tasknet_files/benchmark/par_${n}_5.tn
done
```

### 2. Testing Conflict Detection

Generate various UNSAT problems:
```bash
for type in resource temporal dependency mixed; do
  python tools/generate_benchmark.py unsat --tasks 30 --conflict-type $type \
    --output tests/tasknet_files/benchmark/unsat_30_$type.tn
done
```

### 3. Property Verification Scaling

Test how property verification scales:
```bash
# Fixed tasks, varying properties
for p in 10 20 50 100; do
  python tools/generate_benchmark.py properties --tasks 10 --properties $p \
    --output tests/tasknet_files/benchmark/prop_10_$p.tn
done
```

## Design Patterns

### Sequential Chain Pattern
- **Goal**: Test worst-case complexity
- **Structure**: Resource dependency forces ordering
- **Scaling**: Non-linear (exponential blowup with optional tasks + duration ranges)
- **Use**: Identify performance limits

### Parallel Resource Pattern
- **Goal**: Test concurrent scheduling
- **Structure**: Multiple resources allow parallelism
- **Scaling**: Better than sequential (sub-linear with good parallelism)
- **Use**: Show best-case performance

### UNSAT Pattern
- **Goal**: Test conflict detection
- **Structure**: Deliberately conflicting constraints
- **Scaling**: Very fast (conflict detection efficient)
- **Use**: Validate UNSAT detection

### Property Verification Pattern
- **Goal**: Measure per-property verification cost
- **Structure**: Simple base problem + many properties
- **Scaling**: Linear with number of properties (ideally)
- **Use**: Property verification benchmarking

## Tips

1. **Start small**: Test with smaller parameters first before generating large benchmarks
2. **Compare to existing**: Use stress tests as reference points
3. **Document results**: Add performance notes as comments in generated files after testing
4. **Version control**: Generated benchmarks can be checked in if they're useful for regression testing

## Related Files

- `tests/tasknet_files/stress/` - Manually-created stress tests (good reference examples)
- `tests/tasknet_files/examples/` - Example tasknets with domain-specific names
- `tests/tasknet_files/valid/` - Small validation test cases
- `doc/performance.md` - Performance characteristics and scaling guidelines
