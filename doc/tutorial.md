# TaskSAT Tutorial

This tutorial provides an in-depth walkthrough of TaskSAT concepts, patterns, and best practices.

> **Prerequisites**: Install TaskSAT and run your first example by following [Getting Started](getting-started.md) first. This tutorial assumes you've already seen the basic MyRobot example.

## Understanding Timelines

Timelines are the foundation of TaskSAT - they model state variables and resources that change over time. Let's explore each type in detail.
    active tasks : drive
    battery        = 90 -> 60
    location       = target

  -- zone 3: (55, 100] --
    active tasks : (none)
    battery        = 60 -> 60
    location       = target

Temporal properties:
  ✓ battery_safe: always (battery >= 0.0)
```

**What this tells us:**
- The robot charges from time 0 to 20 (battery: 50 → 90)
- It waits from 20 to 25
- It drives from 25 to 55 (battery: 90 → 60)
- Battery stays above 0 throughout (property satisfied ✓)

## Basic Concepts

### Timelines

Timelines represent state variables or resources that change over time:

```tasknet
timelines {
  battery   : rate [min_rate, max_rate] bounds [min, max] = initial;
  mode      : state(idle, active, done) = idle;
  sensor    : atomic = false;
  memory    : claim [0.0, 100.0] = 100.0;
  data      : cumulative [0.0, 1000.0] bounds [0.0, 1000.0] = 0.0;
}
```

**Timeline Types:**
- **state**: Discrete values (e.g., mode names, numeric states like 0, 1, 2)
- **atomic**: Boolean (true/false)
- **claim**: Numeric resource that can be claimed/released
- **cumulative**: Numeric accumulator (can only increase or stay same)
- **rate**: Numeric with rate of change (models continuous dynamics)

### Tasks

Tasks are operations that:
- Have a defined duration or duration range
- Require certain conditions to hold (preconditions, invariants, postconditions)
- Affect resources (impacts)

```tasknet
task my_task {
  id 1;
  duration 10;              // Fixed duration
  // OR
  duration_range [5, 15];   // Variable duration

  pre {
    // Must be true when task starts
    battery in [20.0, 100.0];
  }

  inv {
    // Must be true throughout task execution
    temperature in [0.0, 50.0];
  }

  post {
    // Must be true when task ends
    data in [10.0, 100.0];
  }

  impacts {
    pre {
      // Effects that occur at task start
      mode = active;
    }
    maint {
      // Effects throughout task duration
      battery +~ -0.5;  // Rate: drain 0.5/time
    }
    post {
      // Effects that occur at task end
      mode = idle;
      data += 10.0;  // Delta: add 10 units
    }
  }
}
```

### Impact Operators

Different operators for different effects:

- **Assignment** (`=`): Set a value
  ```tasknet
  mode = active;
  sensor = true;
  ```

- **Delta** (`+=`, `-=`): Instant change
  ```tasknet
  data += 10.0;    // Add 10 units at this moment
  memory -= 5.0;   // Remove 5 units at this moment
  ```

- **Rate** (`+~`, `-~`): Continuous change over time
  ```tasknet
  battery +~ 2.0;     // Charge at 2 units/time
  temperature -~ 0.1; // Cool at 0.1 degrees/time
  ```

### Impact Timing

- **pre**: Effect occurs at task start boundary
- **maint**: Effect active during task execution
- **post**: Effect occurs at task end boundary

Example showing timing:
```tasknet
task heating {
  duration 10;

  impacts {
    pre {
      heater = on;        // Turn on at t=start
    }
    maint {
      temperature +~ 1.0; // Heat throughout [start, end)
    }
    post {
      heater = off;       // Turn off at t=end
    }
  }
}
```

### Constraints

Express temporal properties that must hold:

```tasknet
constraints {
  prop name: always (battery >= 20.0);
  prop name2: eventually (location = target);
  prop name3: (battery < 30.0) -> (eventually (active(charge)));
}
```

**Temporal Operators:**
- `always φ`: φ holds at all times
- `eventually φ`: φ holds at some future time
- `once φ`: φ has held at some past time
- `φ until ψ`: φ holds until ψ becomes true
- `φ since ψ`: φ has held since ψ was true

## Solver Modes

TaskSAT supports two verification modes:

### Satisfy Mode (Faster)

Finds any valid schedule:

```bash
python src/smt/tasknet_verifier.py my_robot.tn --mode satisfy
```

**Use when:**
- You just want to know if a schedule exists
- You need quick feedback
- Debugging constraints

**Advantages:**
- Faster (often significantly)
- Provides unsat core for debugging
- Good for feasibility checks

### Optimize Mode (Default)

Finds an optimal schedule (minimizes optional tasks):

```bash
python src/smt/tasknet_verifier.py my_robot.tn --mode optimize
```

**Use when:**
- You have optional tasks
- You want the best schedule
- You need to maximize/minimize objectives

**Trade-offs:**
- Slower (can be much slower for complex problems)
- Explores multiple solutions
- May timeout on hard problems

## Common Patterns

### Sequential Tasks

Use `after` keyword:

```tasknet
task task1 {
  id 1;
  duration 10;
}

