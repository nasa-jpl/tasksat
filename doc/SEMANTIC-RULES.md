# TaskNet Semantic Rules

This document codifies the precise semantics for interpreting and validating TaskNet schedules. These rules are extracted from:
- **Lean specification**: `src/lean/TaskNetExec/TaskNet/Semantics.lean`
- **TaskSAT implementation**: `src/smt/tasknet_smt.py`
- **Validation experience**: Bugs fixed and corner cases resolved

## Purpose

When generating schedules (manually or via LLM), these rules define what makes a schedule **valid**. The Lean validator and TaskSAT SMT encoding both implement these semantics.

---

## 1. Task Timing Constraints

### 1.1 Start/End/Duration Ranges

Every task has three range constraints that must ALL be satisfied:

```
startrng: [low, high]  - valid start times
endrng:   [low, high]  - valid end times  
durrng:   [low, high]  - valid durations (end - start)
```

**Rule**: A task scheduled at `[s, e)` is valid only if:
- `startrng.low ≤ s ≤ startrng.high`
- `endrng.low ≤ e ≤ endrng.high`
- `durrng.low ≤ (e - s) ≤ durrng.high`

**Note**: All three constraints must be satisfied simultaneously.

**Optimization Heuristic**: When multiple durations are valid, prefer **shorter durations** near `durrng.low`. This:
- Frees up timeline and resources sooner
- Creates more scheduling flexibility for other tasks
- Reflects typical mission operations (complete tasks efficiently)
- Leaves slack for contingencies

Exception: Request tasks may use longer durations if it provides more value (e.g., longer science observations).

### 1.2 Task Interval Notation

Tasks execute over **half-open intervals** `[start, end)`:
- Task is active from time `start` (inclusive)
- Task completes at time `end` (exclusive)
- Duration is `end - start`

---

## 2. Temporal Dependencies

### 2.1 After Constraints (Instance-Level)

```
task B {
  after A;  // B must start after A ends
}
```

**Rule**: If task B has `after: ["A"]`, then:
```
A.end ≤ B.start
```

**Note**: The equal case is valid (`A.end == B.start` is allowed).

### 2.2 Containedin Constraints (Instance-Level)

```
task child {
  containedin parent;  // child must be fully inside parent
}
```

**Rule**: If task child has `containedin: ["parent"]`, then:
```
parent.start ≤ child.start  AND  child.end ≤ parent.end
```

The child interval must be a subset of the parent interval.

### 2.3 Type-Level Dependencies (Existential Semantics)

```
task downlink_all1 {
  after comm_preheat;           // any instance matching "comm_preheat"
  containedin comm_maintainheat; // any instance matching "comm_maintainheat"
}
```

**Rule**: Type-level constraints use **existential semantics**:
- `after_definitions: ["comm_preheat"]` means "there exists at least one task whose ID starts with 'comm_preheat' such that it ends before this task starts"
- `containedin_definitions: ["comm_maintainheat"]` means "there exists at least one task whose ID starts with 'comm_maintainheat' that contains this task's interval"

**Matching rule**: A task ID matches a definition name if `taskId.startsWith(defName)`
- `comm_preheat__1` matches `comm_preheat` ✓
- `comm_preheat__2` matches `comm_preheat` ✓
- `downlink_all1` does NOT match `comm_preheat` ✗

### 2.4 MEXEC Rule: Creating Instances for Referenced Taskdefs

**CRITICAL**: If a task has a type-level constraint (e.g., `after comm_preheat`) but **no instances of that taskdef exist** in the task list, you MUST create instances to satisfy the constraint.

**Example scenario**:
```
taskdef comm_preheat { ... }  // definition exists
task downlink_all1 {
  after comm_preheat;         // references comm_preheat
}
// BUT: no comm_preheat instances in task list!
```

**What to do**:
1. **Create one or more instances** with IDs like `comm_preheat__1`, `comm_preheat__2`, etc.
2. **Inherit all constraints** from the taskdef (durrng, pre, inv, post, impacts, after, containedin)
3. **Schedule them** with start/end times that:
   - Satisfy the taskdef's constraints
   - Satisfy the dependent task's type-level constraint
4. **Include in schedule**: Add them to the schedule JSON and the "included" array

**How many instances to create?**
- Use judgment based on the scenario
- Example: If 10 downlinks each need their own preheat, create 10 preheat instances
- User guidance may specify patterns (e.g., "one preheat before each downlink")

