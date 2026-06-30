# TaskSAT Language Manual

This document provides complete syntax reference for the TaskSAT DSL.

For the formal grammar specification, see [grammar.txt](../src/smt/grammar.txt).

## Overview

A TaskSAT specification (`.tn` file) defines a scheduling problem with:
- **Timelines**: State variables and resources that evolve over time
- **Tasks**: Operations with durations, constraints, and effects
- **Properties**: Temporal logic formulas that must hold

## Comments

TaskSAT supports both hash-style and C-style line comments:

```tasknet
# Hash-style comment
// C-style comment

tasknet Example {
  end = 100;  # Inline hash comment

  timelines {
    battery : rate [0.0, 100.0] = 50.0;  // Inline C-style comment
  }
}
```

Both comment styles can be used interchangeably in the same file. C-style `//` comments are particularly useful when using editor features like VS Code's block comment toggle (Cmd+/ or Ctrl+/).

## Parameters

TaskSAT supports **parameters** to define reusable constants and avoid magic numbers in specifications. Parameters can be declared at three scopes:

1. **TaskNet-level (global)**: Available everywhere in the specification
2. **TaskDef-level**: Inherited by all task instances of that definition
3. **Task-level**: Override parameters for specific task instances

### Syntax

**TaskNet-level parameters:**
```tasknet
tasknet Example {
  param DRIVE_DURATION = 600;
  param SAFE_BATTERY = 20.0;
  param CHARGE_RATE = 0.5;
  
  task drive {
    duration DRIVE_DURATION;  // Reference global param
  }
}
```

**TaskDef-level parameters:**
```tasknet
taskdef work_def {
  param {
    DURATION = 10;
    RATE = 0.5;
  }
  
  duration DURATION;
  
  impacts {
    maint { battery +~ RATE; }
  }
}

task work1 : work_def {}  // Uses DURATION=10, RATE=0.5
```

**Task-level parameter overrides:**
```tasknet
task work2 : work_def {
  param {
    DURATION = 20;  // Override to 20
    RATE = 1.0;     // Override to 1.0
  }
}
```

### Resolution Order

When a parameter is referenced, TaskSAT resolves it using the following priority (highest to lowest):

1. **Task-level** params (if the reference is within a task body)
2. **TaskDef-level** params (if the task was instantiated from a taskdef)
3. **TaskNet-level** params (global scope)

If a parameter is not found in any scope, it is treated as a state name in constraint formulas.

### Parameter References

Parameters can be referenced in:
- Task durations: `duration PARAM_NAME;`
- Task start times: `start PARAM_NAME;`
- Time ranges: `start in [PARAM_MIN, PARAM_MAX];`
- Timeline ranges: `battery : rate [0.0, CAPACITY] = INITIAL;`
- Impact values: `battery += CHARGE_AMOUNT;`
- Constraint formulas: `battery >= SAFE_LEVEL`

Parameters can also reference other parameters:
```tasknet
param BASE_DURATION = 10;
param LONG_DURATION = BASE_DURATION * 2;  // Not yet supported - use explicit values

taskdef work {
  param {
    DURATION = BASE_DURATION;  // Reference global param
  }
  duration DURATION;
}
```

**Note:** Currently, parameter values must be literal constants (integers or reals). Arithmetic expressions in parameter definitions will be supported in a future version.

### Example: Parameterized Battery Constraints

```tasknet
tasknet RoverWithParams {
  end = 2000;
  
  param SAFE_BATTERY = 20.0;
  param CRITICAL_BATTERY = 10.0;
  param CHARGE_RATE = 0.5;
  param DISCHARGE_RATE = -0.3;
  
  timelines {
    battery : rate [0.0, 100.0] = 50.0;
  }
  
  taskdef drive_def {
    param { DURATION = 600; }
    duration DURATION;
    impacts { maint { battery +~ DISCHARGE_RATE; } }
  }
  
  taskdef charge_def {
    param { DURATION = 300; }
    duration DURATION;
    impacts { maint { battery +~ CHARGE_RATE; } }
  }
  
  task drive1 : drive_def {}  // Uses default DURATION=600
  
  task drive2 : drive_def {
    param { DURATION = 800; }  // Override to 800
  }
  
  task charge : charge_def {}
  
  constraints {
    always (battery >= SAFE_BATTERY);  // Global safety constraint
  }
}
```

### Benefits of Parameters

