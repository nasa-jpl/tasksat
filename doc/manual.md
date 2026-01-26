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

### Impact Operations Summary

This table shows which impact operations are allowed on each timeline type:

| Timeline Type | Assignment (`=`) | Delta (`+=`/`-=`) | Rate (`+~`/`-~`) | When Allowed |
|---------------|------------------|-------------------|------------------|--------------|
| **State** | ✓ | ✗ | ✗ | pre, post only |
| **Atomic** | ✓ | ✗ | ✗ | pre, post only |
| **Claimable** | ✗ | ✓ | ✗ | **maint only** |
| **Cumulative** | ✓ (pre/post only) | ✓ (all) | ✗ | Delta: pre/maint/post<br>Assignment: pre/post only |
| **Rate** | ✓ (pre/post only) | ✓ (all) | ✓ (all) | Delta/Rate: pre/maint/post<br>Assignment: pre/post only |

**Key rules:**
- **State & Atomic**: Only assignments, no deltas or rates, no maint assignments
- **Claimable**: ONLY delta impacts in maint (claim/release pattern)
- **Cumulative**: Delta impacts anywhere, assignments only in pre/post, NO rate impacts
- **Rate**: All impact types allowed, but assignments only in pre/post

### State Timeline

Models discrete states (names or numeric values).

**Syntax:**
```tasknet
name : state(value1, value2, ...) = value2;
```

**Examples:**
```tasknet
mode : state(idle, active, done) = idle;
power_level : state(0, 1, 2, 3) = 0;           // Numeric states
temperature_mode : state(0.0, 10.5, 20.0) = 0.0;  // Real-valued states
```

**Constraints:**
- Can use `=` (equality)
- Works in `pre`, `inv`, `post` sections

**Impacts:**
- Assignment (`=`) in `pre` and `post` only
- No `maint` impacts allowed

### Atomic Timeline

Models boolean values (true/false).

**Syntax:**
```tasknet
name : atomic = initial_value;
```

**Examples:**
```tasknet
sensor_active : atomic = false;
heater_on : atomic = true;
```

**Constraints:**
- Can use `=` (equality)
- Works in `pre`, `inv`, `post` sections

**Impacts:**
- Assignment (`=`) in `pre` and `post` only
- No `maint` impacts allowed

### Claimable Timeline

Models consumable/producible resources that can be claimed and released.

**Syntax:**
```tasknet
name : claim [min, max] = initial_value;
name : claimable [min, max] = initial_value;  // Alternative keyword
```

**Examples:**
```tasknet
memory : claim [0.0, 100.0] = 100.0;
bandwidth : claim [0.0, 1000.0] = 500.0;
```

**Constraints:**
- Can use `in [min, max]` (range check)
- Can use comparison operators (`>=`, `<=`, `<`, `>`, `=`)
- Works in `pre`, `inv`, `post` sections

**Impacts:**
- Delta (`+=`, `-=`) in `pre`, `maint`, `post`
  - `pre`: Instant change at task start
  - `maint`: Temporary claim (add at start, subtract at end)
  - `post`: Instant change at task end
- Rate (`+~`, `-~`) in `pre`, `maint`, `post`
  - Continuous change over time

### Cumulative Timeline

Models accumulators that can only increase or decrease monotonically.

**Syntax:**
```tasknet
name : cumulative [min_rate, max_rate] bounds [min, max] = initial_value;
name : cumul [min_rate, max_rate] bounds [min, max] = initial_value;  // Alternative keyword
```

**Examples:**
```tasknet
data_collected : cumulative [0.0, 10.0] bounds [0.0, 1000.0] = 0.0;
fuel_consumed : cumulative [0.0, 5.0] bounds [0.0, 500.0] = 0.0;
```

**Constraints:**
- Can use `in [min, max]` (range check)
- Can use comparison operators
- Works in `pre`, `inv`, `post` sections

**Impacts:**
- Delta (`+=`, `-=`) in `pre`, `maint`, `post`
- Assignment (`=`) in `pre`, `post` only
- **Note:** Rate impacts (`+~`, `-~`) are NOT allowed on cumulative timelines

### Rate Timeline

Models continuous resources with rates of change.

**Syntax:**
```tasknet
name : rate [min_rate, max_rate] bounds [min, max] = initial_value;
```

