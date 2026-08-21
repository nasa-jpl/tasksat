---
sidebar_position: 2
sidebar_label: "Tutorial"
slug: /tutorial
---

# TaskSAT Tutorial

This tutorial provides an in-depth walkthrough of TaskSAT concepts, patterns, and best practices.

**Prerequisites**: Install TaskSAT and run your first example by following [Installation](installation.md) first. 

## An Example

### The Complete Tasknet Model

Let's start with a complete TaskSAT specification and then understand each part. This example models a Mars rover conducting a science mission. The complete file is available at [tests/tasknet_files/examples/rover2.tn](https://github.com/nasa-jpl/tasksat/blob/main/tests/tasknet_files/examples/rover2.tn).

```
tasknet Rover2 {
  end = 400;

  timelines {
    arm : atomic = 0;
    location : state(home, target) = home;
    data : cumulative [0.0, 50.0] bounds [0.0, 100.0] = 0.0;
    battery : rate [10.0, 100.0] bounds [0.0, 100.0] = 60.0;
    temperature : rate [5.0, 40.0] bounds [0.0, 100.0] = 10.0;
  }

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

  taskdef drive_def {
    pre {
      battery in [60.0, 100.0]; 
      temperature in [10.0, 40.0];  
    }

    impacts {
      maint {
        battery -~ 1.5;  
      }
      post {
        location = target;
      }
    }
  }

  optional task charge : charge_def {
    duration_range [60,70];
  }

  task drive: drive_def {
    start_range [100, 120];
    end_range [130, 160];
    duration_range [30,40];

    # after charge; # this will yield unsat
  }

  optional task heating {
    duration_range [10, 10];

    impacts {
      maint {
        battery -~ 0.5; 
        temperature +~ 2; 
      }
    }
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
        battery -~ 0.5;   
        temperature -~ 0.2;
      }
      post {
        data += 40.0;  
        arm = false;  
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
   // Note: 'implies' keyword can also be used instead of '->'
   prop temperature: always temperature >= 10;
  }
}
```

The tasknet defines five time lines (global variables) and four tasks that operate on these:
a battery charging task, a driving task driving from home to a target, a heating task heating up a movable arm, and a sample collection task. The objective is to drive to the target and collect a sample.

### Stepwise Explanation

We will now go through the individual parts of the tasknet.

#### Time Horizon

The first definition defines the time horizon of schedules, in terms of number of time units.
We request a schedule spanning at most 400 time units.

```
  end = 400;
```

#### Timelines

Next we define the timelines. Timelines are global variables that tasks can read and update.

```
  timelines {
    arm : atomic = 0;
    location : state(home, target) = home;
    data : cumulative [0.0, 50.0] bounds [0.0, 100.0] = 0.0;
    battery : rate [10.0, 100.0] bounds [0.0, 100.0] = 60.0;
    temperature : rate [5.0, 40.0] bounds [0.0, 100.0] = 10.0;
  }
```

There are different kinds of timelines, four of which are shown here: atomic, state, cumulative, and rate.

- The `arm` timeline is atomic, which means an integer [0,1] timeline for mutual exclusion patterns (0 = unclaimed, 1 = claimed). Only cumulative impacts (`+= 1` to claim, `-= 1` to release) are allowed.
- The `location` timeline is a state, which means an enumerated type, here with two possible states `home` and `target`.
- The `data` timeline is cumulative, which means a floating point value which always will be within the bounds 0 to 100, but which we want to stay within the range 0 to 50. This means that a schedule where it goes outside the interval [0,50] is not acceptable. The bounds interval ensures that it always clamped to be in this interval. A task can either assign values to this timeline or add values to/subtract values from this timeline.
- The `battery` and `temperature` timelines are rate timelines, with the same interpretations of the intervals as cumulative timelines. In addition to assignment and addition/subtraction, rate timelines can also be given a rate with which they change per time unit, as we shall see.

#### The charge task Definition

The charge task is defined below. It has a pre-condition, which must be true before it can execute, in this case that the battery is in the interval 0 to 60. Such constraints are expressed as interval memberships, or equalities as we shall see later.

The impacts section specifies how the task updates the timelines. In this case the battery charge is increased with 2.0 for each time unit the task executes (a rate update is indicated by `+~`). So if e.g the battery charge is 30, and it executes 6 time units the battery charge will be increased with 6*2=12, becoming 42. The impact is specified as a maintenance update: `maint`, which means that the rate increase is only active during the task execution. It is also possible to indicate pre and post rate increases, which will be explained later.

```
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

Note that this is a definition of a task. Such definitions must be instantiated in order to be used in a schedules as we shall see below.

#### The drive Task Definition

The `drive` task defines a pre-condition on the `battery` as well as the `temperature`.
It impacts the `battery` by decreasing the charge with 1.5 per time unit. When terminating,
indicated by a post-impact, it assigns the value `target` to the `location` timeline.

```
taskdef drive_def {
    pre {
      battery in [60.0, 100.0]; 
      temperature in [10.0, 40.0]; 
    }

    impacts {
      maint {
        battery -~ 1.5;  
      }
      post {
        location = target;
      }
    }
  }
```

#### Instantiating the charge and drive task definitions

Above we provided definitions of the `charge` and `drive` tasks. These are just definitions, and have to be instantiated before being scheduled. Not unsimilar to class definitions in an object-oriented programming language have to be instantiated. Below we create an optional instance of the `charge` task, meaning that it can be schedule if needed but it if not needed it can be left out of the schedule, and an instance of the `drive` task. In each case we indicate the definition it is an instance of after the colon `:`. Such a task instance inherits the constraints and impacts from the definition. It can furthermore add new constraints and impacts.
For example the `charge` task instance indicates that its execution will take between 60 and 70 time units.
The `drive` task instance also indicates a task execution duration range. In addition it specifies an absolute time range for when the task must start respectively end.

```
  optional task charge : charge_def {
    duration_range [60,70];
  }

  task drive: drive_def {
    start_range [100, 120];
    end_range [130, 160];
    duration_range [30,40];
  }
