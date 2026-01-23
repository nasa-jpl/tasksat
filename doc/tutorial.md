# TaskSAT Tutorial

This tutorial provides an in-depth walkthrough of TaskSAT concepts, patterns, and best practices.

> **Prerequisites**: Install TaskSAT and run your first example by following [Getting Started](getting-started.md) first. 

## An Example

Let's start with a complete TaskSAT specification and then understand each part. This example models a Mars rover conducting a science mission. The complete file is available at [tests/tasknet_files/examples/rover2.tn](../tests/tasknet_files/examples/rover2.tn).

```
tasknet MyRobot {
  end = 400;

  timelines {
    battery : rate [10.0, 100.0] bounds [0.0, 100.0] = 60.0;
    temperature : rate [5.0, 40.0] bounds [0.0, 100.0] = 10.0;
    location : state(home, target) = home;
    arm : atomic = false;
    data : cumulative [0.0, 50.0] bounds [0.0, 100.0] = 0.0;
  }

  taskdef charge_def {
    pre {
      battery in [0.0, 60.0];
    }

    impacts {
      maint {
        battery +~ 2.0;  # Charge at 2 units per time
      }
    }
  }  

  taskdef drive_def {
    pre {
      battery in [60.0, 100.0];  # Need enough power
      temperature in [10.0, 40.0];  # Safe temperature
    }

    impacts {
      maint {
        battery +~ -1.5;  # Drain 5 unit per time
      }
      post {
        location = target;
      }
    }
  }

  optional task charge : charge_def {
    duration_range [60,70];
  }

  optional task heating {
    duration_range [10, 10];

    impacts {
      maint {
        battery +~ -0.5;  # Small power drain
        temperature +~ 2;  # Increase temperature
      }
    }
  }

  task drive: drive_def {
    start_range [100, 120];
    end_range [130, 160];
    duration_range [30,40];

    # after charge; # this will yield unsat
  }
  
  task collect {
    duration_range  [20, 30];

    pre {
      location = target;
      battery in [60.0, 100.0];
      arm = false;
    }

    impacts {
      pre {
        arm = true; 
      }
      maint {
        battery +~ -0.5;   # Use power for collection
        temperature +~ -0.2;
      }
      post {
        data += 40.0;      # Collect 30 units of data
        arm = false;      # Retract arm
      }
    }
  }

  constraints {
     prop not_charge_drive: always not (active(charge) and active(drive));
     prop not_charge_collect: always not (active(charge) and active(collect));
     prop temperature10: always temperature >= 10;
  }

  properties {
   prop target_reached: eventually (location = target and data >= 30);
   prop drive_charge: always (active(drive) -> eventually active(charge));
   prop temperature: always temperature >= 10;
  }
}
```


=================


The ordering of charge and drive
--------------------------------

One would expect charging to happen first, but it has to come after the drive task, and the scheduler determines that. The reason is as follows.

--- Charge first: ---

Suppose we start by charging.

Charge lasts 60-70 time units, adding 2.0 per time unit. If it starts right away at 60, we reach 100% after 20 time units (note that means that at least 40 time units have no charging effect). 

When the drive task then starts, it will last 30-40 time units charging 1.5 per time unit, brining the battery to 55 to 40. The collection task pre condition requires the battery to be at least 60, so this can now not start.

--- drive first: ---

Suppose instead we start by driving. 

The battery is initially 60 which satisfies the pre-condition of driving. Driving lasts 30-40 time units, 
charging 1.5 per time unit, brining the battery to 15 to 0. 

At this point charging can start, lasts 60-70 time units, adding 2.0 per time unit, giving a resulting charge of 100. This is then enough for the collection task to execute.


--- proving this: ---

If we add an 

  after charge

To drive we will see that there is no solution.


Overlapping charge and drive
-----------------------------

However, when we look at the schedule we see that  charge overlaps with drive as well as collect. 
We do not want this. We can avoid this by adding the constraints:

     prop not_charge_drive: always not (active(charge) and active(drive));
     prop not_charge_collect: always not (active(charge) and active(collect));

