# TaskSAT Tutorial

This tutorial provides an in-depth walkthrough of TaskSAT concepts, patterns, and best practices.

> **Prerequisites**: Install TaskSAT and run your first example by following [Getting Started](getting-started.md) first. 

## An Example

### The Complete Tasknet Model

Let's start with a complete TaskSAT specification and then understand each part. This example models a Mars rover conducting a science mission. The complete file is available at [tests/tasknet_files/examples/rover2.tn](../tests/tasknet_files/examples/rover2.tn).

```
tasknet Rover2 {
  end = 400;

  timelines {
    arm : atomic = false;
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
        battery +~ -1.5;  
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
        battery +~ -0.5; 
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
        battery +~ -0.5;   
        temperature +~ -0.2;
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
    arm : atomic = false;
    location : state(home, target) = home;
    data : cumulative [0.0, 50.0] bounds [0.0, 100.0] = 0.0;
    battery : rate [10.0, 100.0] bounds [0.0, 100.0] = 60.0;
    temperature : rate [5.0, 40.0] bounds [0.0, 100.0] = 10.0;
  }
```

There are different kinds of timelines, four of which are shown here: atomic, state, cumulative, and rate.

- The `arm` timeline is atomic, which means a Boolean that can be assigned the values `true` and `false`.
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
        battery +~ -1.5;  
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
        battery +~ -0.5;  
        temperature +~ 2;  
      }
    }
  }