**Naming convention**: Use `{taskdef_name}__{number}` (e.g., `comm_preheat__1`, `comm_maintainheat__2`)

**Why this rule exists**: In MEXEC, taskdefs can be referenced without explicit instances. The scheduler dynamically decides how many instances to create based on operational needs. This is not statically decidable—it depends on the schedule being generated.

---

## 3. Timeline Semantics

### 3.1 Timeline Types

**State Timeline**:
- Discrete states (e.g., "VISIBLE", "HIDDEN")
- Tasks can assign to specific states
- Check equality in conditions

**Atomic Timeline**:
- Boolean: true when claimed by a task, false otherwise
- Only one task can claim it at a time
- Used for exclusive resources

**Claimable Timeline**:
- Numeric resource with range [low, high]
- Tasks claim amounts (must stay within range)
- Check if enough is available

**Cumulative Timeline**:
- Accumulates values over time
- Has rate range [low, high] and bounds [low, high]
- Tasks contribute deltas
- Level must stay within bounds

**Rate Timeline**:
- Like cumulative, but tracks rate of change
- Level = ∫(rate) over time
- Both rate and level have bounds

### 3.2 Timeline State Evolution

Timelines have state that evolves over time:

1. **Initial state** (at time 0): specified in timeline definition
2. **Task impacts** modify state at specific times
3. **State propagates** forward between impacts

**Critical**: When multiple tasks affect the same timeline, impacts are applied in **time order** (by task start/end times).

---

## 4. Impact Application

### 4.1 Impact Timing

Tasks can impact timelines at three times:

- **PRE** (`pre`): Applied at task **start** time `s`
- **MAINT** (`maint`): Applied **throughout** task execution `(s, e)`
- **POST** (`post`): Applied at task **end** time `e` (or `e+1` in some implementations)

### 4.2 Impact Types

**Assign** (`assign`):
```
impacts { pre { resource = "ACTIVE"; } }
```
Sets timeline to a specific value.

**Cumulative** (`cumulative`):
```
impacts { maint { battery_soc += -5.0; } }
```
Adds a delta to cumulative timeline.

**Rate** (`rate`):
```
impacts { maint { battery_rate = -2.0; } }
```
Sets the rate of change for a rate timeline.

### 4.3 Impact Application Order

**For PRE and POST impacts** (instantaneous):
1. Apply all impacts at that time in task ID order (deterministic)
2. Update timeline state
3. State is now available for next time point

**For MAINT impacts** (continuous):
1. Impact is active throughout task interval `(s, e)`
2. For rate timelines: rate is constant during this interval
3. For cumulative: acts like constant rate contribution

---

## 5. Condition Checking (Pre/Inv/Post)

### 5.1 Preconditions (Pre)

```
pre { resource = "IDLE"; }
```

**Rule**: Checked at time `s` (task start), BEFORE this task's PRE impacts are applied.

**Timing**:
```
t = s-1: previous state
t = s:   check PRE conditions with previous state
t = s:   apply PRE impacts (if conditions pass)
```

### 5.2 Invariants (Inv)

```
inv { resource = "ACTIVE"; }
```

**Rule**: Checked throughout `(s, e]` (exclusive start, inclusive end).

**Critical timing detail**:
- At boundary `t = s` (start): invariants are NOT checked
- At boundary `t = e` (end): invariants ARE checked
- During `t ∈ (s, e)`: invariants are checked

**Special case at end boundary**: At `t = e`, check invariants with the state BEFORE this task's POST impacts.

**Why this matters**: The atomic pattern (PRE impact enables INV check) works because:
1. At `t = s`: PRE impacts apply
2. At `t = s+ε`: INV checks with state including PRE impacts ✓

**Implementation note**: Lean uses `st < k ∧ k ≤ en` for invariant checking.

### 5.3 Postconditions (Post)

```
post { resource = "IDLE"; }
```

**Rule**: Checked at time `e` (task end), AFTER this task's POST impacts are applied.

**Timing**:
```
t = e:   apply POST impacts
t = e:   check POST conditions with new state
```

---

## 6. Timeline Condition Syntax

### 6.1 State Timeline Conditions

```
{ timeline_id = "STATE_NAME"; }
```

Checks if timeline is in the specified state.

### 6.2 Numeric Timeline Conditions

```
{ battery_soc = [80.0, 100.0]; }  // value in range
```

Checks if timeline value is within the range.

### 6.3 Multiple Constraints

