# Getting Started with TaskSAT

This guide will get you up and running with TaskSAT in a few minutes.

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Quick Setup

1. Clone the repository:
```bash
git clone https://github.com/nasa-jpl/tasksat.git
cd tasksat
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Verify installation:

We shall now verify the installation. The file 
[tests/tasknet_files/examples/rover1.tn](../tests/tasknet_files/examples/rover1.tn)
contains the following tasknet:

```tasknet
tasknet Rover1 {
  end = 100;

  timelines {
    battery : rate [10.0, 100.0] bounds [0.0, 100.0] = 10.0;
    location : state(home, target) = home;
  }

  task charge {
    duration_range [30,40];

    pre {
      location = home;
      battery in [0.0, 60.0];
    }

    impacts {
      maint {
        battery +~ 2.0; 
      }
    }
  }  

  task drive {
    duration_range [30,40];

    pre {
      battery in [90.0, 100.0]; 
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

  properties {
    prop target_reached: eventually location = target;
  }
}
```

It specifies a tasknet of a rover that is supposed to drive to a target, but the driving engine needs to be heated first. It defines 
two timelines (global variables that tasks can update) and two tasks.
The `battery` time line is bound to be within 0 to 100 (its type) but a constraint is that it stays within 10 to 100 in a schedule. Its initial value is 10. The `location` timeline is an enumerated type representing the rover's location. 

The `charge` task is requested to last between 30 and 40 time units.
A pre condition for its execution is that its `location` is at `home`, and the `battery` must be no greater than 60. The impact of the task is to increase the `battery` charge with 2.0 for each time unit it executes.

The `drive` task similarly has a pre-condition. It has two impacts. During its execution it drains the `battery` with 1.5 per time unit, and at the end it sets the `location` to `target`.

Finally a linear temporal logic property states what we expect any schedule of this tasknet to satisy, namely that the target is reached.
This is a property we want to verify.

Execute the following command:

```bash
python src/smt/tasknet_verifier.py tests/tasknet_files/examples/rover1.tn
```

If you see a schedule output like the one below, you're ready to go!

```
*** NEW SCHEDULE***

Schedule for TaskNet `Rover1`:
  charge        : start =    1, end =   41
  drive         : start =   42, end =   82

Zone boundaries (z_i):
  z_ 0 = 0
  z_ 1 = 1
  z_ 2 = 41
  z_ 3 = 42
  z_ 4 = 82
  z_ 5 = 100

Values in each zone:

  -- zone 0: (0, 1] --
    active tasks : (none)
    battery        = 10 -> 10
    location       = home

  -- zone 1: (1, 41] --
    active tasks : charge
    battery        = 10 -> 90
    location       = home

  -- zone 2: (41, 42] --
    active tasks : (none)
    battery        = 90 -> 90
    location       = home

  -- zone 3: (42, 82] --
    active tasks : drive
    battery        = 90 -> 30
    location       = home

  -- zone 4: (82, 100] --
    active tasks : (none)
    battery        = 30 -> 30
    location       = target

Checking 1 temporal properties:
PROPERTY 'target_reached' HOLDS
```

It shows

- When each task runs (start/end times)
- What time zones it considers
- How resources change over time (battery level, location)
- Whether temporal properties are satisfied (✓ or ✗)

Specifically it shows that

- The rover charged for 40 time units: battery: 50 → 90
- The rover drove for 40 time units: battery: 90 → 30
- The temporal property is satisfied: ✓

### Optional: VS Code Syntax Highlighting

For better editing experience with `.tn` files:

```bash
cd vscode-dsl
code --install-extension tasknet-0.0.1.vsix --force
```






