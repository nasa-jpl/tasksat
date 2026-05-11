# User Guide: Guidance Files

## What Are Guidance Files?

Guidance files let you tell the LLM scheduler about **mission-specific requirements** that aren't captured in the formal tasknet constraints.

Think of them as "soft constraints" or "operational preferences" that guide the LLM toward schedules that are not just valid, but also **realistic and practical**.

## Why Use Guidance Files?

### The Problem

The formal tasknet defines hard constraints:
- Task A must finish before task B starts
- Task C must be contained within task D
- Timeline values must stay within bounds

But it doesn't capture things like:
- "Each operation needs its own thermal preparation cycle"
- "Don't schedule power-intensive tasks back-to-back"
- "Leave 10-minute buffer between communication windows"

**Without guidance**, the LLM finds a **minimal** solution that satisfies formal constraints but may not be operationally realistic.

**With guidance**, the LLM finds a **practical** solution that matches mission operations.

### Example: MEXEC Thermal Management

**Without guidance:**
```
LLM thinks: "The constraint says 'after comm_preheat'. I can use ONE 
preheat at time 0, and all 10 downlinks will be after it!"
```

Result: 1 preheat, 10 downlinks (valid ✅, but unrealistic ❌)

**With guidance:**
```
Guidance says: "Each downlink window MUST have its own dedicated preheat 
100 time units before the window opens."
```

Result: 10 preheats, one per downlink (valid ✅, realistic ✅)

## Creating a Guidance File

### Format

Plain text file with natural language instructions. No special syntax required.

### Structure

Organize by topic with clear headers:

```
Mission Name Scheduling Guidance

## Topic 1: Thermal Management
[Instructions for thermal patterns]

## Topic 2: Power Management  
[Instructions for battery usage]

## Topic 3: Communication Windows
[Instructions for comm scheduling]
```

### Writing Style

**Be direct and specific:**

✅ **GOOD**: "Each downlink window MUST have its own dedicated preheat instance starting 100 time units before the window opens."

❌ **BAD**: "Thermal management should be considered when scheduling communication operations."

**Use examples:**

✅ **GOOD**: 
```
For downlink_all1 at window [360, 660]:
- comm_preheat__1: [260, 360]
- comm_maintainheat__1: [360, 660]
- downlink_all1: [400, 500]
```

❌ **BAD**: "Organize thermal tasks appropriately."

**Explain the "why":**

✅ **GOOD**: "DO NOT reuse a single preheat instance for multiple downlinks. Equipment cannot maintain operational temperature for extended periods."

❌ **BAD**: "Don't share preheats."

## What to Include

### DO Include

✅ **Operational patterns**
- "Preheat before each operation"
- "Maintainheat spans the operation window"
- "Cooldown after intensive activities"

✅ **Resource management**
- "Recharge battery when SOC drops below 20%"
- "Don't schedule power-intensive tasks back-to-back"
- "Leave 5-minute recovery time between activities"

✅ **Timing conventions**
- "Space communication windows 660 time units apart"
- "Schedule housekeeping tasks during gaps"
- "Avoid scheduling during predicted high-radiation periods"

✅ **Safety margins**
- "Leave 10-minute buffer before critical operations"
- "Don't schedule within 100 units of battery depletion"
- "Allow 50 units for unexpected delays"

✅ **Mission priorities**
- "Prioritize science observations over housekeeping"
- "Ensure downlink before data buffer fills"
- "Complete navigation updates before maneuvers"

### DON'T Include

❌ **Things already in tasknet constraints**
- "Task A must finish before task B" → This is an `after` constraint
- "Task C must be contained in task D" → This is a `containedin` constraint
- "Timeline X must stay in range [0, 100]" → This is a timeline bound

❌ **Exact start/end times**
- "Schedule downlink_all1 at exactly t=400" → Too prescriptive, LLM can't adapt
- Instead: "Schedule downlinks 40 units after window opens"

❌ **Low-level implementation details**
- "Use zone-based sparse semantics" → This is validator internals
- "Check invariants at (s,e]" → This is semantic rules (already in prompt)

## Example: Complete Guidance File

**File**: `thermal_and_power.txt`

```
Spacecraft Operations Scheduling Guidance

## Thermal Management

Each power-intensive operation requires a dedicated thermal preparation sequence:

1. **Preheat Phase**: 
   - Schedule a preheat task 100 time units before the operation
   - Duration: 100 time units
   - Example: For operation at t=500, preheat: [400, 500]

2. **Maintainheat Phase**:
   - Schedule a maintainheat task spanning the operation window
   - Must cover entire operation duration
   - Example: For operation [500, 600], maintainheat: [500, 600]

3. **Pattern per Operation**:
   - One preheat before window opens
   - One maintainheat spanning window
   - Operation contained within maintainheat

DO NOT reuse thermal tasks across multiple operations. Each requires 
independent thermal management.

## Power Management

Battery management guidelines:

1. **Recharge Timing**:
   - Schedule recharge when SOC drops below 30%
   - Recharge duration: at least 100 time units
   - Don't interrupt recharge (let it complete)

2. **Power-Intensive Operations**:
   - Don't schedule back-to-back
   - Leave at least 50 time units between them
   - Monitor cumulative drain

3. **Priority**:
   - Battery health > science operations
   - If conflict, delay science to ensure power

## Communication Windows

Downlink scheduling:

1. **Window Usage**:
   - Each orbiter pass is a separate comm window
   - Schedule downlink within the window
   - Start 40-60 time units after window opens (allow stabilization)

2. **Duration**:
   - Downlink should be 30-100 time units
   - Don't fill entire window (leave margin)

3. **Data Volume**:
   - Ensure sufficient data accumulated before downlink
   - Don't waste window with empty downlink
```