task task2 {
  id 2;
  duration 10;
  after task1;  // task2 must start after task1 ends
}
```

### Optional Tasks

Use `optional` keyword:

```tasknet
optional task bonus_science {
  id 3;
  duration 20;
  // ... will be included only if beneficial
}
```

### Resource Constraints

Model shared resources:

```tasknet
timelines {
  memory : claim [0.0, 100.0] = 100.0;
}

task task1 {
  pre { memory in [50.0, 100.0]; }
  impacts {
    pre { memory -= 30.0; }    // Claim 30 units
    post { memory += 30.0; }   // Release 30 units
  }
}

task task2 {
  pre { memory in [40.0, 100.0]; }
  impacts {
    pre { memory -= 40.0; }
    post { memory += 40.0; }
  }
}
```

If both tasks try to run simultaneously with only 100 units total, the solver will schedule them to not overlap.

## Troubleshooting

### Problem: UNSAT (No Solution)

```
unsat
No solution found
```

**Possible causes:**
1. Over-constrained problem (impossible requirements)
2. Insufficient resources
3. Conflicting constraints
4. Time horizon too short

**Debugging:**
- Use `--mode satisfy` for unsat core
- Check resource bounds
- Increase `end` time
- Relax constraints temporarily

### Problem: Timeout

**If in optimize mode:**
- Try `--mode satisfy` first
- Reduce number of optional tasks
- Simplify problem

**If in satisfy mode:**
- Problem may be genuinely hard
- Consider simplifying constraints
- See [performance.md](performance.md) for scaling guidelines

### Problem: Unexpected Schedule

**Check:**
- Impact timing (pre/maint/post)
- Task dependencies (after clause)
- Resource initial values
- Constraint formulas

## Next Steps

- Read [language-reference.md](language-reference.md) for complete syntax details
- Explore [examples.md](examples.md) for more complex patterns
- Check [performance.md](performance.md) to understand scaling
- Study [architecture.md](architecture.md) to understand the encoding

## Quick Reference

```tasknet
tasknet Name {
  end = time_horizon;

  timelines {
    tl1 : state(val1, val2, ...) = initial;
    tl2 : atomic = true|false;
    tl3 : claim [min, max] = initial;
    tl4 : cumulative [min, max] bounds [min, max] = initial;
    tl5 : rate [min_rate, max_rate] bounds [min, max] = initial;
  }

  [optional] task name {
    id number;
    [priority number;]
    duration fixed_duration;
    // OR
    duration_range [min, max];

    [after other_task;]

    [pre { constraints }]
    [inv { constraints }]
    [post { constraints }]

    [impacts {
      [pre { timeline_impacts }]
      [maint { timeline_impacts }]
      [post { timeline_impacts }]
    }]
  }

  [constraints {
    prop name: temporal_formula;
  }]
}
```

**Impact operators:**
- `timeline = value` (assignment)
- `timeline += value` (delta)
- `timeline +~ value` (rate)
- `timeline in [min, max]` (range constraint)

**Temporal operators:**
- `always φ`, `eventually φ`, `once φ`, `sofar φ`
- `φ until ψ`, `φ since ψ`
- `active(task)` (true when task is executing)
