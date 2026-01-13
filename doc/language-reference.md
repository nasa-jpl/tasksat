# TaskSAT Language Reference

This document provides complete syntax reference for the TaskSAT DSL.

## File Structure

A TaskSAT specification (`.tn` file) has this overall structure:

```tasknet
tasknet Name {
  end = time_horizon;

  timelines {
    // Timeline declarations
  }

  // Task definitions

  [constraints {
    // Temporal properties
  }]
}
```

## Timelines

Timelines model state variables and resources that change over time.

### State Timeline

Models discrete states (string values or numeric values).

**Syntax:**
```tasknet
name : state(value1, value2, ...) = initial_value;
```

**Examples:**
```tasknet
mode : state(idle, active, done) = idle;
heating : state(off, on) = off;
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
- Rate (`+~`, `-~`) in `pre`, `maint`, `post`

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

## Tasks

Tasks represent operations with durations, constraints, and effects.

### Basic Task Structure

```tasknet
[optional] task name {
  id number;
  [priority number;]

  // Duration specification (choose one)
  duration fixed_value;
  // OR
  duration_range [min, max];

  // Optional: fixed start time
  [start fixed_time;]

  // Optional: start/end time ranges
  [start_range [min, max];]
  [end_range [min, max];]

  // Optional: ordering constraint
  [after other_task;]

  // Optional: constraints
  [pre { ... }]
  [inv { ... }]
  [post { ... }]

  // Optional: impacts
  [impacts {
    [pre { ... }]
    [maint { ... }]
    [post { ... }]
  }]
}
```

### Task Fields

**id** (required)
- Unique integer identifier
- Example: `id 1;`

**priority** (optional)
- Integer priority for scheduling preferences
- Example: `priority 10;`

**duration** (required, choose one)
- Fixed duration: `duration 30;`
- Variable duration: `duration_range [10, 50];`

**start** (optional)
- Fixed start time: `start 100;`

**start_range / end_range** (optional)
- Constrain when task can start/end
- Example: `start_range [0, 50];`

**after** (optional)
- Task ordering: this task must start after another task ends
- Example: `after heating;`

**optional** (keyword)
- Mark task as optional for optimization
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

Properties express conditions that must hold over time.

### Syntax

```tasknet
constraints {
  prop name: formula;
  prop name2: formula2;
  ...
}
```

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