## Using Guidance Files

### Command Line

```bash
python3 jpl/tools/llm_scheduler.py tasknet.tn --guidance my_guidance.txt
```

### Multiple Guidance Files

Combine multiple guidance files:

```bash
cat thermal.txt power.txt comm.txt > combined_guidance.txt
python3 jpl/tools/llm_scheduler.py tasknet.tn --guidance combined_guidance.txt
```

### Iterative Refinement

1. **First attempt**: Run without guidance, see what LLM produces
2. **Identify issues**: Find patterns that are valid but unrealistic
3. **Write guidance**: Add instructions for those specific patterns
4. **Test**: Run with guidance, verify improvements
5. **Refine**: Adjust guidance based on results

## Tips for Effective Guidance

### Start Simple

Don't try to specify everything at once. Start with:
1. Most critical operational pattern
2. Test
3. Add more guidance as needed

### Use Task Naming Conventions

Leverage tasknet naming:
```
"For each downlink_allN task, schedule comm_preheat__N before it"
```

The LLM will understand the N matches up.

### Provide Rationale

Explain why constraints matter:
```
"DO NOT schedule during high-radiation periods [5000-5500] because 
memory bit-flips can corrupt science data."
```

This helps the LLM understand intent and generalize.

### Test Without Guidance First

Always run once without guidance to see the "baseline" solution. This shows:
- What the LLM naturally generates
- Where guidance is actually needed
- Whether formal constraints are sufficient

### Balance Specificity and Flexibility

❌ **Too specific**: "Schedule comm_preheat__1 at exactly t=260"
- LLM can't adapt if constraints change

✅ **Right level**: "Schedule comm_preheat__N starting 100 units before orbiter_available_N"
- LLM can compute specific times based on actual window times

❌ **Too vague**: "Manage thermal resources appropriately"
- LLM doesn't know what "appropriately" means

## Common Patterns

### Pattern 1: One-Per-Window

**Use case**: Each communication window needs dedicated resources

```
For each orbiter_available_N window, schedule:
- comm_preheat__N ending when window starts
- comm_maintainheat__N spanning entire window  
- downlink_allN contained within window
```

### Pattern 2: Buffer Times

**Use case**: Leave recovery time between operations

```
Leave at least 50 time units between power-intensive operations:
- After high_power_task_A ends
- Before high_power_task_B starts
- Minimum gap: 50 time units
```

### Pattern 3: Sequencing

**Use case**: Specific order for operations

```
Observation sequence must follow this order:
1. Camera_calibration (first)
2. Target_acquisition (after calibration)
3. Science_observation (after acquisition)
4. Data_compression (after observation)
5. Downlink (after compression)
```

### Pattern 4: Resource Thresholds

**Use case**: Trigger actions based on resource levels

```
Schedule battery recharge when:
- Battery SOC drops below 30%
- Recharge duration: at least 100 time units
- Complete before any high-power operations
```

## Troubleshooting

### Guidance Not Followed

**Problem**: LLM ignores guidance

**Possible causes**:
1. Guidance conflicts with formal constraints
2. Guidance is too vague
3. Guidance uses ambiguous terminology

**Solutions**:
1. Check if guidance contradicts tasknet constraints
2. Make guidance more specific with examples
3. Use exact task names from tasknet

### Too Many Failed Attempts

**Problem**: Can't find valid schedule even with guidance

**Possible causes**:
1. Guidance over-constrains the problem
2. No valid schedule exists with those requirements

**Solutions**:
1. Relax guidance (use "prefer" instead of "must")
2. Test without guidance to verify base feasibility
3. Increase `--max-attempts`

### LLM Misinterprets Guidance

**Problem**: Schedule doesn't match intended pattern

**Solution**: Add concrete example in guidance:

```
Example for window 1 at [360, 660]:
✓ CORRECT:
  comm_preheat__1: [260, 360]
  comm_maintainheat__1: [360, 660]
  downlink_all1: [400, 500]

✗ WRONG:
  comm_preheat__1: [0, 100]  ← Too early!
  comm_maintainheat__1: [360, 660] ← OK
  downlink_all1: [400, 500] ← OK but violates thermal timing
```

## Examples

See [mexec_guidance.txt](../jpl/mexec/mexec_guidance.txt) for a complete real-world example used with the 50-task MEXEC tasknet.

## Summary

**Key takeaways**:
1. Guidance files bridge formal constraints and operational reality
2. Use natural language, be specific, include examples
3. Focus on patterns, not prescriptive details
4. Test without guidance first to establish baseline
5. Iterate: start simple, refine based on results

**When guidance works well**:
- You get schedules that are both valid AND practical
- LLM understands operational intent
- Results match mission operations expectations
