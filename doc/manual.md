# TaskSAT Language Manual

This document provides complete syntax reference for the TaskSAT DSL.

For the formal grammar specification, see [grammar.txt](../src/smt/grammar.txt).

## Overview

A TaskSAT specification (`.tn` file) defines a scheduling problem with:
- **Timelines**: State variables and resources that evolve over time
- **Tasks**: Operations with durations, constraints, and effects
- **Properties**: Temporal logic formulas that must hold

## TaskNet Structure

Here is the schematic structure of a TaskNet specification:

```tasknet
tasknet Name {
  end = time_horizon;

  timelines {
    timeline_name : timeline_type = value;
    ...
  }

  init {
    timeline_name = value;
    timeline_name in [min, max];
    ...
  }

  taskdef definition_name {
    ...
  }

  task instance_name : definition_name {
    ...
  }

  task standalone_task {
    ...
  }

  optional task optional_task {
    ...
  }

  constraints {
    prop property_name: formula;
    ...
  }

  properties {
    prop property_name: formula;
    ...
  }
}
```

**Components:**
- `end`: Global time horizon (all tasks must complete by this time)
- `timelines`: Declare all state variables and resources
- `init`: Initial state constraints (optional)
- `taskdef`: Reusable task definitions (optional)
- `task`: Task instances and standalone tasks
- `optional task`: Tasks that may or may not execute
- `constraints`: Temporal properties constraining generated schedules
- `properties`: Temporal properties checked on generated schedules

## Task Structure

Here is the schematic structure of a task:

```tasknet
task task_name {
  duration 30;
  duration_range [20,40];
  start 20;
  start_range [10, 50];
  end_range [30, 100];
  after other_task, another_task;
  containedin parent_task;

  pre {
    timeline_name = value;
    timeline_name in [min, max];
  }

  inv {
    timeline_name = value;
    timeline_name in [min, max];
  }

  post {
    timeline_name = value;
    timeline_name in [min, max];
  }

  impacts {
    pre {
      timeline_name = value;
      timeline_name += delta;
      timeline_name +~ rate;
    }
    maint {
      timeline_name += delta;
      timeline_name +~ rate;
    }
    post {
      timeline_name = value;
      timeline_name += delta;
      timeline_name +~ rate;
    }
  }
}
```

**Components:**

- `duration`: Preferred duration 
- `duration_range`: Duration range
- `start`: Preferred start time 
- `start_range` / `end_range`: Time windows for when task can start/end
- `after`: Task ordering dependencies (must start after other tasks end)
- `containedin`: Task must execute during another task
- `pre`: Preconditions (must hold at task start)
- `inv`: Invariants (must hold throughout task execution)
- `post`: Postconditions (must hold at task end)
- `impacts`: Effects on timelines (assignments, deltas, rates)

---

# Detailed Reference

## Timelines


Timelines model state variables and resources that change over time. Each timeline has a type that determines what values it can hold and how it can be modified.

### The Five Kinds of Timelines

There are five kinds of timelines, shown here in schematic form:

```
name : state(value1, value2, ...) = initial_value;
name : atomic = true/false;
name : claim [min, max] = initial_value;
name : cumulative [min_rate, max_rate] bounds [min, max] = initial_value;
name : rate [min_rate, max_rate] bounds [min, max] = initial_value;
```

The state timeline is an enumerate type of a finite number of values, which
can be names or numbers. The atomic timeline is a special case where the values are Booleans. The three other timelines denote floating point numbers and allow different kinds of operations. They each have a range of values that a schdule must stay within. In addition, the cumulative and rate timelines have a minimal and maximal bound, and any value computed during the execution of a schedule will be clamped to stay in that interval. It is effectively the type of the timeline, whereas the first interval is a subtype of that.

As shown above, timelines can be initialized to a specific value when defined. Howver, this is optional. If no initial value is provided, they can range over their type, unless they are constrained by an init-block shown below schematically:

```tasknet
init {
  timeline1 = value;
  timeline2 in [min, max];
  timeline2 in value, [min1,max1], [min2,max2]'
  ...
}
```

Here timeline1 is given a value, timeline2 is specified to be in a range,
and timeline3 is specified as a disjunction of options: either it has a specific value or it is in the range [min1,max1] or it is in the range [min2,max2] - as an example.

Example:

```tasknet
init {
  battery = 50.0;              // Battery must start at exactly 50
  temperature in [10.0, 30.0]; // Temperature can start anywhere in this range
  mode = idle;                 // Mode must start as idle
}
```

### Constraints

The constraints shown above for initializing timelines represent the general form of constraints, also used in pre, inv, and post conditions.

### Impact Operations Summary

There are three different ways to update a timeline

- assignments: 
  * timeline = value
- cumulative updates (adds/subtracts a delta):
  * timeline += value
  * timeline -= value
- rate updates (sets the rate with which a timeline changes per time unit):
  * timeline +~ value
  * timeline -~ value

Cumulative and rate updates only work on numeric timelines.

The meaning of these updates depend on which impact kind it conerns:

- pre: when the task starts
- maint: during the execution of the task
- post: at the end of the task

Their impacts are shown in the following figure (from MEXEC User’s Guide
Version 1.5.0, May 1, 2024):

![Impacts](impacts.png)

This table shows which impact operations are allowed on each timeline type:

| Timeline Type | Assignment (`=`) | Delta (`+=`/`-=`) | Rate (`+~`/`-~`) | When Allowed |
|---------------|------------------|-------------------|------------------|--------------|
| **State** | ✓ | ✗ | ✗ | pre, post only |
| **Atomic** | ✓ | ✗ | ✗ | pre, post only |
| **Claimable** | ✗ | ✓ | ✗ | like cumulative but maint only |
| **Cumulative** | ✓    | ✓ | ✗ | Delta: pre/maint/post<br>Assignment: pre/post only |
| **Rate** | ✓   | ✓    | ✓ | Delta/Rate: pre/maint/post<br>Assignment: pre/post only |

## Task Definitions and Instances

TaskSAT supports reusable task definitions that can be instantiated multiple times.

### Task Definitions

Define a reusable task template with `taskdef`:

```tasknet
taskdef charge_def {
  pre {
    battery in [0.0, 60.0];
  }
  impacts {
    maint {
      battery +~ 2.0;
    }
  }
}
```

### Task Instances

Create instances of a definition:

```tasknet
task charge1 : charge_def {
  duration_range [30, 40];
  start_range [0, 50];
}

task charge2 : charge_def {
  duration_range [50, 60];
  after charge1;
}
```

**Shorthand syntax:**

If an instance doesn't add any properties, use the shorthand:

```tasknet
task charge3 : charge_def;
```

This creates an instance with all properties inherited from the definition.

**Benefits:**
- **Reusability**: Define common behavior once, instantiate many times
- **Separation**: Definition provides behavior, instance provides scheduling constraints
- **Merging**: Instance properties override definition properties
- **Impacts merge**: If both definition and instance have impacts, they are merged (both apply)

### Standalone Tasks

Tasks can also be defined directly without using definitions:

```tasknet
task drive {
  duration 30;
  pre { battery >= 50.0; }
  impacts {
    maint { battery +~ -1.5; }
  }
}
```

## Tasks

Tasks represent operations with durations, constraints, and effects.

### Task Fields

All task fields are optional unless marked as required.

**duration** or **duration_range** (required, choose one)
- Fixed duration: `duration 30;`
- Variable duration: `duration_range [10, 50];`

**start** (optional)
- Fixed start time: `start 100;`
- Overrides any start_range if both are specified

**start_range** / **end_range** (optional)
- Constrain when task can start/end
- Example: `start_range [0, 50];`
- Example: `end_range [100, 200];`

**priority** (optional)
- Integer priority for scheduling preferences (lower values = higher priority)
- Used in optimization mode to prefer certain tasks
- Example: `priority 10;`

**after** (optional)
- Task ordering: this task must start after other tasks end
- Can specify multiple tasks: `after task1, task2, task3;`
- This task's start time must be >= all specified tasks' end times
- Example: `after heating;`
- Example: `after warmup, calibrate;`

**containedin** (optional)
- Hierarchical constraint: this task must execute entirely within another task
- Can specify multiple parent tasks: `containedin parent1, parent2;`
- This task's start >= parent's start AND this task's end <= parent's end
- Example: `containedin maintenance_window;`
- Example: `containedin daylight, communication_window;`

**optional** (keyword)
- Mark task as optional for optimization
- Solver will try to minimize number of optional tasks included
- Example: `optional task bonus_science { ... }`

**pre** (preconditions)
- Must be true when task starts
- Example:
```tasknet
pre {
  battery in [50.0, 100.0];
  mode = idle;
}
```

**inv** (invariants)
- Must be true throughout task execution
- Example:
```tasknet
inv {
  temperature in [0.0, 50.0];
  sensor_active = true;
}
```

**post** (postconditions)
- Must be true when task ends
- Example:
```tasknet
post {
  data_collected in [100.0, 1000.0];
  mode = done;
}
```

**constraints**

- Temporal constraints used to constrain what schedules are generated
- Just like pre, inv, and post conditions constrain what schedules are generated

```tasknet
constraints {
  prop name1: formula1;
  prop name2: formula2;
  ...
}
```

**properties**

- Temporal properties checked on generated schedules
- Note that these do **not** influence what schedules are generated

```tasknet
properties {
  prop name1: formula1;
  prop name2: formula2;
  ...
}
```

### Temporal Formulas

Temporal properties are expressed in a temporal logic.

**Atomic Formulas**

- `timeline = value` 
- `timeline >= value`
- `timeline <= value`
- `timeline < value`
- `timeline > value`

Where value can be a name (for state timelines), a Boolean (for atomic timelines), or an integer or float.

In addition the following formula:

- `active`(task)

is true when the specified task is executing.

**Logical operators:**

- `not` φ
- φ1 `and` φ2
- φ1 `or` φ2
- φ1 `->` φ2` (implication)

**Temporal operators**

Future time:

- `always` φ - φ is true always in the future, including now
- `eventually` φ - φ is true at some future time
- φ1 `until` φ2 = φ2 eventually is true and until then (not including) φ1 is true

Past time:

- `sofar` φ - φ is true always in the past, including now
- `once` φ - φ is true at some past time
- φ1 since φ2 - φ2 once was true and since then (not including) φ1 is true

**Examples**

```tasknet
  # Battery must always stay above 20%
  prop battery_safe: always battery > 20.0;

  # Rover must eventually reach the target
  prop reach_target: eventually location = target;

  # If battery is low, we must eventually charge
  prop charge_when_low: always(battery < 30.0 -> eventually active(charge));

  # Heating and cooling never happen simultaneously
  prop exclusive_thermal: always (not (active(heating) and active(cooling)));

  # Data collection happens after warming up
  prop collect_after_warmup: active(collect_data) -> once active(warmup);

  # Battery must stay above safe level until charging starts
  prop safe_until_charge: (battery > 20.0) until active(charge);
```