```
  
#### The collect Task Instance

The `collect` task shows some new concepts. It has a pre-condition containing a couple of equalities: the `location` be at the `target` and the arm must not aleady be deployed. We also now see a pre-impact, executed at the beginning of the task exection, namely that the `arm` is deployed (becoming true). At the end of the execution, the `data` timelines is augmented with 40.

```  
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
        battery +~ -0.5;  
        temperature +~ -0.2;
      }
      post {
        data += 40.0;  
        arm = false; 
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

This verification capability goes beyond what traditional planners can do.

**Solver used**: Always Solver (regardless of `--mode` flag) for faster counterexample finding

#### The difference between modes:

- Optimize mode: Finds the optimal minimal schedule in Step 1. The minimization is wrt.
  * number of optional tasks instantiated: they are only schedules if needed, and according to priority: lower priority numnber means higher priority.
  * start times: an attempt is made to start the tasks according to start time preference.
    It minimizes distance between desired start times and realized stat times.
- Satisfy mode: Finds any valid schedule in Step 1
- **Important**: The mode flag only controls Step 1 (main schedule generation). Step 2 (property verification) always uses Solver mode for faster counterexample finding, regardless of the `--mode` flag. This is an optimization since counterexamples don't need to be optimal.

## Visualizing Tasknets

For complex tasknets with many tasks and timelines, it can be helpful to visualize the structure of the model. TaskSAT includes two visualization tools that generate graph diagrams showing task dependencies and timeline interactions.

### Visualization Tools

TaskSAT provides two visualization layouts:

1. **Standard Layout** (`tasknet_visualize.py`): Generates task dependency graphs and timeline interaction graphs with a left-to-right layout
2. **Vertical Layout** (`tasknet_visualize_vert.py`): Generates task dependency graphs with vertical containment (container tasks above/below contained tasks) and temporal ordering

### Basic Usage - Standard Layout

To visualize a tasknet file, use the `tasknet_visualize.py` script:

```bash
python src/smt/tasknet_visualize.py tests/tasknet_files/examples/rover2.tn
```

This generates two types of graphs in a `visualizations/` directory next to your tasknet file:

1. **Task Dependency Graph** (`*_tasks.dot` and `*_tasks.png`): Shows relationships between tasks
2. **Timeline Interaction Graph** (`*_timeline_interactions.dot` and `*_timeline_interactions.png`): Shows how tasks interact with timelines

### Basic Usage - Vertical Layout

For a vertical containment-focused layout:

```bash
python src/smt/tasknet_visualize_vert.py tests/tasknet_files/examples/rover2.tn
```

This generates a task dependency graph (`*_tasks_timeline.dot` and `*_tasks_timeline.png`) with:
- Vertical positioning showing containment relationships (container tasks appear in same rank as contained tasks)
- Horizontal temporal ordering (earlier tasks to the left)
- Dependency arrows pointing backward (dependent → prerequisite)

Both `.dot` (Graphviz format) and `.png` (rendered image) files are generated automatically if Graphviz is installed on your system.

### Understanding the Task Dependency Graph

The task dependency graph shows:

- **Task instances** (boxes): Actual tasks that will be scheduled
- **Explicit dependencies** (blue solid arrows): `after` and `containedin` relationships declared in the tasknet
- **Implicit dependencies** (green dashed arrows): Dependencies inferred from timeline states (e.g., when one task sets a boolean flag that another task requires)

**Arrow Directions:**
- In the **standard layout**, arrows point forward in time (A → B means B comes after A)
- In the **vertical layout**, arrows point backward showing dependencies (B → A means B depends on A)

For example, if task A sets `completed = true` in its `post` block and task B requires `completed = true` as a `pre` condition:
- Standard layout: Shows A → B (labeled "assumes completed")
- Vertical layout: Shows B → A (labeled "assumes completed")

By default, task definitions (templates) are hidden, showing only task instances for clarity.

### Understanding the Timeline Interaction Graph

The timeline interaction graph shows:

- **Timelines** (ellipses): State variables from your tasknet
- **Tasks** (boxes): Tasks that read or modify timelines
- **Constraint arrows**: Pre-conditions, invariants, and post-conditions on timelines
- **Impact arrows**: How tasks modify timeline values (assignments, additions, rates)

This helps you understand which tasks affect which timelines and what constraints are in place.

### Customization Options

#### Include Detailed Information (Standard Layout Only)

Add the `--detail` flag to include additional information like time ranges, constraint details, and impact specifics:

```bash
python src/smt/tasknet_visualize.py tests/tasknet_files/examples/rover2.tn --detail
```

#### Show Task Definitions

To include task definitions (templates) in addition to task instances (available on both tools):

```bash
python src/smt/tasknet_visualize.py tests/tasknet_files/examples/rover2.tn --show-definitions
# or
python src/smt/tasknet_visualize_vert.py tests/tasknet_files/examples/rover2.tn --show-definitions
```

#### Custom Output Location

By default, visualizations are created in a `visualizations/` subdirectory next to your tasknet file. To specify a different location (available on both tools):

```bash
python src/smt/tasknet_visualize.py tests/tasknet_files/examples/rover2.tn --output-dir /path/to/output
# or
python src/smt/tasknet_visualize_vert.py tests/tasknet_files/examples/rover2.tn --output-dir /path/to/output
```

### Example: Visualizing the Rover2 Tasknet

Running the standard visualization on our rover example:

```bash
python src/smt/tasknet_visualize.py tests/tasknet_files/examples/rover2.tn
```

Produces:
- `tests/tasknet_files/examples/visualizations/rover2_tasks.png`: Shows the four task instances (charge, drive, heating, collect) and their dependencies
- `tests/tasknet_files/examples/visualizations/rover2_timeline_interactions.png`: Shows the five timelines (arm, location, data, battery, temperature) and how each task interacts with them

Running the vertical layout visualization:

```bash
python src/smt/tasknet_visualize_vert.py tests/tasknet_files/examples/rover2.tn
```

Produces:
- `tests/tasknet_files/examples/visualizations/rover2_tasks_timeline.png`: Shows tasks with vertical containment and horizontal temporal ordering

Both visualizations will show that the `collect` task has an implicit dependency on the `drive` task (via the `location` timeline being set to `target`), helping you understand the ordering constraints in your model.