The properties
--------------

We can state some properties we want to hold.

   prop target_reached: eventually (location = target and data >= 30);
   prop drive_charge: always (active(drive) -> eventually active(charge));
   prop temperature: always temperature >= 10;

The first two are satisfied but the third is not. Temperature dips down under 10 during collection, which decrements the temperature with 0.2 per time unit, from the initial 10.

This is because nothing in the model solar restricts the temperature from going below 10. For example, the temperature timeline is defined as:

  temperature : rate [5.0, 40.0] bounds [0.0, 100.0] = 10.0;

Only enforcing a lower limit of 5. We could of course now change this to:

  temperature : rate [10.0, 40.0] bounds [0.0, 100.0] = 10.0;

Which will trigger the optional heating task to become active.

However, we can also do it with an additional constraint:

  prop temperature10: always temperature >= 10;





```tasknet
tasknet RoverMission {
  end = 200;

  timelines {
    battery : rate [-10.0, 5.0] bounds [0.0, 100.0] = 80.0;
    data : cumulative [0.0, 10.0] bounds [0.0, 200.0] = 0.0;
    location : state(base, site_a, site_b) = base;
    arm : state(stowed, deployed) = stowed;
    wheels : atomic = false;
  }

  task drive_to_site {
    id 1;
    duration 30;

    pre {
      location = base;
      battery in [40.0, 100.0];
      arm = stowed;
    }

    impacts {
      pre {
        location = site_a;
        wheels = true;
      }
      maint {
        battery +~ -1.5;  // Drain 1.5 units/time while driving
      }
      post {
        wheels = false;
      }
    }
  }

  task collect_sample {
    id 2;
    duration 40;
    after drive_to_site;

    pre {
      location = site_a;
      battery in [30.0, 100.0];
      arm = stowed;
      wheels = false;
    }

    inv {
      arm = deployed;
    }

    impacts {
      pre {
        arm = deployed;
      }
      maint {
        battery +~ -0.8;   // Use power for sampling
        data +~ 2.0;       // Collect 2 units/time
      }
      post {
        arm = stowed;
      }
    }
  }

  task transmit_data {
    id 3;
    duration 30;
    after collect_sample;

    pre {
      location = site_a;
      data in [40.0, 200.0];  // Need data to transmit
      battery in [35.0, 100.0];
    }

    impacts {
      maint {
        battery +~ -1.0;   // Use power for transmission
        data +~ -2.5;      // Transmit 2.5 units/time
      }
    }
  }

  constraints {
    prop battery_safe: always (battery >= 20.0);
    prop arm_while_stopped: always ((wheels = true) -> (arm = stowed));
    prop must_collect: eventually active(collect_sample);
    prop must_transmit: eventually active(transmit_data);
  }
}
```

**What this specification does:**

1. **Defines Resources**: Battery (drains/charges), data storage (accumulates), location (discrete states), arm position, wheel status
2. **drive_to_site**: Rover drives from base to site_a, consuming battery
3. **collect_sample**: Deploys arm, collects scientific data while using power
4. **transmit_data**: Sends collected data back to Earth, consuming remaining data and power
5. **Safety Properties**: Ensures battery stays safe, arm is stowed while driving, critical tasks complete

When you run this:
```bash
python src/smt/tasknet_verifier.py rover_mission.tn --mode satisfy
```

The solver finds a schedule that satisfies all constraints, showing when each task executes and how resources change over time.

Now let's break down each concept in detail.

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

## Quick Help

**Problem: UNSAT (No solution)**
- Check if constraints are too strict
- Increase time horizon (`end = ...`)
- Use `--mode satisfy` for debugging

**Problem: Timeout**
- Try `--mode satisfy` instead of optimize
- Simplify the problem
- See [performance.md](performance.md) for guidelines

**Problem: Unexpected schedule**
- Verify impact timing (pre/maint/post)
- Check initial timeline values
- Review task dependencies