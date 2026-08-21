---
sidebar_position: 10
sidebar_label: "Time Boundaries"
---

# Time Variable and Task Boundaries Feature

## Overview

This document describes the `time` variable and `task.start`/`task.end` boundary references added to TaskSAT in June 2026.

## Motivation

Previously, the only way to express task ordering was using temporal logic with `active()` predicates:

```tasknet
# Old way: using active() and temporal operators
prop order: always (active(T1) -> once active(T2));
```

This approach had several drawbacks:
1. **Performance**: Creates a `__T_active` timeline for every referenced task
2. **Verbosity**: Requires `always` and `once` operators for simple orderings
3. **Semantics**: `active()` means "during execution", but we often just want "T1 starts after T2 ends"

## Solution

Added direct references to task boundaries and current time:

```tasknet
# New way: using task boundaries
prop order: T1.start >= T2.end;
```

## Syntax

### Time Variable

`time` - represents the current time point in temporal formulas

```tasknet
prop early: time < 1000;
prop conditional: always (time >= 500 -> battery > 30.0);
```

### Task Boundaries

`task.start` - the scheduled start time of a task  
`task.end` - the scheduled end time of a task

```tasknet
prop T1_after_T2: T1.start >= T2.end;
prop early_start: mission.start < 100;
prop late_end: mission.end > 5000;
```

### Comparisons

All standard comparison operators are supported:
- `<`, `<=`, `=`, `>=`, `>`

Can compare:
- `time` with numbers
- `time` with task boundaries
- Task boundaries with numbers
- Task boundaries with other task boundaries

```tasknet
prop order1: T1.start >= T2.end;
prop order2: T2.end < T3.start;
prop window: task.start >= 100 and task.end <= 500;
prop gap: T2.start >= T1.end + 50;  # Note: arithmetic not yet supported
```

## Semantics

### Constants, Not Functions

`time`, `task.start`, and `task.end` are **constants** - their values are determined once by the solver and don't change. This is different from timeline references like `battery`, which are functions of time.

```tasknet
# battery is evaluated at each zone
always (battery >= 20.0);  # battery value changes over time

# task.start is a constant
task1.start >= task2.end;  # these are fixed integers chosen by the solver
```

### Conditional Semantics for Optional/Request Tasks

Referencing `task.start` or `task.end` where `task` is optional or request is **conditional** - the constraint evaluates to `true` if the task is not scheduled.

```tasknet
optional task backup { ... }

constraints {
  # This is CONDITIONAL: if backup is scheduled, then backup.start >= main.end
  # If backup is NOT scheduled, the constraint evaluates to true
  prop order: backup.start >= main.end;
}
```

This matches the semantics of `active()`:
```tasknet
# These are semantically equivalent:
prop order_new: opt.start >= req.end;
prop order_old: always (active(opt) -> once active(req));
```

**To force an optional task to be scheduled**, use `eventually active(task)` explicitly, or make it a `request` task.

### SMT Encoding

Under the hood:
- `time` → zone boundary at current position: `zones[j]`
- `task.start` → Z3 Int variable: `start_vars[task]`
- `task.end` → Z3 Int variable: `end_vars[task]`

No additional timelines are created, making this approach more efficient than `active()`.

## Before vs After Comparison

### Example 1: Sequential Task Ordering

**Before:**
```tasknet
prop sequential:
  always (
    (active(T2) -> once active(T1)) and
    (active(T3) -> once active(T2)) and
    (active(T4) -> once active(T3))
  );
```

Creates 4 `__T*_active` timelines, uses 3 `always` checks, 3 `once` checks.

**After:**
```tasknet
prop sequential:
  T1.end <= T2.start and
  T2.end <= T3.start and
  T3.end <= T4.start;
```

No extra timelines, simple arithmetic constraints. If any tasks are optional/request, the constraint is conditional on them being scheduled.

### Example 2: Task Containment

**Before:**
```tasknet
prop preheat_before_mission:
  always (active(mission) -> once active(preheat));

prop mission_during_heating:
  always (active(mission) -> active(maintainheat));
```

**After:**
```tasknet
prop preheat_before_mission:
  preheat.end <= mission.start;

prop mission_during_heating:
  maintainheat.start <= mission.start and
  mission.end <= maintainheat.end;
```

### Example 3: Time Windows

**Before:**
```tasknet
# Hard to express "task must start before time 1000" with active()
# Would need something like:
prop early: always (time < 1000 or not active(task));
```

**After:**
```tasknet
prop early: task.start < 1000;
```

## When to Use Each Approach

### Use `task.start` / `task.end` for:
- Task ordering constraints (`T1.start >= T2.end`)
- Time windows (`task.start < 100`)
- Gaps between tasks (`T2.start >= T1.end + 50`)
- Simple "before/after" relationships

### Use `active(task)` for:
- Checking if a task is executing **during** a time period
- Mutual exclusion ("heating and cooling never overlap")
- Resource constraints ("only one comm task active at a time")
- Conditional behavior ("if task is active, then timeline X must be Y")

## Implementation Notes

- Parser: Added `time` keyword, `DOT` token handling for `task.start`/`task.end`
- AST: New nodes `TLTimeVar`, `TLTaskBoundary`, `TLTimeCmp`
- SMT Encoder: Maps to Z3 Int variables, forces optional/request inclusion
- Wellformedness: Validates task existence, prevents taskdef references

## Examples in Practice

See [tests/test_time_boundaries.py](https://github.com/nasa-jpl/tasksat/blob/main/tests/test_time_boundaries.py) for comprehensive examples and test cases.

## Limitations

1. **No arithmetic expressions yet**: Can't write `T1.start + 100` or `T2.end - T1.start > 50`
   - Workaround: Use multiple constraints
2. **Only in temporal formulas**: Can't use in task `inv` or `pre` conditions
3. **No dynamic duration**: Can't reference `task.duration` (but you can compute it from `task.end - task.start` conceptually)

## Future Enhancements

Potential future additions:
- Arithmetic expressions: `T1.start + 100`, `T2.end - T1.start`
- Duration references: `T1.duration`
- Optional forcing: Flag to make boundary references NOT force optional tasks
- Use in task conditions: Allow in `inv`/`pre`/`post`