```

#### The heating Task Instance

The `heating` task instance shows that one can define a task instance without first providing a definition.
This task is also optional

```
  optional task heating {
    duration_range [10, 10];

    impacts {
      maint {
        battery -~ 0.5;  
        temperature +~ 2;  
      }
    }
  }
```
  
#### The collect Task Instance

The `collect` task shows some new concepts. It has a pre-condition containing a couple of equalities: the `location` be at the `target` and the arm must not aleady be deployed. We also now see a pre-impact, executed at the beginning of the task exection, namely that the `arm` is deployed (becoming true). At the end of the execution, the `data` timelines is augmented with 40.

**Important note on impact timing:** Pre-impacts take effect *during* task execution, not before the pre-condition is checked. In this example, the pre-condition checks `arm = false` before the pre-impact sets `arm = true`. This allows the pre-condition to verify the "input state" (arm not deployed) before the task modifies it. The task then executes with `arm = true` (the modified state). Similarly, post-impacts take effect *after* the post-condition is checked, so the next task sees the modified state.

```  
  task collect {
    duration_range  [20, 30];

    pre {
      location = target;
      battery in [60.0, 100.0];
      arm = false;           // Checks BEFORE pre-impact modifies it
    }

    impacts {
      pre {
        arm = true;          // Takes effect during execution
      }
      maint {
        battery -~ 0.5;  
        temperature -~ 0.2;
      }
      post {
        data += 40.0;  
        arm = false;         // Takes effect after task completes
      }
    }
  }
```

#### Finding a Schedule for the So Far Shown Model

If we comment out the constaints and properties at the bottom of the tasknet, and apply the tasknet explorer on it as follows:

```bash
python src/smt/tasknet_verifier.py tests/tasknet_files/examples/rover2.tn
```

We get an output looking like this:

```
*** NEW SCHEDULE***

Schedule for TaskNet `Rover2`:
  charge        : start =   46, end =  106
  drive         : start =  100, end =  130
  collect       : start =  173, end =  198
  heating       : [OPTIONAL - NOT INCLUDED]

Zone boundaries (z_i):
  z_ 0 = 0
  z_ 1 = 46
  z_ 2 = 100
  z_ 3 = 105
  z_ 4 = 106
  z_ 5 = 114
  z_ 6 = 130
  z_ 7 = 173
  z_ 8 = 198
  z_ 9 = 400

Values in each zone:

  -- zone 0: (0, 46] --
    active tasks : (none)
    arm            = False
    location       = home
    data           = 0
    battery        = 60 -> 60
    temperature    = 10 -> 10

  -- zone 1: (46, 100] --
    active tasks : charge
    arm            = False
    location       = home
    data           = 0
    battery        = 60 -> 100
    temperature    = 10 -> 10

  -- zone 2: (100, 105] --
    active tasks : drive, charge
    arm            = False
    location       = home
    data           = 0
    battery        = 100 -> 100
    temperature    = 10 -> 10

  -- zone 3: (105, 106] --
    active tasks : drive, charge
    arm            = False
    location       = home
    data           = 0
    battery        = 100 -> 100
    temperature    = 10 -> 10

  -- zone 4: (106, 114] --
    active tasks : drive
    arm            = False
    location       = home
    data           = 0
    battery        = 100 -> 88
    temperature    = 10 -> 10

  -- zone 5: (114, 130] --
    active tasks : drive
    arm            = False
    location       = home
    data           = 0
    battery        = 88 -> 64
    temperature    = 10 -> 10

  -- zone 6: (130, 173] --
    active tasks : (none)
    arm            = False
    location       = target
    data           = 0
    battery        = 64 -> 64
    temperature    = 10 -> 10

  -- zone 7: (173, 198] --
    active tasks : collect
    arm            = True
    location       = target
    data           = 0
    battery        = 64 -> 51.5
    temperature    = 10 -> 5

  -- zone 8: (198, 400] --
    active tasks : (none)
    arm            = False
    location       = target
    data           = 40
    battery        = 51.5 -> 51.5
    temperature    = 5 -> 5


No temporal properties attached to this TaskNet.
```

It shows the schedule: for each task it shows the start time and the end time. It also shows which optional tasks that have not been schedule since it was not necessary, in this case the `heating` task was not scheduled.

The zone boundaries are the time points that TaskSAT has calculated with to generate the schedule.
Note that TaskSAT does not examine every single time step. Instead, it divides the timeline into zones to reduce the state space. This part is not important for the user to examine. 

Then follows the values of timelines at the end of each zone. For example:

- zone 0 - time 0-46: no tasks are active.
- zone 1 - time 46-100: the `charge` task is active, and changes the `battery` from 60 to 100.
- zone 2 - time 100-105: both the `drive` task and the `charge` task are active, where the `battery` compensates for the use by the `drive` task.
- etc.

#### The ordering of charge and drive

As can be seen, the `drive` and `charge` tasks overlap. If we want to avoid this, we can add a constraint to the tasknet:

```
  constraints {
     prop not_charge_drive: always not (active(charge) and active(drive));
  }
```

That yields the following schedule:

```
Schedule for TaskNet `Rover2`:
  drive         : start =  120, end =  150
  charge        : start =  318, end =  378
  collect       : start =  379, end =  399
  heating       : [OPTIONAL - NOT INCLUDED]