```
pre {
  resource = "IDLE";
  battery_soc = [50.0, 100.0];
}
```

ALL constraints must be satisfied (logical AND).

---

## 7. Sparse Semantics (Optimization)

### 7.1 Zone Boundaries

The validator doesn't check every time point `t ∈ [0, endTime]`. Instead, it checks only at **zone boundaries**:

**Zone boundaries are**:
- Task start times: `{t : ∃task. t = task.start}`
- Task end times: `{t : ∃task. t = task.end}`
- Time 0 (initial)
- Time endTime (final)

### 7.2 State Propagation

Between zone boundaries, timeline state is **constant** (no tasks active, no impacts).

**Rule**: 
```
state(t) = last_computed_state  for all t in (boundary_i, boundary_i+1)
```

This is valid because:
- Impacts only occur at task start/end
- Conditions only checked at task start/end
- Between boundaries, nothing changes

---

## 8. Task Kinds

### 8.1 Required Tasks

```
task foo {
  kind required;
}
```

**Rule**: MUST be scheduled. Validation fails if not in schedule.

### 8.2 Optional Tasks

```
task bar {
  kind optional;
}
```

**Rule**: MAY be scheduled. Include in schedule's `included` array if scheduled.

### 8.3 Request Tasks

```
task baz {
  kind request;
}
```

**Rule**: Like optional, but semantically represents a user request. Include in `included` array if scheduled.

**Optimization Goal**: Schedules should include **as many request task instances as possible**. When multiple valid schedules exist, prefer the one that satisfies more request tasks.

**Rationale**: Request tasks represent user-desired activities (e.g., science observations, data collections). A schedule that includes more requests provides more value to the mission.

**For LLM schedulers**: Actively try to include all request tasks unless constraints make it impossible. Don't minimize the schedule—maximize request task inclusion.

#### Handling Impossible Request Tasks

**If a request task consistently violates constraints across multiple attempts**, it may be fundamentally unsatisfiable. In this case:

1. **Recognize the pattern**: If the same request task violates the same constraint in 3+ consecutive attempts, it's likely impossible
2. **Exclude it**: Remove the task from the schedule and from the "included" array
3. **Continue with others**: Generate a schedule with the remaining request tasks
4. **Result**: A valid schedule with N-1 request tasks is better than no valid schedule

**Example scenario**:
```
battery_recharge_request_0: inv { battery_soc in [0.0, 95.0] }
Initial battery_soc = 95.0, natural rate = +0.01

Attempt 1: Schedule at t=10000 → SOC = 195.0 → VIOLATION
Attempt 2: Schedule at t=5000 → SOC = 145.0 → VIOLATION  
Attempt 3: Schedule at t=1000 → SOC = 105.0 → VIOLATION
Attempt 4: Exclude battery_recharge_request_0, schedule other requests → SUCCESS
```

**When to apply this strategy**:
- Same violation message appears repeatedly for the same request task
- You've tried different timing positions without success
- Other tasks in the schedule are consistently valid

**Result**: A schedule satisfying 2 out of 3 request tasks is a valid and valuable solution.

### 8.4 Definition Tasks

```
task comm_preheat {
  kind definition;
}
```

**Rule**: This is a **template**, not a schedulable instance. Used for type-level constraints. Does not appear in schedule.

---

## 9. Schedule Validation Algorithm

A schedule is **valid** (admissible) if ALL of the following hold:

### 9.1 Syntactic Validity
- All required tasks are scheduled
- All scheduled tasks satisfy start/end/duration range constraints
- All "after" dependencies are satisfied
- All "containedin" dependencies are satisfied

### 9.2 Semantic Validity
- All preconditions hold at task start times
- All invariants hold throughout task execution
- All postconditions hold at task end times
- All timeline bounds are respected throughout

### 9.3 Validation Process

```
1. Filter active tasks (required + included optional/request)
2. Compute zone boundaries from task start/end times
3. For each zone boundary t:
   a. Apply impacts from tasks starting/ending at t
   b. Update timeline states
   c. Check conditions for tasks active at t
4. If all conditions pass at all boundaries: VALID
5. Otherwise: INVALID with violation list
```

---

## 10. Common Patterns

### 10.1 Thermal Preparation Pattern

```
task preheat {
  impacts { maint { thermal_state = "WARMING"; } }
}

task maintainheat {
  after preheat;
  impacts { maint { thermal_state = "STABLE"; } }
}

task operation {
  after preheat;
  containedin maintainheat;
  inv { thermal_state = "STABLE"; }
}
```

