# LLM-Based Task Scheduler for TaskSAT

This is an alternative approach to the SMT-based TaskSAT verifier for generating valid task schedules.

## Overview

The LLM scheduler uses a **generate-and-test loop** with the Lean validator, scaling to larger tasknets where SMT solving becomes intractable.

**Key capability**: This is a **planning + scheduling system** (not just scheduling). The LLM can dynamically create task instances from taskdefs, deciding both *how many* instances to create and *when* to schedule them. This MEXEC semantic enables flexible mission planning with operational guidance.

### Architecture

```
┌────────────────────┐
│   TaskNet (.tn)    │
└─────────┬──────────┘
          │
          v
┌─────────────────────┐
│  Lean JSON Format   │ ← Converted from .tn
└─────────┬───────────┘
          │
          v
    ╔═══════════════════════╗
    ║   GENERATE-VALIDATE   ║
    ║        LOOP           ║
    ╚═══════════════════════╝
          │
          v
    ┌──────────────────┐
    │ LLM generates    │ ← Planning: creates instances from taskdefs
    │ candidate        │ ← Scheduling: assigns start/end times
    └────────┬─────────┘
             │
             v
    ┌──────────────────┐
    │ Lean validates   │ ← Polynomial-time check
    └────────┬─────────┘
             │
       Valid? │
          ┌───┴───┐
          │       │
        Yes      No
          │       │
          v       v
      SUCCESS  Feed violations back
                  │
                  └──> Retry generation
```

## Why an Alternative Approach?

TaskSAT (SMT-based) works well for small to medium tasknets but has fundamental scaling limits:
- **10-20 tasks**: ✅ Solves in seconds
- **50+ tasks**: ❌ Can timeout after hours