```

One would expect charging to happen first, but it has to come after the drive task.
The reason is as follows. Suppose we start by charging. `charge` lasts 60-70 time units, adding 2.0 per time unit. If it starts right away at 60, we reach 100% after 20 time units. That means that at least 40 time units have no charging effect and are wasted.  Suppose instead we start by driving. 
The battery is initially 60 which satisfies the pre-condition of driving. Driving lasts 30-40 time units, 
charging 1.5 per time unit, brining the battery to 15 to 0. 
At this point charging can start, lasts 60-70 time units, adding 2.0 per time unit, giving a resulting charge of 100. This is then enough for the collection task to execute.

We can show that `charge` cannot start before `drive` by adding an after-constraint to the `drive` task:

```
  task drive: drive_def {
    start_range [100, 120];
    end_range [130, 160];
    duration_range [30,40];

    after charge; # this will yield unsat
  }
```

This the results in no solution found:

```
*** NEW SCHEDULE***

TaskNet constraints (schedule + zone trace): unsat
UNSAT: No valid schedule found!
```

#### Let us Add Some Properties

The TaskSAT language allows us to add temporal logic formulas to be proven about executions of schedules generated by the tasknet. We can for example state the following temporal properties that we would like to hold for all generated schedules:

```
  properties {
    prop target_reached: eventually (location = target and data >= 30);
    prop drive_charge: always (active(drive) -> eventually active(charge));
    prop temperature: always temperature >= 10;
  }
```

The result is a schedule but now also a results of verifying the properties:

```
Checking 3 temporal properties:
PROPERTY 'target_reached' HOLDS
PROPERTY 'drive_charge' HOLDS
PROPERTY 'temperature' VIOLATED!
```

The first two properties hold but the last one concerning the temperature is violated. We also get an error trace:

```
Counterexample:

Schedule for TaskNet `Rover2`:
  drive         : start =  120, end =  153
  collect       : start =  377, end =  398
  charge        : start =  316, end =  376
  heating       : [OPTIONAL - NOT INCLUDED]

Zone boundaries (z_i):
  z_ 0 = 0
  z_ 1 = 120
  z_ 2 = 153
  z_ 3 = 315
  z_ 4 = 316
  z_ 5 = 376
  z_ 6 = 377
  z_ 7 = 398
  z_ 8 = 399
  z_ 9 = 400

Values in each zone:

  -- zone 0: (0, 120] --
    active tasks : (none)
    arm            = False
    location       = home
    data           = 0
    battery        = 60 -> 60
    temperature    = 10 -> 10
    __drive_active = False
    __charge_active = False

  -- zone 1: (120, 153] --
    active tasks : drive
    arm            = False
    location       = home
    data           = 0
    battery        = 60 -> 10.5
    temperature    = 10 -> 10
    __drive_active = True
    __charge_active = False

  -- zone 2: (153, 315] --
    active tasks : (none)
    arm            = False
    location       = target
    data           = 0
    battery        = 10.5 -> 10.5
    temperature    = 10 -> 10
    __drive_active = False
    __charge_active = False

  -- zone 3: (315, 316] --
    active tasks : (none)
    arm            = False
    location       = target
    data           = 0
    battery        = 10.5 -> 10.5
    temperature    = 10 -> 10
    __drive_active = False
    __charge_active = False

  -- zone 4: (316, 376] --
    active tasks : charge
    arm            = False
    location       = target
    data           = 0
    battery        = 10.5 -> 100
    temperature    = 10 -> 10
    __drive_active = False
    __charge_active = True

  -- zone 5: (376, 377] --
    active tasks : (none)
    arm            = False
    location       = target
    data           = 0
    battery        = 100 -> 100
    temperature    = 10 -> 10
    __drive_active = False
    __charge_active = False

  -- zone 6: (377, 398] --
    active tasks : collect
    arm            = True
    location       = target
    data           = 0
    battery        = 100 -> 89.5
    temperature    = 10 -> 5.8
    __drive_active = False
    __charge_active = False

  -- zone 7: (398, 399] --
    active tasks : (none)
    arm            = False
    location       = target
    data           = 40
    battery        = 89.5 -> 89.5
    temperature    = 5.8 -> 5.8
    __drive_active = False
    __charge_active = False

  -- zone 8: (399, 400] --
    active tasks : (none)
    arm            = False
    location       = target
    data           = 40
    battery        = 89.5 -> 89.5
    temperature    = 5.8 -> 5.8
    __drive_active = False
    __charge_active = False
```

We see in zone 6 that during the `collect` task the temperature dips down under 10 to 5.8.
So how do we fix this? We need to force the optional `heating` task to take place.
We could do that by changing the permitted range for the `temperature` timeline to:

```
  temperature : rate [10.0, 40.0] bounds [0.0, 100.0] = 10.0;
```

However, we can also do it with an additional constraint:

```
  constraints {
    prop not_charge_drive: always not (active(charge) and active(drive));
    prop temperature10: always temperature >= 10;
  }
```

Now all the properties are satisfied but we get a scedule

```
Schedule for TaskNet `Rover2`:
  drive         : start =  120, end =  150
  heating       : start =  151, end =  161
  charge        : start =  163, end =  223
  collect       : start =  209, end =  238
```

where `charge` overlaps with `collect`. To avoid this we add an additional constraint:

```
  constraints {
    prop not_charge_drive: always not (active(charge) and active(drive));
    prop not_charge_collect: always not (active(charge) and active(collect));
    prop temperature10: always temperature >= 10;
  }
```

Now all the properties hold and we get a schedule where there is no overlap between
`charge`, `drive`, and `collect`:

```
Schedule for TaskNet `Rover2`:
  drive         : start =  118, end =  148
  heating       : start =  137, end =  147
  charge        : start =  149, end =  209
  collect       : start =  210, end =  233
