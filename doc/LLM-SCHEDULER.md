# LLM-Based Task Scheduler

## Overview

The LLM scheduler is an alternative approach to TaskSAT for generating valid task schedules. Instead of using SMT solvers (which can time out on large tasknets), it uses an iterative generate-and-test loop:

1. **LLM generates** a candidate schedule based on constraints and semantic rules
2. **Lean validator checks** if the schedule is valid
3. **Violations feed back** to the LLM for the next iteration
4. **Repeat** until a valid schedule is found

## Why This Approach Works

### The Problem with TaskSAT

TaskSAT uses Z3 SMT solver to search for valid schedules. This works well for small tasknets but has fundamental scaling limits:

- **10 tasks**: ✅ Solves in ~11 seconds
- **17 tasks**: ✅ Solves in ~8 seconds
- **62 tasks (all required)**: ❌ Timeout after 5+ hours

The bottleneck is NOT the boolean search space (optional/request tasks) but the SMT encoding complexity (zone boundaries, dense constraints).

### The LLM Approach Advantage

- **Schedule generation**: NP-hard search (but LLM uses reasoning, not exhaustive search)
- **Schedule validation**: Polynomial time (check constraints at zone boundaries)
- **Key insight**: LLM with semantic knowledge can efficiently navigate the search space

**Results:**
- **50-task MEXEC tasknet**: ✅ Valid schedule in < 30 seconds (1 attempt)
- **62-task tasknets**: ✅ Can handle (TaskSAT times out)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ 1. Convert .tn → Lean JSON                              │
│    (tools/lean_converter.py)                            │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│ 2. Analyze tasknet structure                            │
│    - Extract constraints                                │
│    - Identify type-level dependency patterns            │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│ 3. LOOP: Generate-Validate                              │
│                                                          │
│   ┌──────────────────────────────────────────┐          │
│   │ A. LLM generates candidate schedule      │          │
│   │    Input: tasknet + semantic rules +     │          │
│   │           violations from prev attempt   │          │
│   │    Output: schedule JSON                 │          │
│   └──────────────────┬───────────────────────┘          │
│                      │                                   │
│                      ▼                                   │
│   ┌──────────────────────────────────────────┐          │
│   │ B. Lean validator checks schedule        │          │
│   │    (src/lean/TaskNetExec/Main.lean)      │          │
│   │    Output: valid + violations            │          │
│   └──────────────────┬───────────────────────┘          │
│                      │                                   │
│                      ▼                                   │
│            ┌─────────┴─────────┐                        │
│            │ Valid?             │                        │
│            └─────────┬─────────┘                        │
│              Yes ✓   │   No ✗                           │
│                 │    │    │                             │
│              SUCCESS  └────┘ Feed violations back       │
│                          (loop continues)               │
└─────────────────────────────────────────────────────────┘
```

## Installation & Setup

### Prerequisites

1. **JPL GenAI API access**: You must have a subscription to JPL's managed GenAI API service
2. **genai_api package**: Must be installed at `~/Desktop/genai_api`
3. **Lean validator**: Already built in `src/lean/TaskNetExec`
4. **Python dependencies**: `requests` package

### Setup

```bash
# Install Python dependencies
pip install requests

# Authenticate with JPL GenAI API (one-time setup)
cd ~/Desktop/genai_api
uv run genai_api login --terminal

# Test authentication
uv run genai_api token
```

## Usage

### Basic Command

```bash
python3 tools/llm_scheduler.py <tasknet.tn>
```

### With Options

```bash
python3 tools/llm_scheduler.py <tasknet.tn> \
  --guidance <guidance-file.txt> \
  --max-attempts <number> \
  --model <model-id> \
  --no-visualize