**Examples:**
```tasknet
battery : rate [-10.0, 10.0] bounds [0.0, 100.0] = 100.0;
temperature : rate [-5.0, 5.0] bounds [0.0, 100.0] = 20.0;
distance : rate [0.0, 50.0] bounds [0.0, 1000.0] = 0.0;
```

**Constraints:**
- Can use `in [min, max]` (range check)
- Can use comparison operators
- Works in `pre`, `inv`, `post` sections

**Impacts:**
- Delta (`+=`, `-=`) in `pre`, `maint`, `post`
  - Instant change to the accumulated value
- Rate (`+~`, `-~`) in `pre`, `maint`, `post`
  - Continuous change over time
  - Example: `battery +~ -1.0` means drain at 1 unit per time

## Initial State Constraints

The `init` block specifies constraints on initial values of timelines. This is optional - if not specified, timelines start with their declared initial values.

**Syntax:**
```tasknet
init {
  timeline_name = value;
  timeline_name in [min, max];
  ...
}
```

**Examples:**
```tasknet
init {
  battery = 50.0;              // Battery must start at exactly 50
  temperature in [10.0, 30.0]; // Temperature can start anywhere in this range
  mode = idle;                 // Mode must start as idle
}
```

**Use cases:**
- Constrain initial values to specific ranges
- Test system behavior under different starting conditions
- Ensure initial state meets safety requirements

**Note:** If a timeline has both a declared initial value and an init constraint, both must be satisfied.

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

### Constraints

Constraints express conditions that must hold at specific points.

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

### Constraint Operators

**For state/atomic timelines:**
- `timeline = value` (equality)

**For numeric timelines:**
- `timeline in [min, max]` (range check)
- `timeline >= value`
- `timeline <= value`
- `timeline < value`
- `timeline > value`
- `timeline = value` (exact value)

**Logical operators:**
- `not condition`
- `condition1 and condition2`
- `condition1 or condition2`
- `condition1 -> condition2` (implication)

### Impacts

Impacts specify how tasks affect timelines.

**Impact timing:**
- **pre**: Effect occurs at task start boundary
- **maint**: Effect active during task execution
- **post**: Effect occurs at task end boundary

**Impact operators:**

1. **Assignment** (`=`)
   - Set a value
   - Only for state/atomic timelines
   - Only in `pre` and `post` (not `maint`)
   - Example: `mode = active;`

2. **Delta** (`+=`, `-=`)
   - Instant change
   - For numeric timelines only
   - Works in `pre`, `maint`, `post`
   - Example: `memory -= 50.0;`
   - Timing:
     - `pre`: Add/subtract at task start
     - `maint`: Add at start, subtract at end (temporary)
     - `post`: Add/subtract at task end

3. **Rate** (`+~`, `-~`)
   - Continuous change over time
   - For numeric timelines only
   - Works in `pre`, `maint`, `post`
   - Example: `battery +~ -0.5;` (drain 0.5 per time unit)
   - Timing:
     - `pre`: Rate active from task start onward (permanent)
     - `maint`: Rate active during task only (temporary)
     - `post`: Rate active from task end onward (permanent)

**Examples:**

```tasknet
impacts {
  pre {
    mode = active;           // Assignment: set state at start
    memory -= 30.0;          // Delta: claim 30 units at start
    battery +~ -1.0;         // Rate: start draining from now on
  }
  maint {
    temperature +~ 0.5;      // Rate: heat during execution
    bandwidth -= 10.0;       // Delta: claim during, release after
  }
  post {
    mode = done;             // Assignment: set state at end
    data_collected += 50.0;  // Delta: add 50 units at end
    battery +~ 0.0;          // Rate: stop draining (set to 0)
  }
}
```

## Temporal Properties

Properties express temporal logic formulas that must hold over all valid schedules.

### Syntax

Properties can be declared in either a `constraints` or `properties` block (they are synonyms):

```tasknet
constraints {
  prop name: formula;
  prop name2: formula2;
  ...
}
```

or equivalently:

```tasknet
properties {
  prop name: formula;
  prop name2: formula2;
  ...
}
```

**Note:** Both blocks have the same semantics. Use whichever name you prefer.

### Temporal Operators

**always φ**
- φ must hold at all times
- Example: `always (battery >= 20.0)`

**eventually φ**
- φ must hold at some future time
- Example: `eventually (mode = done)`

**once φ**
- φ has held at some past time
- Example: `once (sensor_active = true)`