```

However, `heating` overlaps with `drive`. If we do not want that we must add a further constraint. 

#### Initial Values

In the example above, each timeline was given a specific initial value. It is also possible to be loose wrt. initial values, and instead either leave them out, in which case they are unconstrained, or provide constraints on them in a specific initialization block.
For example, the `battery` timelines could be defined as follows without an initial value:

```
 timelines {
    ...
    battery : rate [10.0, 100.0] bounds [0.0, 100.0];
    ...
  }
```

and then a range of values could be specified in an initial block:


```
  initial {
    battery in [0,59];
  }
```

In this case we attempt to see if there is a schedule if the battery is below 60. In fact, there isn't.

#### Final Values

Where the `initial` block *constrains* the state at the start of the schedule, the
`final` block *checks* the state at the end. It has the same body syntax, but a
different meaning: it is a **property**, not a constraint. It asks whether **every**
valid schedule ends in a state satisfying the given conditions; if some schedule
does not, that schedule is reported as a counterexample (just like a violated
entry in the `properties` block).

The end state is taken **right after the last scheduled task finishes** (the
makespan), which may be earlier than the `end` horizon. For example, to require
that every schedule leaves the battery at least 60% charged and the rover back at
home:

```
  final {
    battery in [60.0, 100.0];
    location = home;
  }
```

If you want the schedule to end the way it started — plus some extra conditions —
you can write `final within initial { ... }`, which means "the initial conditions
and these":

```
  final within initial {
    battery in [60.0, 100.0];
  }
```

The block is optional: `final within initial;` alone means every schedule must
end in a state satisfying exactly the initial conditions.

## Using Parameters

Parameters allow you to define reusable constants and avoid magic numbers in your TaskSAT specifications. This makes your models more readable, maintainable, and easier to tune.

### Why Use Parameters?

Consider this specification without parameters:

```tasknet
task drive {
  duration 600;
  impacts { maint { battery +~ -0.3; } }
}

task charge {
  duration 300;
  impacts { maint { battery +~ 0.5; } }
}

constraints {
  always (battery >= 20.0);
}
```

The values `600`, `300`, `-0.3`, `0.5`, and `20.0` are "magic numbers" - their meaning isn't clear, and if you want to change them, you have to find every occurrence.

### Parameterized Version

Here's the same specification using parameters:

```tasknet
tasknet RoverWithParams {
  end = 2000;
  
  # Global parameters make the model more readable
  param DRIVE_DURATION = 600;
  param CHARGE_DURATION = 300;
  param DRIVE_RATE = -0.3;
  param CHARGE_RATE = 0.5;
  param SAFE_BATTERY = 20.0;
  
  timelines {
    battery : rate [0.0, 100.0] = 50.0;
  }
  
  task drive {
    duration DRIVE_DURATION;
    impacts { maint { battery +~ DRIVE_RATE; } }
  }
  
  task charge {
    duration CHARGE_DURATION;
    impacts { maint { battery +~ CHARGE_RATE; } }
  }
  
  constraints {
    always (battery >= SAFE_BATTERY);
  }
}
```

Now the model is self-documenting, and you can easily experiment with different values by changing the parameter declarations.

### Parameter Scopes

Parameters can be declared at three levels:

**1. TaskNet-level (Global):**
```tasknet
tasknet Example {
  param GLOBAL_DURATION = 10;
  
  task t1 { duration GLOBAL_DURATION; }
  task t2 { duration GLOBAL_DURATION; }
}
```

**2. TaskDef-level (Template defaults):**
```tasknet
taskdef science_def {
  param {
    DURATION = 30;
    DATA_RATE = 2.0;
  }
  
  duration DURATION;
  impacts { maint { data += DATA_RATE; } }
}

task science1 : science_def {}  // Uses defaults
```

**3. Task-level (Instance overrides):**
```tasknet
task science2 : science_def {
  param {
    DURATION = 45;  // Override: longer duration
    DATA_RATE = 3.0;  // Override: faster data collection
  }
}
```

### Resolution Priority

When TaskSAT resolves a parameter reference, it uses the following priority (highest first):

1. **Task-level** parameter (if defined in the task body)
2. **TaskDef-level** parameter (if the task is an instance of a taskdef)
3. **TaskNet-level** parameter (global scope)

This allows you to:
- Set sensible defaults at the taskdef level
- Override specific instances as needed
- Share common constants globally

### Complete Example with All Scopes

```tasknet
tasknet ParamExample {
  end = 500;
  
  # Global parameters
  param STANDARD_DURATION = 30;
  param HIGH_PRIORITY = 10;
  
  timelines {
    data : cumulative [0.0, 100.0] = 0.0;
  }
  
  # TaskDef with parameter defaults
  taskdef science_def {
    param {
      DURATION = STANDARD_DURATION;  // Reference global
      RATE = 1.0;
    }
    
    duration DURATION;
    priority HIGH_PRIORITY;
    
    impacts {
      maint { data += RATE; }
    }
  }
  
  # Instance 1: Uses all defaults
  task science1 : science_def {}
  
  # Instance 2: Override duration only
  task science2 : science_def {
    param { DURATION = 45; }
  }
  
  # Instance 3: Override both parameters
  task science3 : science_def {
    param {
      DURATION = 60;
      RATE = 2.0;
    }
  }
}
```

When this model runs:
- `science1` has `DURATION=30` and `RATE=1.0` (taskdef defaults)
- `science2` has `DURATION=45` and `RATE=1.0` (duration overridden)
- `science3` has `DURATION=60` and `RATE=2.0` (both overridden)

### Where Parameters Can Be Used

Parameters can be referenced in:
- Task durations: `duration PARAM;`
- Task start/end times: `start PARAM;`
- Time ranges: `start_range [MIN_PARAM, MAX_PARAM];`
- Timeline declarations: `battery : rate [0.0, CAPACITY] = INITIAL;`
- Impact values: `battery += CHARGE_AMOUNT;`
- Constraint formulas: `battery >= SAFE_LEVEL`
- Priority values: `priority PRIORITY_PARAM;`

### Best Practices

1. **Use UPPER_CASE names** for parameters to distinguish them from tasks and timelines
2. **Group related parameters** at the tasknet level for easy tuning
3. **Use descriptive names** that explain what the value represents
4. **Set taskdef defaults** for reusable task templates
5. **Override sparingly** - only when an instance needs different behavior

### Example: Tuning a Model

Parameters make it easy to experiment with different scenarios:

```tasknet
# Conservative scenario
param SAFE_BATTERY = 30.0;
param DRIVE_DURATION = 400;  # Slower driving