```

**Parameters:**
- `<tasknet.tn>`: Path to tasknet file (required)
- `--guidance`: Optional text file with mission-specific requirements
- `--max-attempts`: Maximum generation attempts (default: 20)
- `--model`: Specific model ID (auto-detects Claude Sonnet 4 if not specified)
- `--no-visualize`: Disable automatic grouped Gantt chart generation (enabled by default)

### Examples

**1. Simple 10-task MEXEC:**
```bash
python3 tools/llm_scheduler.py test_mexec_10tasks.tn
```

**2. Large 50-task MEXEC with guidance:**
```bash
python3 tools/llm_scheduler.py ./jpl/mexec/xml/tasknet.tn \
  --guidance jpl/mexec/mexec_guidance.txt
```

**3. With more attempts:**
```bash
python3 tools/llm_scheduler.py tasknet.tn --max-attempts 15
```

## Output

### Success Case

```
🔐 Authenticating with JPL GenAI API...
   Connected to: https://gov.genai-api.jpl.nasa.gov
📋 Fetching available models...
   Using model: us-gov.anthropic.claude-sonnet-4-5-20250929-v1:0
🔄 Converting tasknet: tasknet.tn
📊 Analyzing tasknet structure...
   - 50 tasks to schedule
   - Time horizon: 0 to 250000
   - 6 type-level constraint patterns

🤖 Attempt 1/10: Generating schedule with JPL GenAI API...
   Scheduled 48 tasks
   📊 Visualization: /tmp/schedule_attempt_1.png
✅ Validating with Lean...

🎉 SUCCESS! Valid schedule found on attempt 1
   Schedule saved to: /tmp/candidate_schedule_attempt_1.json
   Final schedule: tasknet_schedule.json
   📊 Final visualization: tasknet_schedule.png
   🖼️  Opening visualization...
```

### Generated Files

- **Working file**: `/tmp/candidate_schedule_attempt_N.json` (intermediate attempts)
- **Working visualizations**: `/tmp/schedule_attempt_N.png` (grouped Gantt charts for each attempt)
- **Final output**: `<tasknet>_schedule.json` (next to input file)
- **Final visualization**: `<tasknet>_schedule.png` (grouped Gantt chart, opens automatically)

### Visualizing the Schedule

#### Automatic Visualization (Default)

Visualization is **enabled by default** and creates grouped Gantt charts during scheduling:

```bash
# Automatic visualization (default)
python3 tools/llm_scheduler.py tasknet.tn --guidance guidance.txt

# Disable visualization if not needed
python3 tools/llm_scheduler.py tasknet.tn --no-visualize
```

**What happens:**
- Creates a grouped Gantt chart for **each attempt** → `/tmp/schedule_attempt_N.png`
- Creates a final chart for the valid schedule → `tasknet_schedule.png`
- Opens the final visualization automatically in your default image viewer
- Shows progress visually as the LLM iterates

**Benefits:**
- See how schedules evolve across attempts
- Visual feedback on constraint violations
- Compare different approaches the LLM tried
- Grouped by task type for clarity
- Immediate visual confirmation of success

**Example output:**
```
🤖 Attempt 1/5: Generating schedule with JPL GenAI API...
   Scheduled 42 tasks
   📊 Visualization: /tmp/schedule_attempt_1.png
✅ Validating with Lean...
❌ Invalid schedule (3 violations)

🤖 Attempt 2/5: Generating schedule with JPL GenAI API...
   Scheduled 48 tasks
   📊 Visualization: /tmp/schedule_attempt_2.png
✅ Validating with Lean...
🎉 SUCCESS! Valid schedule found on attempt 2
   📊 Final visualization: tasknet_schedule.png
   🖼️  Opening visualization...
```

#### Manual Visualization

After generating a schedule, you can also create custom visualizations:

```bash
# Basic Gantt chart (one line per task)
python3 tools/visualize_schedule.py schedule.json

