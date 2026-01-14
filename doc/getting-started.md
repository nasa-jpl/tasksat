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

4. Verify installation:
```bash
python src/smt/tasknet_verifier.py tests/tasknet_files/examples/my_robot.tn
```

If you see a schedule output, you're ready to go!

### Optional: VS Code Syntax Highlighting

For better editing experience with `.tn` files:

```bash
cd vscode-dsl
code --install-extension tasknet-0.0.1.vsix --force
```

## Your First TaskNet

Let's create a simple robot scheduling problem. You can either create this file yourself or use the provided example at [tests/tasknet_files/examples/my_robot.tn](../tests/tasknet_files/examples/my_robot.tn).

### Step 1: Create `my_robot.tn`

```tasknet
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

### Step 2: Run the Verifier

```bash
python src/smt/tasknet_verifier.py my_robot.tn --mode satisfy
```

### Step 3: Understand the Output

You'll see a schedule showing:
- When each task runs (start/end times)
- How resources change over time (battery levels, location)
- Whether temporal properties are satisfied (✓ or ✗)

Example output:
```
*** NEW SCHEDULE***

Schedule for TaskNet `MyRobot`:
  charge : start =   0, end =  20
  drive  : start =  25, end =  55

Values in each zone:
  -- zone 0: (0, 20] --
    battery        = 50 -> 90
    location       = home

  -- zone 1: (25, 55] --
    battery        = 90 -> 60
    location       = target

Temporal properties:
  ✓ battery_safe: always (battery >= 0.0)
```

**What happened:**
- Robot charged for 20 time units (battery: 50 → 90)
- Robot drove for 30 time units (battery: 90 → 60)
- Battery never went below 0 (property satisfied ✓)

## Solver Modes

TaskSAT has two verification modes:

### Satisfy Mode (Fast)
```bash
python src/smt/tasknet_verifier.py my_robot.tn --mode satisfy
```
Finds **any** valid schedule quickly. Use for feasibility checks and debugging.

### Optimize Mode (Default)
```bash
python src/smt/tasknet_verifier.py my_robot.tn --mode optimize
```
Finds the **best** schedule (minimizes optional tasks). Slower but optimal.

## Next Steps

Now that you have TaskSAT running:

- **[Tutorial](tutorial.md)** - Learn concepts in depth with detailed examples
- **[Language Reference](language-reference.md)** - Complete syntax documentation
- **[Examples](examples.md)** - Real-world patterns and applications
- **[Performance](performance.md)** - Understand scaling and complexity

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

## Running Examples in this Document

All examples in this document are organized in 

```
tests/tasknet_files/examples.
```

Users can run any example, say `my_robot.py` in this documentation as folows:

```
python src/smt/tasknet_verifier.py tests/tasknet_files/examples/my_robot.tn --mode satisfy
```

If `--mode ...` is left out it will run in the default `optimize` mode.