# Aggressive scenario
# param SAFE_BATTERY = 15.0;
# param DRIVE_DURATION = 600;  # Faster driving
```

Simply comment/uncomment parameter declarations to switch between configurations without touching the rest of your model.

## Auto-Instantiation: Reducing Boilerplate

TaskSAT can automatically create task instances when you use **type-level dependencies** - referencing `taskdef` names in `after` or `containedin` constraints. This powerful feature dramatically reduces boilerplate in your specifications.

### The Problem: Repetitive Task Definitions

Imagine a rover mission where every drive operation requires a pre-drive safety check:

```tasknet
// Manual approach - lots of repetition!
tasknet ManualRover {
  taskdef predrive { duration 300; }
  taskdef drive { duration_range [5000, 7000]; }
  
  // For 2 drives, need to manually create 2 predrives:
  task predrive1 : predrive {}
  task predrive2 : predrive {}
  
  task drive1 : drive { after predrive1; }
  task drive2 : drive { after predrive2; }
}
```

With 10 drives, you'd need 10 predrive definitions. With 100 drives... you get the idea.

### The Solution: Type-Level Dependencies

Instead of referencing specific task instances, reference the **taskdef** directly:

```tasknet
tasknet AutoRover {
  taskdef predrive { duration 300; }
  
  taskdef drive {
    after predrive;  // Type-level dependency!
    duration_range [5000, 7000];
  }
  
  // Just define the drives:
  task drive1 : drive { start_range [5000, 10000]; }
  task drive2 : drive { start_range [15000, 20000]; }
  task drive3 : drive { start_range [25000, 30000]; }
}
```

TaskSAT automatically creates:
- `predrive_auto_0` (for drive1)
- `predrive_auto_1` (for drive2)  
- `predrive_auto_2` (for drive3)

**Result**: 3 task definitions instead of 7!

### How Auto-Instantiation Works

When you run the verifier, you'll see:

```
*** Auto-instantiated 3 task(s) from taskdefs:
    predrive_auto_0 (from taskdef predrive)
    predrive_auto_1 (from taskdef predrive)
    predrive_auto_2 (from taskdef predrive)

📄 Transformed tasknet written to: .tasksat/transformed/AutoRover_transformed.tn
```

**Key principle**: One instance per dependent task (MEXEC semantics)

Each drive gets its own predrive instance because:
1. **Independence**: Each drive might need its predrive at a different time
2. **Flexibility**: The solver can schedule predrives optimally for each drive
3. **Parallelism**: Multiple predrives can potentially overlap if safe

### Real-World Example: Thermal Management

Consider a communication system where each downlink requires thermal conditioning:

```tasknet
tasknet SatelliteDownlink {
  end = 10000;
  
  timelines {
    temperature : rate [0.0, 60.0] = 20.0;
    battery : rate [0.0, 100.0] = 80.0;
  }
  
  taskdef preheat {
    duration_range [50, 100];
    impacts { maint { temperature +~ 0.5; battery +~ -0.2; } }
  }
  
  taskdef maintainheat {
    duration_range [110, 120];
    after preheat;  // Maintain heat after preheating
    impacts { maint { temperature +~ -0.05; battery +~ -0.05; } }
  }
  
  taskdef downlink {
    duration_range [50, 100];
    after preheat;
    containedin maintainheat;  // Must stay warm during downlink
    inv { temperature in [25.0, 50.0]; }
    impacts { maint { battery +~ -0.3; } }
  }
  
  // Just specify the downlinks - thermal management is automatic!
  task downlink_0 : downlink { start_range [100, 300]; }
  task downlink_1 : downlink { start_range [500, 700]; }
  task downlink_2 : downlink { start_range [1200, 1500]; }
}
```

TaskSAT automatically creates **6 thermal tasks**:
- `preheat_auto_0`, `maintainheat_auto_0` (for downlink_0)
- `preheat_auto_1`, `maintainheat_auto_1` (for downlink_1)
- `preheat_auto_2`, `maintainheat_auto_2` (for downlink_2)

You defined 3 tasks, got 9 tasks total (3 downlinks + 6 thermal), reducing specification from 9 explicit tasks to 3.

### Viewing What Was Created

Use `--transform-only` to see exactly what TaskSAT created without running verification:

```bash
python src/smt/tasknet_verifier.py AutoRover.tn --transform-only
cat .tasksat/transformed/AutoRover_transformed.tn
```

The transformed file shows all auto-instances as explicit task declarations. You can:
- Verify the correct number of instances were created
- See what properties each instance inherited
- Edit the transformed file to add scheduling hints (e.g., priority, start_range)
- Use the transformed file as your source if you want full manual control

### When Auto-Instantiation is Skipped

If you create **any** manual instance of a taskdef, auto-instantiation is skipped for that taskdef:

```tasknet
taskdef predrive { duration 300; }
taskdef drive { after predrive; }