# Grouped view (tasks of same type on one line) - recommended
python3 tools/visualize_schedule.py schedule.json --grouped --output gantt.png
```

**Features:**
- Color-coded by task type
- Two modes: flat (all tasks) or grouped (by type)
- High resolution (300 DPI)
- Grid lines for easy timing analysis

The grouped view is especially useful for schedules with repeating patterns (like MEXEC's 10 communication windows).

### Schedule JSON Format

```json
{
  "tasknet": "Tasknet_1",
  "tasks": {
    "task_id_1": {"start": 100, "end": 200},
    "task_id_2": {"start": 250, "end": 350},
    ...
  },
  "included": ["optional_task_1", "request_task_2"]
}
```

## User Guidance Files

### Purpose

Guidance files allow you to specify **mission-specific requirements** that aren't captured in the formal tasknet constraints. This bridges the gap between "formally valid" and "operationally realistic."

### Example: Without vs With Guidance

**Without guidance:**
- LLM finds minimal solution: 1 shared preheat for all 10 downlinks
- Technically valid ✅
- Operationally unrealistic ❌ (equipment can't stay warm for hours)

**With guidance:**
- LLM creates 10 separate preheat instances, one before each downlink
- Technically valid ✅
- Operationally realistic ✅

### Creating a Guidance File

Guidance files are plain text with natural language instructions:

**Example: `jpl/mexec/mexec_guidance.txt`**

```
MEXEC Mission-Specific Scheduling Guidance

## Thermal Management Pattern

Each downlink window MUST have its own dedicated preheat and maintainheat sequence:

1. Preheat Phase: Schedule a comm_preheat__N instance to start exactly 100 
   time units before the corresponding orbiter_available_N window opens.

2. Maintainheat Phase: Schedule a comm_maintainheat__N instance that spans 
   the entire orbiter_available_N window.

3. Pattern: For each downlink_allN task, there should be:
   - comm_preheat__N ending when orbiter_available_N starts
   - comm_maintainheat__N spanning the orbiter_available_N window
   - downlink_allN contained within comm_maintainheat__N

DO NOT reuse a single preheat instance for multiple downlinks.

## Example Pattern

For downlink_all1 at orbiter window [360, 660]:
- comm_preheat__1: [260, 360]  (100 units before window)
- comm_maintainheat__1: [360, 660]  (spans the window)
- downlink_all1: [400, 500]  (contained within maintainheat)

Repeat this pattern for all 10 downlink windows.
```

### Best Practices for Guidance Files

1. **Be specific**: "Each downlink needs its own preheat" is better than "manage thermal resources"
2. **Include examples**: Show the desired pattern with concrete timings
3. **Explain why**: "equipment can't stay warm for hours" helps the LLM understand intent
4. **Use structure**: Organize by topic (thermal management, power management, etc.)
5. **Keep it concise**: Focus on high-level patterns, not every detail

### What to Include in Guidance

**DO include:**
- Operational patterns (preheat before each operation)
- Resource management strategies (when to recharge batteries)
- Timing conventions (spacing between activities)
- Safety margins (buffer times)
- Mission-specific preferences (prioritize science over housekeeping)

**DON'T include:**
- Things already in tasknet constraints (after/containedin relationships)
- Exact start/end times (LLM should figure these out)
- Overly prescriptive details (let LLM have flexibility)

## Semantic Rules

The LLM is given semantic rules extracted from the Lean validator and TaskSAT implementation. See [SEMANTIC-RULES.md](SEMANTIC-RULES.md) for the complete reference.

**Key rules the LLM understands:**

1. **Task timing**: [start, end) half-open intervals, must satisfy all range constraints
2. **Duration preference**: Prefer shorter durations near durrng.low to free up resources (except for valuable request tasks)
3. **After constraints**: `A.end ≤ B.start` (equal is valid)
4. **Containedin**: Child interval must be subset of parent
5. **Type-level constraints**: Existential semantics (need at least one matching instance)
6. **Invariant timing**: Checked at (s, e], not [s, e] (critical for atomic pattern)
7. **Impact application**: PRE at start, MAINT throughout, POST at end
8. **Zero-duration tasks**: Valid but tricky edge case
9. **Request task optimization**: Schedule as many request task instances as possible (they represent user-desired activities)

These rules are included in the prompt automatically, so the LLM knows how to generate valid schedules.

## MEXEC Dynamic Instance Creation

### What It Is

MEXEC (and the LLM scheduler) support **dynamic instance creation from taskdefs**. This bridges the gap between pure scheduling and planning:

- **Pure scheduling**: You have a fixed set of task instances (e.g., 10 downlink tasks) and assign them start/end times
- **Planning + Scheduling**: You have task definitions (templates) and must decide:
  1. **How many instances to create** (planning decision)
  2. **When to schedule them** (scheduling decision)

### How It Works

**Example scenario:**

```
taskdef comm_preheat { ... }           # Template exists
taskdef comm_maintainheat { ... }     # Template exists