- **Avoid magic numbers**: Makes specifications more readable and maintainable
- **Single source of truth**: Change a value in one place, affects all references
- **Reusable definitions**: TaskDefs with configurable defaults
- **Type safety**: Parameters are resolved at parse time, errors caught early
- **Documentation**: Parameter names serve as inline documentation

## TaskNet Structure

Here is the schematic structure of a TaskNet specification:

```tasknet
tasknet Name {
  end = time_horizon;

  param PARAM_NAME = value;

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
    param {
      PARAM_NAME = value;
    }
    ...
  }

  task instance_name : definition_name {
    param {
      PARAM_NAME = value;
    }
    ...
  }

  task standalone_task {
    ...
  }

  optional task optional_task {
    ...
  }

  request task request_task {
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
- `param`: Global parameter declarations (optional, covered in detail below)
- `timelines`: Declare all state variables and resources
- `init`: Initial state constraints (optional)
- `taskdef`: Reusable task definitions (optional)
- `task`: Task instances and standalone tasks
- `optional task`: Tasks scheduled only if needed (minimize in optimize mode)
- `request task`: Tasks scheduled if possible (maximize in optimize mode)
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
      timeline_name +~ rate_delta;
      timeline_name =~ absolute_rate;
    }
    maint {
      timeline_name += delta;
      timeline_name +~ rate_delta;
    }
    post {
      timeline_name = value;
      timeline_name += delta;
      timeline_name +~ rate_delta;
      timeline_name =~ absolute_rate;
    }
  }
}
```

**Components:**

- `duration`: Preferred duration 
- `duration_range`: Duration range
- `start`: Preferred start time 
- `start_range` / `end_range`: Time windows for when task can start/end
- `after`: Task ordering dependencies (must start after other tasks end). Supports optional time gaps. Note that an `after X` constraint in a task definition
   means that the task must occur after some instance of the task definition `X`.
- `containedin`: Task must execute during another task. Supports optional start/end offsets. Note that a `containedin X` constraint in a task definition
   means that the task must be contained in some instance of the task definition `X`.
- `pre`: Preconditions (must hold at task start)
- `inv`: Invariants (must hold throughout task execution)
- `post`: Postconditions (must hold at task end)
- `impacts`: Effects on timelines (assignments, deltas, rates)

---

## Timelines

Timelines model state variables and resources that change over time. Each timeline has a type that determines what values it can hold and how it can be modified.

There are five kinds of timelines, shown here in schematic form:

```
name : state(value1, value2, ...) = initial_value;
name : bool = true/false;           # Syntactic sugar for state(true, false)
name : atomic = 0/1;
name : claim [min, max] = initial_value;
name : cumulative [min_rate, max_rate] bounds [min, max] = initial_value;
name : rate [min_rate, max_rate] bounds [min, max] = initial_value initial_rate = rate_value;
```

The state timeline is an enumerate type of a finite number of values, which
can be names or numbers. The **bool timeline** is syntactic sugar for `state(true, false)` - a TaskSAT-specific convenience feature (MEXEC uses explicit STATE_TIMELINE). The atomic timeline is an integer [0,1] timeline with cumulative-only semantics for mutual exclusion patterns (0 = unclaimed, 1 = claimed). The three other timelines denote floating point numbers and allow different kinds of operations. They each have an optional range of values that a schdule must stay within. In addition, the cumulative and rate timelines have an optional minimal and maximal bound, and any value computed during the execution of a schedule will be clamped to stay in that interval. It is effectively the type of the timeline, whereas the first interval is a subtype of that.

**Rate Timelines with Initial Rate:**

Rate timelines track both a VALUE (the resource level) and a RATE (how fast it changes per time unit). The `initial_rate` parameter sets the default rate of change when no task is affecting the timeline. The value evolves as the integral of the rate over time:

```
value(t) = value(t₀) + ∫[t₀ to t] rate(τ) dτ
```

Example:
```tasknet
battery : rate [-5.0, 5.0] bounds [0.0, 100.0] = 50.0 initial_rate = -0.1;
```

This defines a battery timeline with:
- Initial value: 50.0
- Initial rate: -0.1 (drains at 0.1 units per time step by default)
- Rate bounds: [-5.0, 5.0] (can charge up to 5.0 or drain up to -5.0)
- Value bounds: [0.0, 100.0] (clamped to this range)

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

## A Word on Constraints

The constraints shown above for initializing timelines represent the general form of constraints, also used in pre, inv, and post conditions introduced below.

## Impact Operations

There are four different ways to update a timeline:

- **Assignments**:
  * `timeline = value`
- **Cumulative updates** (adds/subtracts a delta to the value):
  * `timeline += value`
  * `timeline -= value`
- **Cumulative rate updates** (adds/subtracts a delta to the rate):
  * `timeline +~ value`
  * `timeline -~ value`
- **Rate assignment** (sets the rate to an absolute value):
  * `timeline =~ value`

Cumulative and rate updates only work on numeric timelines (claimable, cumulative, rate).

**Rate Updates vs Rate Assignment:**

For rate timelines, there are two distinct operations:
- **Cumulative rate** (`+~`, `-~`): Adds or subtracts from the current rate
  - Example: If rate = 1.0 and task does `+~ 2.0`, new rate = 3.0
  - MAINT impacts automatically restore: `+~ 2.0` at start, `-~ 2.0` at end
- **Rate assignment** (`=~`): Sets the rate to an absolute value
  - Example: If rate = 1.0 and task does `=~ 5.0`, new rate = 5.0
  - Only allowed in PRE and POST (not MAINT) due to restoration complexity

The meaning of these updates depend on which impact kind it conerns:

- pre: when the task starts
- maint: during the execution of the task
- post: at the end of the task

Their impacts are shown in the following figure (from MEXEC User’s Guide
Version 1.5.0, May 1, 2024):

![Impacts](impacts.png)

This table shows which impact operations are allowed on each timeline type:

| Timeline Type | Assignment (`=`) | Delta (`+=`/`-=`) | Rate Cumulative (`+~`/`-~`) | Rate Assignment (`=~`) | When Allowed |
|---------------|------------------|-------------------|-----------------------------|------------------------|--------------|
| **State** | ✓ | ✗ | ✗ | ✗ | Assignment: pre/post only |
| **Atomic** | ✗ | ✓ | ✗ | ✗ | Assignment: **not allowed** (use cumulative instead)<br>Delta: pre/maint/post (for claim/release) |
| **Claimable** | ✗ | ✓ | ✗ | ✗ | Delta: maint only |
| **Cumulative** | ✓ | ✓ | ✗ | ✗ | Delta: pre/maint/post<br>Assignment: pre/post only |
| **Rate** | ✓ | ✓ | ✓ | ✓ | Delta/Rate Cumulative: pre/maint/post<br>Assignment (value or rate): pre/post only |

**Notes:**
- **Atomic timelines** support **only cumulative impacts** (`+= 1` to claim, `-= 1` to release) for mutual exclusion patterns. Assignment (`= 0` or `= 1`) is not allowed because it doesn't enforce mutual exclusion—multiple tasks can assign the same value without conflict. Use MAINT timing for automatic claim/release at task start/end.
- **Rate assignment (`=~`) with MAINT** is not supported due to restoration complexity in the zone-based model. Use cumulative rate impacts (`+~`/`-~`) with MAINT, which automatically restore (e.g., `+~ 2.0` at start, `-~ 2.0` at end).

### Impact Timing: When Do Changes Take Effect?

**Important:** Impacts do not modify timeline values at the exact moment they fire—they take effect in the "next" zone.

When a task starts, its PRE impacts modify the timeline values that will be used *during* task execution (not before). Similarly, POST impacts modify values that *next* tasks will see (not during the current task).

**Example:**
```tasknet
timeline battery : cumulative [0, 100] = 100;

task discharge {
  pre { battery >= 50; }        // Checks: do we have enough battery?
  impacts { pre { battery = 0; } }  // Discharge it
}
```

**What happens:**
1. Pre-condition checks `battery = 100` (the value *before* the impact) ✓
2. Impact sets `battery = 0` for use *during* task execution
3. Task executes with `battery = 0`

If impacts modified values immediately, the pre-condition would check `battery = 0` and fail, even though we *did* have enough battery to start!

**Why this matters:**
- Pre-conditions see the "input state" (before task modifies anything)
- Invariants see the "execution state" (after pre/maint impacts take effect)
- Post-conditions see the "end state" (before post impacts and cleanup)

**Exception for rate impacts:** Rate changes (`+~`, `-~`, `=~`) take effect immediately so the task executes with the new rate from the start. This is necessary for correct rate evolution. Value impacts on rate timelines (`+=`, `-=`, `=`) follow the standard delayed timing.

## Task Definitions and Instances

TaskSAT supports reusable task definitions that can be instantiated multiple times.

**Task Definitions**

Define a reusable task template with `taskdef`:

```tasknet
taskdef charge_def {
  pre {
    battery in [0.0, 60.0];
  }
  impacts {
    maint {
      battery +~ 2.0;  // Cumulative: adds 2.0 to current rate during task
    }
  }
}
```

**Task Instances**

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

### Auto-Instantiation

When a task has type-level dependencies (references to `taskdef` names in `after` or `containedin` constraints), TaskSAT automatically creates instances of those taskdefs if none exist.

**How it works:**

1. **One instance per dependent task**: Each task that depends on a taskdef gets its own instance (MEXEC semantics)
2. **Automatic naming**: Auto-created instances are named `{taskdef}_auto_0`, `{taskdef}_auto_1`, etc.
3. **Inherits task kind**: Auto-instances inherit the task kind (INSTANCE, OPTIONAL, REQUEST) from their dependent task
4. **No cascade**: Only direct dependencies are instantiated; dependencies of auto-created instances are not

**Example: Thermal Management Pattern**

```tasknet
taskdef preheat {
  duration_range [50, 100];
  impacts { maint { battery +~ -0.2; temperature +~ 0.5; } }
}

taskdef maintainheat {
  duration_range [110, 120];
  impacts { maint { battery +~ -0.05; temperature +~ -0.05; } }
  after preheat;  // Type-level dependency
}

taskdef downlink {
  duration_range [50, 100];
  inv { temperature in [25.0, 50.0]; }
  impacts { maint { battery +~ -0.3; } }
  after preheat;           // Type-level dependency
  containedin maintainheat; // Type-level dependency
}

// Just specify the downlinks:
task downlink_0 : downlink { start_range [100, 300]; }
task downlink_1 : downlink { start_range [500, 700]; }
```

**Auto-instantiation creates 4 thermal tasks:**
- `preheat_auto_0`, `maintainheat_auto_0` (for downlink_0)
- `preheat_auto_1`, `maintainheat_auto_1` (for downlink_1)

Each downlink gets its own thermal management sequence, reducing manual specification from 6 tasks to 2 tasks.

**Example: Rover with Pre-Drive Checks**

```tasknet
taskdef predrive {
  duration_range [300, 300];
  impacts { maint { checks += 1; } }
}

taskdef drive {
  after predrive;  // Each drive needs a predrive
  duration_range [5000, 7000];
  impacts { maint { distance +~ 0.3; } }
}

task drive1 : drive { start_range [5000, 10000]; }
task drive2 : drive { start_range [15000, 20000]; }
```

**Auto-instantiation creates:**
- `predrive_auto_0` (before drive1)
- `predrive_auto_1` (before drive2)

This is **by design** (MEXEC semantics): each drive gets its own independent predrive instance. The solver can schedule them at different times based on when each drive needs to start. In the example above:
- `predrive_auto_1` might run at 7425-7725
- `predrive_auto_0` might run at 7726-8026
- They can overlap or run in any order

**Why one instance per dependent?**
- **Independence**: Each dependent task can have its own timing for the required predecessor
- **Flexibility**: The solver can schedule predecessors optimally for each dependent
- **MEXEC compatibility**: Matches JPL's MEXEC scheduling system behavior

**When auto-instantiation is skipped:**