task predrive_manual : predrive {}  // Manual instance exists!

task drive1 : drive {}
task drive2 : drive {}

# Result: NO auto-instantiation
# Both drive1 and drive2 reference the single predrive_manual
# Solver must ensure: predrive_manual.end <= drive1.start AND
#                     predrive_manual.end <= drive2.start
```

This assumes you want full manual control over that taskdef's instances.

### Best Practices

1. **Use type-level dependencies for repeated patterns**: Pre-checks, thermal conditioning, post-operations
2. **Let TaskSAT handle instantiation** unless you need fine-grained control over specific instances
3. **Check the transformed file** when debugging to see what was created
4. **Combine with parameters** for maximum reusability:

```tasknet
param PREDRIVE_DURATION = 300;

taskdef predrive {
  duration PREDRIVE_DURATION;  // Easy to tune globally
}

taskdef drive {
  after predrive;  // Auto-instantiation handles the rest
  ...
}
```

## Sessions: Grouping Subtasks

Auto-instantiation reduces boilerplate for *single* repeated predecessors. When
you have a repeating **group** of subtasks — a preheat, then a contained drive,
say — you can package them as a **session**: a `taskdef` whose body declares
nested `task` children.

```tasknet
taskdef PreHeat { duration_range [30, 40]; }
taskdef Drive   { duration_range [60, 80]; }

taskdef DriveSession {
  task preheat : PreHeat;
  task drive   : Drive { after preheat; }   // refer to siblings by bare name
}

// Instantiate the whole group with one declaration each:
task drive1 : DriveSession;
task drive2 : DriveSession { after drive1; }
```

A session is **pure sugar**: before the solver runs, each instance is flattened
into ordinary qualified instances named `{instance}__{child}`. The spec above
becomes:

```tasknet
task drive1__preheat : PreHeat {}
task drive1__drive   : Drive { after drive1__preheat; }

task drive2__preheat : PreHeat { after drive1__preheat, drive1__drive; }
task drive2__drive   : Drive { after drive2__preheat, drive1__preheat, drive1__drive; }
```

Two rules govern the rewrite:

1. **Sibling references are qualified**: `drive`'s `after preheat` becomes
   `after drive1__preheat` — siblings stay wired within their own instance.
2. **Session-to-session `after` fans out (conservative)**: `drive2 after drive1`
   makes *every* `drive2` child start after *all* `drive1` children end — i.e.
   "after the whole predecessor session."

Because it is sugar, sessions add no solver cost and no new semantics. Inspect
the flattened network with `--transform-only`.

## Time-Constrained Dependencies

TaskSAT supports optional time ranges on `after` and `containedin` dependencies to express temporal gaps and offsets between tasks.

### After Dependencies with Time Gaps

By default, `after` allows immediate succession. Add a time range to enforce a gap:

```tasknet
tasknet RoverWithGaps {
  end = 30000;
  
  timelines {
    battery : rate [0.0, 100.0] = 50.0;
  }
  
  taskdef predrive { duration_range [300, 300]; }
  taskdef drive { 
    after predrive [600, 1200];  // Must start 600-1200 time units after predrive
    duration_range [6000, 6000]; 
  }
  
  task drive1 : drive {}
}
```

**Syntax variants:**
- `after A [min, max];` - Full range: start between `A.end + min` and `A.end + max`
- `after A num;` - Shorthand for `[0, num]`: start within `num` time units after A ends
- `after A;` - No gap: start anytime at or after A ends (default behavior)

**Examples:**
```tasknet
after warmup [100, 200];     // Start 100-200 time units after warmup ends
after charge 500;            // Start within 500 time units after charge ends  
after calibrate;             // Start anytime after calibrate ends (default)
after A [50, 100], B 200;    // Multiple dependencies with different gaps
```

### Containedin Dependencies with Offsets

By default, `containedin` requires exact containment. Add offsets to specify margins from the parent's boundaries:

```tasknet
tasknet ObservationWindow {
  end = 30000;
  
  timelines {
    battery : rate [0.0, 100.0] = 50.0;
  }
  
  taskdef warmup { duration_range [1000, 1000]; }
  taskdef science {
    containedin warmup [100, 200] [100, 200];  
    // Start 100-200 after warmup starts
    // End 100-200 before warmup ends
    duration_range [500, 500];
  }
  
  task warmup1 : warmup {}
  task science1 : science {}
}
```

If `warmup1` runs from 1000 to 2000:
- `science1.start ∈ [1100, 1200]` (warmup start + [100, 200])
- `science1.end ∈ [1800, 1900]` (warmup end - [200, 100])

**Syntax variants:**
- `containedin A [s_min, s_max] [e_min, e_max];` - Full ranges for start and end offsets
- `containedin A num1 num2;` - Shorthand for `[0, num1] [0, num2]`
- `containedin A num;` - Shorthand for `[0, num] [0, num]` (same offset for both)
- `containedin A 100 [200, 300];` - Mixed: shorthand start, full range end
- `containedin A;` - No offsets: exact containment (default behavior)

**Examples:**
```tasknet
containedin daylight [300, 600] [300, 600];  // Must have margins from daylight boundaries
containedin window 500 1000;                 // Start within 500 of start, end within 1000 of end
containedin observation 200;                 // 200 time unit margins on both sides
containedin parent;                          // Exact containment (default)
```

### Combining with Auto-Instantiation

Time-constrained dependencies work seamlessly with auto-instantiation:

```tasknet
taskdef predrive { duration_range [300, 300]; }
taskdef drive { 
  after predrive [600, 1200];  // Type-level dependency with time gap
  duration_range [6000, 6000]; 
}