task downlink_all1 {
  after comm_preheat;                  # Type-level constraint
  containedin comm_maintainheat;       # Type-level constraint
}
# ... 9 more downlinks (downlink_all2 through downlink_all10)

# BUT: No comm_preheat or comm_maintainheat instances in tasknet!
```

**The problem**: The tasknet has 10 downlinks that each require thermal management, but zero thermal management instances.

**The solution**:
1. **LLM decides**: "I need 10 comm_preheat instances (one per downlink) and 10 comm_maintainheat instances"
2. **LLM creates**: Instances named `comm_preheat__1` through `__10`, `comm_maintainheat__1` through `__10`
3. **LLM schedules**: Each instance gets start/end times that satisfy constraints and guidance
4. **Validator accepts**: The system automatically instantiates these tasks from their taskdefs before validation

**Result**: Schedule with 24 original tasks + 20 dynamically created thermal instances = 44 schedulable tasks

### When to Use

This feature is **automatic** - no special flags or configuration needed. The LLM will create instances whenever:

- A task has a type-level constraint (e.g., `after comm_preheat`)
- But no instances of that taskdef exist in the tasknet
- The guidance or constraints suggest instances are needed

### Guidance for Dynamic Instances

User guidance files (like `jpl/mexec/mexec_guidance.txt`) help the LLM make good planning decisions:

```
MEXEC Mission-Specific Scheduling Guidance

## Thermal Management Pattern

Each downlink window MUST have its own dedicated preheat and maintainheat sequence:
- Preheat 100 units before window opens
- Maintainheat spanning entire window
- Downlink contained within maintainheat

DO NOT reuse thermal resources across multiple downlinks.
```

This tells the LLM:
- **How many**: One thermal sequence per downlink (10 downlinks → 10 sequences)
- **Naming**: Use pattern like `comm_preheat__1`, `comm_preheat__2`, etc.
- **Timing**: Relative positions (100 units before, spanning window)

### Technical Details

**Under the hood:**

1. **Converter** ([tools/lean_converter.py](../../tools/lean_converter.py)): Separates taskdefs from instances, outputs both to JSON
2. **LLM prompt**: Includes MEXEC rule explaining dynamic instantiation (see [SEMANTIC-RULES.md §2.4](SEMANTIC-RULES.md#L85))
3. **Schedule generation**: LLM creates instances in schedule JSON with names matching taskdefs
4. **Validation**: Before calling Lean, `augment_tasknet_with_dynamic_instances()` finds schedule tasks that don't exist in tasknet, matches them to taskdefs by prefix, and instantiates them
5. **Lean validator**: Receives augmented tasknet with all instances, validates normally

**Example flow:**

```python
# LLM generates schedule with:
{
  "tasks": {
    "downlink_all1": {"start": 370, "end": 400},
    "comm_preheat__1": {"start": 260, "end": 360},      # ← Created by LLM
    "comm_maintainheat__1": {"start": 360, "end": 660}, # ← Created by LLM
    ...
  },
  "included": ["comm_preheat__1", "comm_maintainheat__1", ...]
}