**sofar φ**
- φ has held at all past times
- Example: `sofar (temperature <= 100.0)`

**φ until ψ**
- φ holds until ψ becomes true
- Example: `(battery > 50.0) until (mode = charging)`

**φ since ψ**
- φ has held since ψ was true
- Example: `(temperature < 80.0) since (heater_on = false)`

### Special Predicates

**active(task)**
- True when the specified task is executing
- Example: `eventually active(science_task)`

### Property Examples

```tasknet
constraints {
  // Battery must always stay above 20%
  prop battery_safe: always (battery >= 20.0);

  // Must eventually reach the target
  prop reach_target: eventually (location = target);

  // If battery is low, must eventually charge
  prop charge_when_low: (battery < 30.0) -> eventually active(charge);

  // Heating and cooling never happen simultaneously
  prop exclusive_thermal: always (not (active(heating) and active(cooling)));

  // Data collection happens after warming up
  prop collect_after_warmup: active(collect_data) -> once active(warmup);
}
```

## Complete Example

```tasknet
tasknet ScienceMission {
  end = 200;

  timelines {
    mode : state(idle, warming, collecting, transmitting) = idle;
    battery : rate [-2.0, 5.0] bounds [0.0, 100.0] = 100.0;
    data : cumulative [0.0, 10.0] bounds [0.0, 500.0] = 0.0;
    memory : claim [0.0, 100.0] = 100.0;
    antenna : atomic = false;
  }

  task warmup {
    id 1;
    duration 20;
    priority 10;

    pre {
      mode = idle;
      battery in [50.0, 100.0];
    }

    inv {
      battery in [30.0, 100.0];
    }

    post {
      mode = idle;
    }

    impacts {
      pre {
        mode = warming;
      }
      maint {
        battery +~ -0.5;
      }
      post {
        mode = idle;
      }
    }
  }

  task collect_science {
    id 2;
    duration_range [30, 60];
    after warmup;

    pre {
      mode = idle;
      battery in [40.0, 100.0];
      memory in [50.0, 100.0];
    }

    inv {
      battery in [20.0, 100.0];
      memory in [30.0, 100.0];
    }

    impacts {
      pre {
        mode = collecting;
        memory -= 40.0;
      }
      maint {
        battery +~ -1.0;
        data +~ 2.0;
      }
      post {
        mode = idle;
        memory += 40.0;
      }
    }
  }

  optional task transmit_data {
    id 3;
    duration 40;

    pre {
      mode = idle;
      data in [50.0, 500.0];
      battery in [60.0, 100.0];
    }

    impacts {
      pre {
        mode = transmitting;
        antenna = true;
      }
      maint {
        battery +~ -1.5;
        data +~ -5.0;
      }
      post {
        mode = idle;
        antenna = false;
      }
    }
  }

  constraints {
    prop battery_safe: always (battery >= 15.0);
    prop collect_once: eventually active(collect_science);
    prop warmup_before_collect: active(collect_science) -> once active(warmup);
    prop no_overlap: always (not (active(collect_science) and active(transmit_data)));
  }
}
```

## Grammar Summary

### Keywords
`tasknet`, `end`, `timelines`, `state`, `atomic`, `claim`, `cumulative`, `rate`, `bounds`, `task`, `optional`, `id`, `priority`, `duration`, `duration_range`, `start`, `start_range`, `end_range`, `after`, `pre`, `inv`, `post`, `impacts`, `maint`, `constraints`, `prop`, `always`, `eventually`, `once`, `sofar`, `until`, `since`, `active`, `not`, `and`, `or`, `in`, `true`, `false`

### Operators
- Assignment: `=`
- Delta: `+=`, `-=`
- Rate: `+~`, `-~`
- Comparison: `<`, `>`, `<=`, `>=`
- Logical: `not`, `and`, `or`, `->`
- Range: `in [min, max]`

### Comments
- Single line: `// comment`
- Multi-line: `/* comment */`

### Identifiers
- Timeline names: Start with letter, can contain letters, digits, underscores
- Task names: Same rules as timeline names
- Property names: Same rules as timeline names

### Numbers
- Integers: `0`, `42`, `-10`
- Reals: `0.0`, `3.14`, `-2.5`

### Strings
- State values: Unquoted identifiers like `idle`, `active`
- Can also use numeric values: `0`, `1`, `2.5`