**Interpretation**: Equipment needs warm-up before use, must maintain temperature during operation.

### 10.2 Atomic Resource Pattern

```
timeline resource : atomic;

task use_resource {
  pre { resource = false; }   // must be free
  inv { resource = true; }    // claim it
  impacts { pre { resource = true; } maint { resource = true; } post { resource = false; } }
}
```

**Interpretation**: Exclusive access to a resource (e.g., communication system).

### 10.3 Battery Drain Pattern

```
timeline battery_soc : cumulative [-100.0, 0.0] bounds [0.0, 100.0] = 95.0;

task power_consumer {
  impacts { maint { battery_soc += -5.0; } }  // drain at 5%/time
}

task battery_recharge {
  impacts { maint { battery_soc += 10.0; } }  // charge at 10%/time
}
```

**Interpretation**: Tasks consume/produce power, battery level must stay in bounds.

---

## 11. Edge Cases and Gotchas

### 11.1 Zero-Duration Tasks

Tasks with `start == end` (duration 0) are allowed but tricky:
- PRE and POST impacts both apply at same time `t = start = end`
- Invariants checked at `(start, end]` = empty interval → always pass
- Use for "instantaneous" events

### 11.2 Adjacent Tasks

```
task A: [100, 200)
task B: [200, 300)  with "after A"
```

Valid! `A.end == B.start` satisfies "after" constraint.

### 11.3 Timeline Naming Collisions

If two tasks have impacts on same timeline at same time, order matters:
- Implementation-dependent (TaskSAT: alphabetical; Lean: definition order)
- Best practice: avoid this, design timelines to compose cleanly

### 11.4 Missing Type-Level Instances

```
task downlink {
  after comm_preheat;  // but no comm_preheat__* instances scheduled!
}
```

**Result**: Validation FAILS with violation "no instances of comm_preheat exist".

**Solution**: Either schedule a matching instance, or remove the constraint.

---

## 12. Scheduler Guidelines

When generating schedules (manually or via algorithm):

### 12.1 Start with Required Tasks
Schedule all required tasks first, respecting their constraints.

### 12.2 Resolve Type-Level Dependencies
If a task requires `after_definitions: ["foo"]`, ensure at least one instance matching "foo" is scheduled with appropriate timing.

### 12.3 Respect Timeline Bounds
Track timeline state evolution and ensure bounds are never violated.

### 12.4 Check Conditions Early
Before committing to a schedule, verify pre/inv/post conditions would hold.

### 12.5 Use Slack in Ranges
Don't schedule tasks at exact boundary limits unless necessary. Use interior of ranges for robustness.

### 12.6 Iterate on Violations
If validation fails, read violation messages carefully:
- "outside range" → adjust start/end time
- "requires 'after X' but no instances exist" → schedule X instances
- "invariant violated at t=T" → check timeline state at that time

---

## 13. Differences Between Implementations

### 13.1 TaskSAT vs Lean

**Invariant timing**:
- TaskSAT: Checks at `(s, e]` with special boundary handling
- Lean: Checks at `st < k ∧ k ≤ en` (same semantics)

**Impact application**:
- TaskSAT: POST impacts at `e`
- Lean: POST impacts at `e` (in practice, checked before boundary advance)

**Type-level matching**:
- TaskSAT: Uses Z3 string operations (startsWith)
- Lean: Uses `String.startsWith` (same semantics)

### 13.2 Known Issues Fixed

**Bug**: Invariant checked at `[s, e]` instead of `(s, e]`
- **Symptom**: Atomic pattern fails (PRE impact doesn't take effect before INV check)
- **Fix**: Changed to `st < k ∧ k ≤ en`
- **When**: Fixed in Lean semantics update

**Bug**: Type-level constraints only searched filtered tasks
- **Symptom**: Valid schedules marked invalid if dependency instance not in "included" set
- **Fix**: Search full task list, not filtered active tasks
- **When**: Fixed in Lean semantics line 743

---

## Summary

These rules define the **precise semantics** of TaskNet validation. When generating schedules:

1. Satisfy all timing constraints (ranges, after, containedin)
2. Track timeline state evolution through impacts
3. Verify conditions at appropriate times (pre at start, inv during, post at end)
4. Use zone boundaries for efficiency (don't check every time point)
5. Handle type-level constraints with existential semantics

The Lean validator and TaskSAT both implement these semantics. When they disagree, investigate which is correct and update both to match.