# Validator augments tasknet:
# - Finds comm_preheat__1 in schedule but not in tasknet.tasks
# - Matches prefix "comm_preheat__1" → taskdef "comm_preheat"
# - Creates instance: inherits all constraints from taskdef
# - Adds to tasknet.tasks before validation
# - Lean validates the complete schedule
```

**Naming convention**: `{taskdef_name}__{number}` (double underscore + instance number)

### Example: 24-Task MEXEC

The 24-task MEXEC tasknet demonstrates this feature:

**Input tasknet**:
- 21 required task instances (orbiter windows, downlinks)
- 3 request tasks (global_localization, battery_recharge, route_segment)
- 12 task definitions (templates for thermal management, localization, etc.)
- **0 thermal management instances**

**LLM generates**:
- 10 comm_preheat instances
- 10 comm_maintainheat instances
- 2 global_localization thermal instances
- 2 route_segment thermal instances
- Total: **48 tasks** in final schedule

**Result**: Valid schedule found in 1 attempt (~15 seconds)

### Planning vs Scheduling

This makes the LLM scheduler a **planning + scheduling system**:

| Decision Type | Example | Who Decides |
|---------------|---------|-------------|
| Planning | "Create 10 comm_preheat instances, not 1" | LLM |
| Scheduling | "comm_preheat__1 runs at [260, 360]" | LLM |
| Validation | "Does comm_preheat__1 satisfy all constraints?" | Lean |

The LLM makes both architectural decisions (how many instances) and timing decisions (when to run them), while Lean enforces correctness.

## Troubleshooting

### Authentication Issues

**Error**: `Could not find JPL GenAI API base URL`

**Fix**:
```bash
# Re-authenticate
cd ~/Desktop/genai_api
uv run genai_api login --terminal
```

### No Valid Schedule Found

**Error**: `FAILED: Could not find valid schedule after N attempts`

**Possible causes:**
1. **Overconstrained tasknet**: No valid schedule exists
2. **Complex guidance**: Guidance conflicts with formal constraints
3. **Need more attempts**: Try `--max-attempts 20`

**Debug approach:**
1. Check violations from last attempt: `/tmp/candidate_schedule_attempt_N.json`
2. Simplify or remove guidance temporarily
3. Try with fewer optional/request tasks

### Model Not Available

**Error**: `No Claude models found in your subscription`

**Fix**:
```bash
# Check available models
cd ~/Desktop/genai_api
uv run python3 examples/example.py | grep "Available models"

# Use a specific model
python3 tools/llm_scheduler.py tasknet.tn --model <model-id>
```

## Performance

### Expected Iteration Counts

Based on testing:

| Tasknet Size | Complexity | Expected Attempts |
|--------------|------------|-------------------|
| 10-20 tasks  | Simple     | 1-3 attempts      |
| 20-50 tasks  | Medium     | 1-5 attempts      |
| 50+ tasks    | Complex    | 3-10 attempts     |

**Time per attempt**: ~2-5 seconds (API call + validation)

**Total time**: Usually < 30 seconds even for large tasknets

### Comparison to TaskSAT

| Approach | 10 tasks | 50 tasks | 62 tasks |
|----------|----------|----------|----------|
| TaskSAT  | 11 sec   | ?        | 5+ hrs (timeout) |
| LLM      | 2 sec    | 30 sec   | ~1 min   |

LLM approach scales to large tasknets that TaskSAT cannot handle.

## Limitations

### What the LLM Approach Can't Do

1. **Prove optimality**: LLM finds *a* valid schedule, not necessarily the *best* one
2. **Guarantee success**: If no valid schedule exists, it will exhaust attempts and fail
3. **Handle conflicting guidance**: If guidance contradicts formal constraints, it will struggle

### When to Use TaskSAT Instead

Use TaskSAT (SMT approach) when:
- Tasknet is small (< 20 tasks)
- You need proof of optimality (minimize makespan, maximize optional tasks)
- You want to prove no valid schedule exists (unsatisfiability)

Use LLM scheduler when:
- Tasknet is large (> 20 tasks)
- You just need *a* valid schedule quickly
- You have mission-specific preferences (via guidance)

## Available Tools

The LLM scheduler comes with several supporting tools:

### 1. Schedule Generator (`llm_scheduler.py`)

Main tool for generating schedules:

```bash
python3 tools/llm_scheduler.py tasknet.tn \
  --guidance guidance.txt \
  --max-attempts 10