task drive1 : drive {}  // Creates predrive_auto_0 with 600-1200 gap
task drive2 : drive {}  // Creates predrive_auto_1 with 600-1200 gap
```

Each `drive` task gets its own `predrive` instance, scheduled 600-1200 time units before it starts.

## Solver Modes

### Commands

TaskSAT supports two verification modes: `optimize` mode and `satisfy` mode. 
`optimize` mode is activated as follows:

```bash
python src/smt/tasknet_verifier.py some_tasknet.tn --mode optimize
```

or, since `optimize` mode is the default:

```
python src/smt/tasknet_verifier.py some_tasknet.tn
```

`satisfy` mode is activated as follows:

```bash
python src/smt/tasknet_verifier.py some_tasknet.tn --mode satisfy
```

### Explanation


Both modes perform two steps:

#### Step 1 - Find a schedule (existential):

∃ initial, schedule. constraints(initial, schedule)

Find a schedule that satisfies all constraints. The found schedule is displayed with property evaluation results.

This is the traditional planning problem that planners solve.

**Solver used**: Depends on `--mode` flag (Optimize or Solver)

#### Step 2 - Verify properties (universal):

∀ initial, schedule. constraints(initial, schedule) → properties(schedule)

Prove that properties hold for all valid schedules, not just the one found in Step 1.
The `final` block is verified in exactly this step: it is one of the `properties`,
asserting that the terminal state (at the makespan) holds for every valid schedule.

This verification capability goes beyond what traditional planners can do.

**Solver used**: Always Solver (regardless of `--mode` flag) for faster counterexample finding

#### The difference between modes:

- Optimize mode: Finds the optimal minimal schedule in Step 1. The minimization is wrt.
  * number of optional tasks instantiated: they are only scheduled if needed, and according to priority: higher priority number means higher priority.
  * start times: an attempt is made to start the tasks according to start time preference.
    It minimizes distance between desired start times and realized start times.
- Satisfy mode: Finds any valid schedule in Step 1
- **Important**: The mode flag only controls Step 1 (main schedule generation). Step 2 (property verification) always uses Solver mode for faster counterexample finding, regardless of the `--mode` flag. This is an optimization since counterexamples don't need to be optimal.

#### Step 3 (opt-in) - Realizability (forall-exists):

∀ initial. ∃ schedule. constraints(initial, schedule)

Enabled with the `--realizability` flag. Checks that **every** initial state
allowed by the spec admits some valid schedule. Neither of the first two steps
answers this:

- Step 1 only proves *some* initial state admits a schedule (the solver picks a
  convenient one).
- Step 2 is **vacuously true** for an initial state with no valid schedules — an
  implication with an empty antecedent says nothing.

For example, with `initial { battery in [0, 59]; }` and a task requiring
`battery >= 30` at its start (and no way to charge first), Steps 1 and 2 both
pass, yet the mission cannot be scheduled if the battery happens to start below
30. Step 3 reports exactly that: a concrete counterexample initial state (e.g.
`battery = 0`) together with the UNSAT core explaining why no schedule exists
from it.

```bash
python src/smt/tasknet_verifier.py some_tasknet.tn --realizability
```

The check alternates quantifiers (∀∃), which a single solver call cannot decide
here, so TaskSAT uses a counterexample-guided loop (CEGIS — a standard technique
from program synthesis, Solar-Lezama et al. 2006; see the references in
[smt-encoding.md](../theory/smt-encoding.md)): it repeatedly picks a
not-yet-covered initial state, plans from it (failure = counterexample), and
otherwise generalizes the found schedule to cover a whole region of initial
states at once. The result is HOLDS, VIOLATED (with counterexample), or UNKNOWN
if the iteration/time budget (`--realizability-max-iters`,
`--realizability-budget`) runs out.

##### How one schedule covers a whole region of initial states

The generalization step deserves explanation, because it can look like a leap:
the solver verified ONE initial state (say `battery = 30`), yet the loop crosses
off the whole interval `[30, 59]`. **No extrapolation from the sample happens.**
The sample plays only one role: it makes the planner produce a concrete schedule
(say `work: start = 10, end = 30`). After that, the sample is discarded, and a
second, independent question is answered exactly:

> *For which initial battery values `b` is this particular schedule valid?*

With the schedule's times fixed to numbers, the constraint system collapses to a
small system of inequalities in the single unknown `b`:

```
30 ≤ b ≤ 59       (the initial block)
b ≥ 30            (the task's precondition at its start)
b + 20 ≤ 100      (bounds after the task's +20 impact)
```

This system is *solved* — the way one solves any inequality, not by testing
values — and its exact solution set is `b ∈ [30, 59]`. Every value in that set
is covered *by construction*: the system IS the original constraints partially
evaluated, so any `b` satisfying it, together with the frozen schedule, makes
every original constraint true — which is precisely the definition of a valid
schedule.

Two technical notes. First, timeline values at later time points (helpers like
"battery after the task") remain existentially quantified in this residual
system; TaskSAT hands the quantified formula to Z3 rather than eliminating the
helpers by hand. Second, fixing the schedule times is also what makes the
residual system *linear* (the encoding's only nonlinear terms are
`rate × duration`), so these per-iteration queries fall in a fragment Z3 decides
reliably — this is exactly why the loop succeeds where a single monolithic ∀∃
query returns *unknown*.

For a crisp, fully formal one-page treatment of the algorithm (definitions,
soundness and progress lemmas), see [cegis.md](../theory/cegis.md).

## Understanding UNSAT Diagnostics

When TaskSAT cannot find a valid schedule, it provides diagnostics showing which constraints conflict:

```
UNSAT CORE (N conflicting constraints)

Detailed Analysis:
  [Explanation of the conflict with specific tasks/timelines/values]

Suggestions:
  [Concrete recommendations to fix the issue]

Raw Z3 Unsat Core:
  [Technical constraint labels for advanced debugging]
```

### Common Issues

**Missing dependency targets**: A task has a dependency (`after` or `containedin`) on a task definition that has no instances in the tasknet. TaskSAT validates dependencies at initialization and reports clear errors:
```
DEPENDENCY VALIDATION ERRORS
======================================================================

The following tasks have unresolvable dependencies:

1. Task 'downlink_task' has 'after preheat' dependency, 
   but no instances of 'preheat' exist in the tasknet.
2. Task 'downlink_task' has 'containedin maintainheat' dependency, 
   but no instances of 'maintainheat' exist in the tasknet.

Please add the missing task instances or remove the dependencies.
```
Fix by either: (a) adding instances of the required task definitions, or (b) removing the invalid dependencies from the task definition.

**Atomic capacity violations**: Multiple tasks need exclusive access to the same resource at overlapping times. Fix by adding temporal ordering constraints (`after`/`before`) or widening time windows.

**Impossible preconditions**: Task requires timeline values outside the valid range. Fix by adjusting the precondition range or increasing the timeline range.

**Circular dependencies**: Task A depends on B, and B depends on A. Fix by removing one dependency or changing direction.

**Timeline range violations**: Task impacts push values outside the timeline's range without a bounds clause. Fix by reducing impacts, increasing the range, or adding an explicit `bounds` clause for clamping.

**RANGE vs BOUNDS**: `range` is a hard constraint (violations cause UNSAT), while `bounds` clamps values (always SAT). Use explicit `bounds` clauses when you want clamping behavior.

## Visualizing Tasknets

For complex tasknets with many tasks and timelines, it can be helpful to visualize the
**static structure** of the model — its tasks, taskdefs, dependencies, resource
interactions, and constraints. This is distinct from the schedule/timeline charts, which
visualize a *solved* schedule. The structure diagram describes the specification itself and
does not require solving (it is meaningful even for UNSAT tasknets).

### Visualization Tool

TaskSAT provides `tasknet_structure_viz.py`, which renders the tasknet structure as a single
PNG containing two Graphviz panels **side by side** (composited into one image so both panels
share a single scale — a node box on the left is exactly the same size as one on the right):

1. **Task / taskdef relations** (left panel): tasks and taskdefs as nodes; edges for `after`
   (labeled with the gap range), `containedin` (labeled with start/end offsets),
   instance→taskdef ("of"), `mutex` (symmetric no-overlap), and `sequence` (ordering chain).
2. **Task ↔ timeline interactions** (right panel): a bipartite graph with tasks in the left
   column and timelines in the right; solid edges for `impacts` (writes, colored by timing —
   pre=green, maint=blue, post=red) and dotted edges for `pre`/`inv`/`post` reads.

### Basic Usage

```bash
python src/smt/tasknet_structure_viz.py tests/tasknet_files/examples/rover2.tn
```

By default this writes `<tasknet_dir>/visualizations/<name>_structure.png`. To choose the
output location, pass a path as a second argument:

```bash
python src/smt/tasknet_structure_viz.py tests/tasknet_files/examples/rover2.tn /path/to/out.png
```

Graphviz (`dot`) must be installed. If it is not available, the tool prints a warning and
exits without producing an image. (Compositing the two panels needs the Python `PIL`/Pillow
package; without it, the two panels are written as separate `_relations`/`_timelines` PNGs.)

### Node styling

- **Tasks** are boxes colored **by taskdef family**, using the same palette as the Gantt and
  Timeline Evolution charts — so a task that is teal in the schedule chart is teal here too.
  All instances of a taskdef (and the taskdef node itself) share one color. Task *kind* is
  shown by border/label: taskdefs have a bold border and "(taskdef)"; optional/request tasks
  have a dashed border and a "(optional)"/"(request)" label.
- **Timelines** are shaped by type: state = yellow hexagon, atomic = plum diamond,
  rate = coral box, cumulative = light-cyan box, claimable = pink oval.
- **Sessions** ([nested-subtask taskdefs](#sessions-grouping-subtasks)) render as a
  **nested box (cluster) per session instance** — e.g. `drive1` and `drive2` each a
  labeled box enclosing their `preheat`/`drive` subtasks, with the sibling
  `after`/`containedin` edges drawn inside and session-to-session dependencies drawn
  box-to-box. In the Gantt and Timeline Evolution charts the same subtasks are grouped
  into a contiguous band per instance, share one color per session, and are labeled
  `instance / subtask` (e.g. `drive1 / preheat`) rather than the flattened `drive1__preheat`.

### In the web UI

When you verify a tasknet, the structure diagram is generated automatically and shown in the
web interface: a **Structure** tab on the tasknet detail page (and a **TaskNet Structure**
card in the verification report), alongside the existing Gantt and Timeline Evolution views.

The Gantt and Timeline Evolution charts grow taller with the number of task rows so rows
never overlap, and are shown in a scrollable, drag-to-resize panel (pan both axes; click to
enlarge) — so a schedule with many tasks (e.g. a long session sequence) stays readable.

### Note on mutex / sequence

`mutex` and `sequence` are shown as high-level edges between their operands. The tool parses
the tasknet *before* desugaring so these constructs remain visible (after desugaring they
become low-level boundary comparisons). `mutex cross [...]` is labeled "mutex (cross)".