If you manually create any instances of a taskdef, auto-instantiation is skipped for that taskdef (assumes you're managing instances manually).

**Example: Manual control**
```tasknet
taskdef predrive { duration 300; }
taskdef drive { after predrive; }

task predrive1 : predrive {}  // Manual instance exists
task drive1 : drive {}
task drive2 : drive {}

# Result: NO auto-instantiation of predrive
# Both drive1 and drive2 will reference the single predrive1 instance
# (solver must ensure predrive1.end <= drive1.start AND predrive1.end <= drive2.start)
```

**Standalone Tasks**

Tasks can also be defined directly without using definitions:

```tasknet
task drive {
  duration 30;
  pre { battery >= 50.0; }
  impacts {
    maint { battery -~ 1.5; }  // Cumulative: subtracts 1.5 from current rate during task
  }
}
```

## Tasks

Tasks represent operations with durations, constraints, and effects.

All task fields are optional unless marked as required.

**id**
- A task can have a numeric id (integer) different from the name, but it is not currently used
- Example: `id` 1;

**duration**
- Preferred duration
- Example: `duration` 10;

**duration_range**
- Duration range which is enforced
- Example:`duration_range` [10, 50];

**start** 
- Preferred start time: 
- Example: `start` 100;

**start_range** / **end_range**
- Constrain when task can start/end
- Example: `start_range` [0, 50];
- Example: `end_range` [100, 200];

**priority**
- Integer priority for scheduling preferences (higher values = higher priority)
- Example: `priority` 10;

**after**
- Task ordering: this task must start after other tasks end
- Syntax:
  - `after A;` - No gap (immediate succession allowed): `B.start >= A.end`
  - `after A [min, max];` - Time gap range: `B.start ∈ [A.end + min, A.end + max]`
  - `after A num;` - Shorthand for `[0, num]`: `B.start ∈ [A.end, A.end + num]`
  - Multiple dependencies: `after A [10, 20], B 30, C;`
- Examples:
  - `after warmup, calibrate;` - Start after both warmup and calibrate end
  - `after predrive [50, 100];` - Start 50-100 time units after predrive ends
  - `after charge 30;` - Start within 30 time units after charge ends
- Can reference task instance names or taskdef names (type-level dependencies)
- When referencing a taskdef name, TaskSAT automatically creates instances if none exist (see Auto-Instantiation)

**containedin**
- Hierarchical constraint: this task must execute entirely within another task.
- Syntax:
  - `containedin A;` - No offsets: `A.start <= child.start AND child.end <= A.end`
  - `containedin A [s_min, s_max] [e_min, e_max];` - Full ranges:
    - Start offset: `child.start ∈ [A.start + s_min, A.start + s_max]`
    - End offset: `child.end ∈ [A.end - e_max, A.end - e_min]`
  - `containedin A num1 num2;` - Shorthand for `[0, num1] [0, num2]`
  - `containedin A num;` - Shorthand for `[0, num] [0, num]`
  - Mixed syntax: `containedin A 10 [20, 30];` - First offset shorthand, second full range
- Examples:
  - `containedin daylight, communication_window;` - Must be within both windows
  - `containedin warmup [5, 10] [5, 10];` - Start 5-10 after warmup starts, end 5-10 before warmup ends
  - `containedin observation 20;` - Start within 20 of parent start, end within 20 of parent end
- Can reference task instance names or taskdef names (type-level dependencies)
- When referencing a taskdef name, TaskSAT automatically creates instances if none exist (see Auto-Instantiation)

**optional** 
- Marks task as optional, it may only be scheduled if needed
- Example: `optional` task bonus_science { ... }

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
- Example:
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
- Example:
```tasknet
properties {
  prop name1: formula1;
  prop name2: formula2;
  ...
}
```

### Task Kinds: Required, Optional, and Request

TaskSAT supports three kinds of tasks:

1. **Required tasks** (default `task` keyword): Must be scheduled
2. **Optional tasks** (`optional task` keyword): Scheduled only if needed to satisfy constraints. In optimize mode, their inclusion is minimized.
3. **Request tasks** (`request task` keyword): Scheduled if possible while satisfying constraints. In optimize mode, their inclusion is maximized.

**Satisfy mode**: Optional and request tasks behave identically - they may or may not be scheduled based on constraints.

**Optimize mode**: 
- Optional tasks: Minimize inclusion (use only if needed)
- Request tasks: Maximize inclusion (use as many as possible)

**Example**:
```tasknet
task required_mission {
  duration 50;
}

optional task emergency_backup {
  # Only scheduled if needed to satisfy constraints
  duration 30;
}

request task bonus_objective {
  # Scheduled if possible, even if not strictly needed
  duration 20;
}
```

Priority values further refine the optimization among optional and request tasks (higher priority = more important).

### Instance Range Syntax

TaskSAT supports compact syntax for creating multiple task instances with a mix of required and optional/request instances.

#### Range Notation

**Syntax:**
```tasknet
task <name>[<min>..<max>] : <taskdef> { ... }
request task <name>[<min>..<max>] : <taskdef> { ... }
```

Creates `min` required instances and `(max - min)` optional/request instances, numbered sequentially from 0 to (max-1).

**Example:**
```tasknet
task science[2..4] : science_def {
  id 100;
  priority 50;
}
```

Expands to:
```tasknet
task science_0 : science_def { id 100; priority 50; }  # required
task science_1 : science_def { id 101; priority 50; }  # required
optional task science_2 : science_def { id 102; priority 50; }
optional task science_3 : science_def { id 103; priority 50; }
```

#### Count Notation

**Syntax:**
```tasknet
task <name>[<count>] : <taskdef> { ... }
```

Equivalent to `task <name>[0..<count>]` - creates all optional instances (min=0).

**Example:**
```tasknet
request task bonus[3] : work { }
```

Expands to:
```tasknet
request task bonus_0 : work { }
request task bonus_1 : work { }
request task bonus_2 : work { }
```

#### Optimization Behavior

- **`task T[min..max]`**: Creates required + optional instances. Optional instances are minimized (scheduled only if needed).
- **`request task T[min..max]`**: Creates required + request instances. Request instances are maximized (scheduled if possible).

In satisfy mode (default), both behave the same - instances may or may not be scheduled based on constraints.

#### ID Assignment

When an `id` is specified in a range declaration, IDs are auto-incremented for each instance:

```tasknet
task T[2..4] { id 100; }
# Assigns: T_0=100, T_1=101, T_2=102, T_3=103
```

#### Constraints

- Cannot use `optional` keyword with ranges: `optional task T[2..4]` is invalid
- Use `task T[2..4]` for optional instances or `request task T[2..4]` for request instances
- `min` must be ≤ `max`
- Both `min` and `max` must be non-negative

### Temporal Constraints

Temporal constraints mentioned just above are 
expressed in a linear temporal logic with future and past time
temporal operators.

**Atomic Formulas**

- `true` - always true
- `false` - always false
- `timeline = value` 
- `timeline >= value`
- `timeline <= value`
- `timeline < value`
- `timeline > value`

Where value can be a name (for state timelines), a Boolean (for atomic timelines), or an integer or float.

**Note:** For rate/cumulative timelines, `timeline = number` is interpreted as state equality (for compatibility with state timelines that have numeric state names). For numeric equality on rate timelines, use: `timeline >= value` combined with `timeline <= value`, or `timeline in [value, value]`.

In addition the following formula:

- `active`(task)

is true when the specified task is executing.

**Logical operators:**

- `not` φ
- φ1 `and` φ2
- φ1 `or` φ2
- φ1 `->` φ2 (implication; can also use `implies` keyword)

**Temporal operators**

Future time:

- `always` φ - φ is true always in the future, including now
- `eventually` φ - φ is true at some future time
- φ1 `until` φ2 = φ2 eventually is true and until then (not including) φ1 is true

Past time:

- `sofar` φ - φ is true always in the past, including now
- `once` φ - φ is true at some past time
- φ1 since φ2 - φ2 once was true and since then (not including) φ1 is true

**Time variable and task boundaries**

In addition to timeline references, temporal formulas can reference:

- `time` - the current time point in the schedule
- `task.start` - the start time of a task
- `task.end` - the end time of a task

These are **constants** (determined once by the solver) that can be compared with each other, with `time`, or with numeric constants:

```tasknet
# Task ordering without active()
prop T1_after_T2: T1.start >= T2.end;

# Time windows
prop early_start: task1.start < 100;
prop late_end: task2.end > 200;

# Comparing with current time
prop before_task: always (time < task1.start -> battery > 50.0);

# Complex orderings
prop sequential: T1.end <= T2.start and T2.end <= T3.start;
```

**Important semantics:**
- Referencing `task.start` or `task.end` where `task` is optional/request is **conditional** - the constraint evaluates to `true` if the task is not scheduled
- This matches `active(task)` semantics and allows converting `always (active(T) -> constraint)` to just use `T.start`/`T.end`
- `time`, `task.start`, and `task.end` are more efficient than `active(task)` because they don't create additional timelines
- Use `task.start`/`task.end` for ordering constraints; use `active(task)` for checking if a task is executing at a specific time point

**Sequence construct**

For sequential task execution, TaskNet provides the `sequence` construct as syntactic sugar:

```tasknet
prop ordering: sequence [task1, task2, task3, task4];
```

This is equivalent to writing:

```tasknet
prop ordering:
  task1.end <= task2.start and
  task2.end <= task3.start and
  task3.end <= task4.start;
```

The `sequence` construct:
- Takes a list of task names in square brackets
- Desugars to pairwise `.end <= .start` constraints
- Can be used in both `constraints` and `properties` blocks
- Is more concise and less error-prone than manually writing pairwise constraints

**Mutex construct**

For mutual exclusion (tasks that cannot overlap in time), TaskNet provides the `mutex` construct:

```tasknet
# Within-group exclusion: no two tasks in the list can overlap
mutex [science1, science2, science3];

# Between-group exclusion: no task from group A can overlap with any task from group B
mutex [drive1, drive2] with [science1, science2];
```

Within-group mutex `[A, B, C]` desugars to:
```tasknet
(A.end <= B.start or B.end <= A.start) and
(A.end <= C.start or C.end <= A.start) and
(B.end <= C.start or C.end <= B.start)
```

Between-group mutex `[A, B] with [C, D]` desugars to the cross-product of non-overlap conditions.

The `mutex` construct:
- Takes one or two lists of task names in square brackets
- Desugars to non-overlap constraints using task boundaries
- Can be used in both `constraints` and `properties` blocks
- More efficient than using `active()` predicates (doesn't create additional timelines)
- More concise than complex temporal logic with `active()` and `implies`

**Named vs. unnamed constraints**

Both `sequence` and `mutex` (and any temporal formula) can be used with or without explicit names:

```tasknet
constraints {
  # Named constraints (useful for debugging/documentation)
  prop mission_order: sequence [charge, drive, science];
  prop exclusive_ops: mutex [drive1, drive2] with [science1, science2];
  
  # Unnamed constraints (more concise, auto-named)
  mutex [science1, science2];
  sequence [task1, task2, task3];
  always (battery >= 20.0);
}
```

Unnamed constraints are automatically given descriptive names:
- `mutex [A, B]` → `"mutex_A_B"`
- `sequence [A, B, C]` → `"sequence_A_B_C"`
- Other formulas → `"constraint_1"`, `"constraint_2"`, etc.
- Works with any number of tasks (2 or more)

**Example:**

```tasknet
constraints {
  // Sequential downlink operations
  prop downlinks: sequence [
    preheat_0,
    downlink_0,
    preheat_1,
    downlink_1,
    preheat_2,
    downlink_2
  ];
  
  // Equivalent to:
  // prop downlinks:
  //   preheat_0.end <= downlink_0.start and
  //   downlink_0.end <= preheat_1.start and
  //   preheat_1.end <= downlink_1.start and
  //   ...
}
```

**Examples**

```tasknet
  # Battery must always stay above 20%
  prop battery_safe: always battery > 20.0;

  # Rover must eventually reach the target
  prop reach_target: eventually location = target;

  # If battery is low, we must eventually charge (using -> syntax)
  prop charge_when_low: always(battery < 30.0 -> eventually active(charge));

  # Alternative: using 'implies' keyword (equivalent to ->)
  prop charge_when_low_alt: always(battery < 30.0 implies eventually active(charge));

  # Heating and cooling never happen simultaneously
  prop exclusive_thermal: always (not (active(heating) and active(cooling)));

  # Data collection happens after warming up
  prop collect_after_warmup: active(collect_data) -> once active(warmup);

  # Battery must stay above safe level until charging starts
  prop safe_until_charge: (battery > 20.0) until active(charge);

  # Using true/false constants
  prop tautology: always (true or false);
  prop conditional: true -> (battery >= 0.0);
  prop negation: always (not false);

  # Using time and task boundaries
  prop task_ordering: drive.start >= preheat.end;
  prop early_completion: collect_data.end < 500;
  prop minimum_gap: transmit.start >= collect_data.end + 100;
  prop time_window: always (time > 1000 -> battery >= 40.0);
```

### Property Verification Output

When you run the TaskSAT verifier, it checks all properties and generates detailed reports:

**Console output:**
```
✓ Property battery_safe holds
✗ Property battery_critical violated
  Violation detected at zones: [0, 2, 4]
  Error trace saved to: .tasksat/schedules/tasknet/2026-06-10_14-30-15/errors/
```

**Generated files** (in `.tasksat/schedules/<tasknet>/<timestamp>/`):
- `properties.json` - Comprehensive property verification summary
- `errors/<property>_timeline.png` - Visual error trace with violation zones highlighted
- `errors/<property>_schedule.json` - Counterexample schedule
- `errors/<property>_timeline.json` - Timeline evolution data

**Properties JSON format:**
```json
[
  {
    "name": "battery_safe",
    "status": "holds",
    "duration_sec": 0.027,
    "formula": "always (battery >= 20.0)"
  },
  {
    "name": "battery_critical",
    "status": "violated",
    "duration_sec": 0.006,
    "formula": "always (battery >= 0.0)",
    "violation_zones": [0, 2, 4]
  }
]
```

**Status values:**
- `holds` - Property is satisfied by the schedule
- `violated` - Property is violated (counterexample generated)
- `unknown` - Verification inconclusive

**Violation zones:** For `always` formulas, the verifier identifies specific time zones where the property fails. These zones are highlighted in red in the error trace visualization.

**Web UI:** Use the web interface to browse property results and compare error traces:
```bash
python src/smt/tasknet_web.py
# Navigate to http://localhost:5000 to view verification reports
```

## User-Guided Scheduling

For large tasknets (100+ tasks), the SMT solver may timeout. You can guide the solver by adding temporal constraints that narrow the search space.

### Viewing Auto-Instantiated Tasks

Auto-instantiated tasks (e.g., `preheat_auto_0`) only exist in the transformed AST after parsing. When auto-instantiation occurs, the verifier **automatically writes** the transformed tasknet to `.tasksat/transformed/<filename>_transformed.tn`:

```bash
# Normal verification (auto-writes transformed file if auto-instantiation occurs)
python src/smt/tasknet_verifier.py input.tn

# Skip verification and only generate transformed file
python src/smt/tasknet_verifier.py input.tn --transform-only
```

**Example output when auto-instantiation occurs:**

```
*** Auto-instantiated 2 task(s) from taskdefs:
    predrive_auto_0 (from taskdef predrive)
    predrive_auto_1 (from taskdef predrive)

📄 Transformed tasknet written to: .tasksat/transformed/input_transformed.tn
```

The transformed tasknet shows all auto-instantiated tasks as explicit task declarations. Generated files are stored in `.tasksat/transformed/` to keep your project organized. You can then edit the transformed file to add scheduling hints.

**Inspecting the transformed file:**

```bash
# View which tasks were auto-instantiated
cat .tasksat/transformed/input_transformed.tn

# You'll see explicit task declarations like:
# task predrive_auto_0 : predrive {
#   id 101;
#   # Inherited from drive1 which depends on predrive
# }
```

**Use cases for transformed files:**
1. **Understanding what was instantiated**: See exactly which instances were created and why
2. **Adding scheduling hints**: Edit the transformed file to add `start_range`, `priority`, etc. to auto-instances
3. **Debugging**: Verify that auto-instantiation created the expected number of instances
4. **Manual control**: Convert an auto-instantiated tasknet to fully manual by using the transformed file as your source

**Note**: The `.tasksat/` directory is automatically added to `.gitignore` to avoid committing generated files.

### Schedule Output

The LLM-based scheduler (for large tasknets) writes schedules and visualizations to `.tasksat/schedules/`:

```bash
python jpl/tools/llm_scheduler.py tasknet.tn
# Generates:
#   .tasksat/schedules/tasknet_schedule.json
#   .tasksat/schedules/tasknet_schedule.png
```

All TaskSAT-generated artifacts are organized under `.tasksat/`:
- `.tasksat/transformed/` - Transformed tasknets with auto-instantiated tasks
- `.tasksat/schedules/` - Generated schedules and visualizations

### Example: Adding Scheduling Hints

Given a tasknet with auto-instantiated thermal management:

```tasknet
taskdef preheat { ... }
taskdef maintainheat { after preheat; ... }
taskdef downlink { after preheat; containedin maintainheat; ... }

task downlink_0 : downlink { start_range [100, 300]; }
task downlink_1 : downlink { start_range [500, 700]; }
```

Auto-instantiation creates: `preheat_auto_0`, `preheat_auto_1`, `maintainheat_auto_0`, `maintainheat_auto_1`.

After running the verifier (which auto-writes the transformed file), edit `.tasksat/transformed/<filename>_transformed.tn` to add hints:

```tasknet
constraints {
  # Temporal ordering: complete downlink_0 before starting downlink_1
  prop downlink_sequential:
    active(downlink_1) -> once active(downlink_0);

  # Task grouping: cluster thermal operations early
  prop thermal_early:
    always (active(preheat_auto_0) -> preheat_auto_0.start < 500);
    
  # Resource management: spread battery-heavy operations
  prop spread_downlinks:
    active(downlink_0) -> (downlink_1.start - downlink_0.end > 200);
}
```

### Common Patterns

**Temporal Ordering**:
```tasknet
# Task A must complete before task B starts
prop A_before_B: active(B) -> once active(A);

# Bound task start time
prop early_start: active(task) -> task.start < 1000;
```

**Task Grouping**:
```tasknet
# Cluster tasks within time window
prop cluster: active(A) -> (B.start - A.end < 100);
```

**Mutual Exclusion**:
```tasknet
# Modern syntax - more concise
mutex [A, B];

# Or using active() predicates (less efficient)
prop exclusive: always (active(A) -> not active(B));
```

