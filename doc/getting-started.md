# Getting Started with TaskSAT

This guide will get you up and running with TaskSAT in a few minutes.

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Quick Setup

1. Clone the repository:
```bash
git clone https://github.jpl.nasa.gov/pass/tasksat.git
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
[tests/tasknet_files/examples/my_robot.tn](../tests/tasknet_files/examples/my_robot.tn)
contains the following tasknet:

```javascript
tasknet MyRobot {
  end = 100;

  timelines {
    battery : rate [10.0, 100.0] bounds [0.0, 100.0] = 50.0;
    location : state(home, target) = home;
  }

  task charge {
    id 1;
    duration 20;

    pre {
      location = home;
      battery in [0.0, 60.0];
    }

    impacts {
      maint {
        battery +~ 2.0;  // Charge at 2 units per time
      }
    }
  }

  task drive {
    id 2;
    duration 30;

    pre {
      battery in [30.0, 100.0];  // Need enough power
    }

    impacts {
      pre {
        location = target;
      }
      maint {
        battery +~ -1.0;  // Drain 1 unit per time
      }
    }
  }

  property {
    prop target_reached: eventually location = target;
  }
}
```

It specifies a tasknet of a robot with two timelins (global variables that tasks can update) and two tasks, a battery charging task and a driving task.

Execute the following command:

```bash
python src/smt/tasknet_verifier.py tests/tasknet_files/examples/my_robot.tn
```

If you see a schedule output like the one below, you're ready to go!

```
*** NEW SCHEDULE***

Schedule for TaskNet `MyRobot`:
  charge        : start =    1, end =   15
  drive         : start =   16, end =   17

Zone boundaries (z_i):
  z_ 0 = 0
  z_ 1 = 1
  z_ 2 = 15
  z_ 3 = 16
  z_ 4 = 17
  z_ 5 = 100

Values in each zone:

  -- zone 0: (0, 1] --
    active tasks : (none)
    battery        = 50 -> 50
    location       = home

  -- zone 1: (1, 15] --
    active tasks : charge
    battery        = 50 -> 78
    location       = home

  -- zone 2: (15, 16] --
    active tasks : (none)
    battery        = 78 -> 78
    location       = home

  -- zone 3: (16, 17] --
    active tasks : drive
    battery        = 78 -> 77
    location       = target

  -- zone 4: (17, 100] --
    active tasks : (none)
    battery        = 77 -> 77
    location       = target

No temporal properties attached to this TaskNet.
```

It shows

- When each task runs (start/end times)
- How resources change over time (battery levels, location)
- Whether temporal properties are satisfied (✓ or ✗)

Specifically it shows that

- The robot charged for 20 time units (battery: 50 → 90)
- The robot drove for 30 time units (battery: 90 → 60)
- The battery never went below 0 (property satisfied ✓)

### Optional: VS Code Syntax Highlighting

For better editing experience with `.tn` files:

```bash
cd vscode-dsl
code --install-extension tasknet-0.0.1.vsix --force
```