The LLM approach uses Claude (via JPL's GenAI API) to generate candidate schedules, then validates them with the Lean semantics:

- **Schedule generation**: Uses LLM reasoning instead of exhaustive SMT search
- **Schedule validation**: Polynomial-time check (not NP-hard search)
- **Iteration**: LLM learns from violation feedback
- **Optimization heuristics**: Prefers shorter durations and maximizes request tasks

**Performance on large tasknets:**
- **50-task MEXEC**: ✅ Valid schedule in ~30 seconds (1 attempt)
- **62-task cases**: ✅ Succeeds where TaskSAT times out

## Quick Start

### Prerequisites

1. **JPL GenAI API access**: You must have a subscription to JPL's managed GenAI API service
2. **genai_api package**: Must be installed at `~/Desktop/genai_api`
3. **Lean validator**: Already built in `src/lean/TaskNetExec`

### Basic Usage

```bash
# Simple usage (automatic visualization)
python3 tools/llm_scheduler.py tasknet.tn

# With mission-specific guidance
python3 tools/llm_scheduler.py tasknet.tn --guidance guidance.txt

# Without visualization
python3 tools/llm_scheduler.py tasknet.tn --no-visualize

# With more attempts
python3 tools/llm_scheduler.py tasknet.tn --max-attempts 15
```

**Output**: 
- `tasknet_schedule.json` with valid schedule
- `tasknet_schedule.png` (automatic, grouped Gantt chart, opens automatically)

### Example Session

```bash
$ python3 tools/llm_scheduler.py test_mexec_10tasks.tn

🔐 Authenticating with JPL GenAI API...
   Connected to: https://gov.genai-api.jpl.nasa.gov
📋 Fetching available models...
   Using model: us-gov.anthropic.claude-sonnet-4-5-20250929-v1:0
🔄 Converting tasknet: test_mexec_10tasks.tn
📊 Analyzing tasknet structure...
   - 9 tasks to schedule
   - Time horizon: 0 to 50000

🤖 Attempt 1/10: Generating schedule with JPL GenAI API...
   Scheduled 9 tasks
   📊 Visualization: /tmp/schedule_attempt_1.png
✅ Validating with Lean...

🎉 SUCCESS! Valid schedule found on attempt 1
   Schedule saved to: test_mexec_10tasks_schedule.json
   📊 Final visualization: test_mexec_10tasks_schedule.png
   🖼️  Opening visualization...
```

### Visualizing Schedules

After generating a schedule, visualize it as a Gantt chart:

```bash
# Grouped view (recommended)
python3 tools/visualize_schedule.py test_mexec_10tasks_schedule.json --grouped

# Open the chart
open gantt.png
```

The visualization tool creates color-coded Gantt charts showing task timing and relationships.

## User Guidance Files

The LLM scheduler supports **guidance files** that specify mission-specific operational requirements not captured in formal constraints:

**Example: `guidance.txt`**

```
Each downlink window MUST have its own dedicated thermal 
preparation sequence:
- Preheat 100 units before window opens
- Maintainheat spanning entire window  
- Downlink contained within maintainheat

DO NOT reuse thermal resources across multiple downlinks.
```

This bridges the gap between "formally valid" and "operationally realistic."

**Without guidance:**
- LLM finds minimal solution: 1 shared preheat for all 10 downlinks
- Technically valid ✅, but operationally unrealistic ❌

**With guidance:**
- LLM creates 10 separate preheat instances, one before each downlink
- Technically valid ✅ and operationally realistic ✅

## When to Use Which Approach?

### Use TaskSAT (SMT) when:
- Tasknet is small (< 20 tasks)
- You need proof of optimality (minimize makespan)
- You want to prove no solution exists (UNSAT)

### Use LLM Scheduler when:
- Tasknet is large (> 20 tasks)
- You need *a* valid schedule quickly
- You have mission-specific preferences (via guidance)
- TaskSAT times out

## Performance Comparison

| Approach | 10 tasks | 50 tasks | 62 tasks |
|----------|----------|----------|----------|
| TaskSAT  | 11 sec   | ?        | 5+ hrs (timeout) |
| LLM      | 2 sec    | 30 sec   | ~1 min   |

The LLM approach scales to large tasknets that TaskSAT cannot handle.

## Documentation

- **[LLM Scheduler Complete Guide](doc/LLM-SCHEDULER.md)** - Full reference with architecture, installation, usage, and troubleshooting
- **[Guidance Files User Guide](doc/GUIDANCE-FILES.md)** - How to write effective mission-specific guidance
- **[Semantic Rules](doc/SEMANTIC-RULES.md)** - Scheduling semantics the LLM follows (extracted from Lean and TaskSAT)

## Key Features

✅ **Scales to large tasknets** (50+ tasks) where TaskSAT times out  
✅ **Fast iteration** (~2-5 seconds per attempt)  
✅ **Mission-specific guidance** via natural language files  
✅ **MEXEC dynamic instances** - LLM creates task instances from templates (planning + scheduling)  
✅ **Maximizes request tasks** (user-desired activities)  
✅ **Detailed violation feedback** for debugging  
✅ **JPL GenAI API integration** (Claude Sonnet 4.5)  
✅ **Lean validator** ensures correctness  

## Example: MEXEC Scheduling

The LLM scheduler successfully generates valid schedules for MEXEC tasknets with thermal management, communication windows, and power constraints.

**Key capability**: Dynamic instance creation from taskdefs. The LLM decides how many instances to create (a planning decision) and when to schedule them (a scheduling decision).

**Example: 24-task MEXEC**:
- Input: 21 required tasks + 3 requests + 12 taskdefs (no thermal instances)
- LLM creates: 20 thermal management instances (comm_preheat, comm_maintainheat, etc.)
- Output: Valid 48-task schedule found in 1 attempt (~15 seconds)

**With guidance** (using mexec_guidance.txt):
- Proper thermal pattern: dedicated preheat/maintainheat per window
- Valid and operationally realistic
- Generated in 1 attempt (~30 seconds)

See [mexec_guidance.txt](mexec_guidance.txt) for the complete guidance file used.

## Command Line Reference

### LLM Scheduler

```bash
python3 tools/llm_scheduler.py <tasknet.tn> \
  [--guidance <file.txt>] \
  [--max-attempts <N>] \
  [--model <model-id>] \
  [--no-visualize]
```

**Options:**
- `--guidance`: Text file with mission-specific requirements (optional)
- `--max-attempts`: Maximum generation attempts (default: 20)
- `--model`: Specific Claude model ID (auto-detects if not specified)
- `--no-visualize`: Disable automatic grouped Gantt chart generation (enabled by default)

### Schedule Visualization

```bash
python3 tools/visualize_schedule.py <schedule.json> \
  [--output <file.png>] \
  [--grouped]
```

**Options:**
- `--output` / `-o`: Output PNG file (default: gantt.png)
- `--grouped` / `-g`: Group tasks of same type on one line (recommended)

**Example workflow:**
```bash
# Generate schedule
python3 tools/llm_scheduler.py tasknet.tn --guidance guidance.txt

# Visualize it
python3 tools/visualize_schedule.py tasknet_schedule.json --grouped -o schedule_gantt.png

# View
open schedule_gantt.png
```

### Other Tools

```bash
# Convert tasknet to Lean JSON format
python3 tools/lean_converter.py tasknet.tn output.json

# Validate schedule directly with Lean
cd src/lean/TaskNetExec
lake exe tasknet-validate --tasknet tasknet.json --schedule schedule.json
```

## Architecture Details

### Generate-Validate Loop

1. **LLM generates** candidate schedule based on:
   - Tasknet constraints (extracted and formatted)
   - Semantic rules (from Lean/TaskSAT)
   - User guidance (if provided)
   - Violations from previous attempts (if any)

2. **Lean validates** schedule:
   - Converts to Lean JSON format
   - Executes sparse semantics validator
   - Returns: valid (true/false) + detailed violations

3. **Iterate**:
   - If valid: SUCCESS, save schedule
   - If invalid: feed violations back to LLM, retry

### Semantic Knowledge

The LLM is given semantic rules extracted from the formal specifications:

- Task timing constraints (ranges, intervals)
- Temporal dependencies (after, containedin)
- Type-level constraints (existential semantics)
- Invariant timing (checked at (s, e], not [s, e])
- Impact application order (PRE, MAINT, POST)
- Timeline state evolution

See [doc/SEMANTIC-RULES.md](doc/SEMANTIC-RULES.md) for complete details.

## Getting Help

- **Installation issues**: See [doc/LLM-SCHEDULER.md](doc/LLM-SCHEDULER.md) troubleshooting section
- **Authentication problems**: Check JPL GenAI API setup at `~/Desktop/genai_api`
- **Writing guidance**: See [doc/GUIDANCE-FILES.md](doc/GUIDANCE-FILES.md) for best practices
- **Understanding violations**: Check semantic rules in [doc/SEMANTIC-RULES.md](doc/SEMANTIC-RULES.md)

## Summary

The LLM scheduler provides a practical alternative to SMT-based scheduling for large tasknets. By combining LLM generation with formal Lean validation, it achieves both **scalability** (handles 50+ task tasknets) and **correctness** (validated against formal semantics).

**Try it now:**
```bash
python3 tools/llm_scheduler.py test_mexec_10tasks.tn
```