```

**What it does:**
- Converts tasknet to Lean JSON
- Iteratively generates and validates schedules
- Outputs valid schedule as JSON

### 2. Schedule Visualizer (`visualize_schedule.py`)

Creates Gantt charts from schedules:

```bash
python3 tools/visualize_schedule.py schedule.json --grouped -o gantt.png
```

**Features:**
- Two modes: flat (one line per task) or grouped (by type)
- Color-coded by task type
- High resolution (300 DPI)
- Grid lines for timing analysis

**Task type colors:**
- Orbiter: Blue
- Preheat: Red
- Maintainheat: Orange
- Downlink: Green
- Localization: Purple
- Battery: Teal
- Route: Pink

### 3. TaskNet Converter (`lean_converter.py`)

Converts .tn files to Lean JSON format:

```bash
python3 tools/lean_converter.py tasknet.tn output.json
```

**Used internally by llm_scheduler.py**, but can be run standalone for inspection.

### 4. Lean Validator (Direct)

Validate a schedule directly with Lean semantics:

```bash
cd src/lean/TaskNetExec
lake exe tasknet-validate --tasknet tasknet.json --schedule schedule.json
```

**Output:** JSON with `valid` (true/false) and detailed `violations` array.

### Complete Workflow Example

```bash
# 1. Generate schedule with guidance
python3 tools/llm_scheduler.py ./jpl/mexec/xml/tasknet.tn \
  --guidance jpl/mexec/mexec_guidance.txt \
  --max-attempts 10

# Output: ./jpl/mexec/xml/tasknet_schedule.json

# 2. Visualize the schedule
python3 tools/visualize_schedule.py ./jpl/mexec/xml/tasknet_schedule.json \
  --grouped \
  --output mexec_schedule_gantt.png

# 3. View the chart
open mexec_schedule_gantt.png

# 4. (Optional) Manually validate with Lean
python3 tools/lean_converter.py ./jpl/mexec/xml/tasknet.tn /tmp/tasknet.json
cd src/lean/TaskNetExec
lake exe tasknet-validate \
  --tasknet /tmp/tasknet.json \
  --schedule ../../jpl/mexec/xml/tasknet_schedule.json
```

## Extending the Scheduler

### Adding New LLM Providers

Currently supports JPL GenAI API. To add others:

1. Modify `generate_schedule_with_llm()` to use different API endpoint
2. Update authentication in `main()`
3. Test with your provider's models

### Custom Validation

The validator is the Lean executor in `src/lean/TaskNetExec/Main.lean`. To customize:

1. Modify validation logic in `Semantics.lean`
2. Rebuild: `cd src/lean/TaskNetExec && lake build`
3. Test: `lake exe tasknet-validate --tasknet ... --schedule ...`

### Guidance Templates

Create reusable guidance templates for common mission types:

```bash
doc/guidance/
├── thermal_management.txt
├── power_management.txt
└── comm_windows.txt
```

Combine them: `cat doc/guidance/*.txt > my_guidance.txt`

## References

- **Semantic rules**: [SEMANTIC-RULES.md](SEMANTIC-RULES.md)
- **Lean validator**: [src/lean/TaskNetExec/](../src/lean/TaskNetExec/)
- **TaskSAT comparison**: [SMT encoding docs](smt-encoding.md)
- **Example guidance**: [jpl/mexec/mexec_guidance.txt](../jpl/mexec/mexec_guidance.txt)
