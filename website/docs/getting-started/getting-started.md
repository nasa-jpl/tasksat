---
sidebar_position: 1
sidebar_label: "Getting Started"
slug: /getting-started
---

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
[tests/tasknet_files/examples/rover1.tn](https://github.com/nasa-jpl/tasksat/blob/main/tests/tasknet_files/examples/rover1.tn)
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
        battery +~ 2.0;  // Cumulative: adds 2.0 to current rate during charging
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
        battery -~ 1.5;  // Cumulative: subtracts 1.5 from current rate during driving
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

## Explore the Web UI

TaskSAT includes a web interface for browsing verification results, viewing schedules, and comparing error traces.

**Start the web server:**
```bash
./start_web.sh
```

**Open your browser to:** http://localhost:5001

**Note:** You can specify a custom port: `./start_web.sh 8080`

The web UI provides:
- Browse all tasknets with verification history
- View Gantt charts and timeline visualizations
- Property verification results with error traces
- Verification timing — total time plus a per-phase breakdown (validity, properties, and, when enabled, realizability and compositional)
- Side-by-side comparison of valid schedules vs counterexamples
- Open an existing `.tn` file, or create a new tasknet, and verify it directly in the browser
- Add a `.tn` file to the list without running it (verify later), and cancel a running verification
- **UNSAT Core Analysis** with three levels of detail:
  - Human-readable conflict explanations and suggestions
  - TaskSAT constraint labels showing which constraints conflict
  - Raw Z3 SMT formulas in S-expression format for advanced debugging
- **Console Output** - Full ASCII text output from the verifier
- **Delete All Reports** - Bulk deletion of verification results (source files are preserved)

**How it works:**
- Tasknets verified in the shell automatically appear in the web UI
- You can also open existing `.tn` files (via **Open File**) or create new tasknets directly on the website
- Edits made in the browser are written back to the original file in place
- Re-verify any tasknet from the web interface with different settings

**Tip:** Run the verifier on a few tasknets first to see them in the web UI:
```bash
python src/smt/tasknet_verifier.py tests/tasknet_files/examples/rover2.tn
python src/smt/tasknet_verifier.py tests/tasknet_files/valid/tasknet67_two_missions.tn
```

Then explore and experiment with them in the web interface!

### A guided tour

The screenshots below walk through a typical session, using `rover2` (a
standard verification) and `tasknet67_two_missions` (a compositional one).

#### 1. The home page — browse verified tasknets

![Home page listing verified tasknets](/img/top.png)

The landing page lists every tasknet the tool knows about, one card each. A card
shows the tasknet name, a status badge (here **All Properties Verified**, green), a
link to reveal its source path, and buttons to **View Report** or delete it. From
the top of the page you can **Create New Tasknet** from scratch, **Open File** to add
an existing `.tn`, or **Delete All Reports** to clear the list (source files are kept).
Click **View Report** on `rover2` to open its report.

#### 2. The report header and source

![rover2 report header and source code](/img/rover2-top.png)

The report opens with a status icon and the tasknet name, the source path, and the
exact command used to verify it (both click-to-copy). The **Performance** line breaks
the run down by phase — here `Total 5.142s (validity: 1.539s, properties: 3.562s)`.

The control row lets you re-run the check with different settings without leaving the
page: the **Optimize/Satisfy** mode selector, the **Realizability** and
**Compositional** opt-in checkboxes, **Re-verify**, **Add Notes**, and **Delete**.
Below that, the **TaskNet Source Code** panel shows the syntax-highlighted spec; click
**Edit** to modify it in place and **Save & Re-verify**. **View Diagrams** reveals the
static structure/temporal diagrams, and **Console Output** expands the raw verifier log.

#### 3. Verification checks

![Verification checks table for rover2](/img/rover2-results.png)

The **Verification Checks** card lists *every* check that applies to the chosen mode,
with its result — even checks that had nothing to verify. The **Form** column shows
the logical shape (∃ = exists, ∀ = for all, over the initial state then the schedule):

- **Validity** (∃∃) — a valid schedule exists.
- **Properties** (∀∀) — the parent row aggregates the temporal properties; each one
  (`target_reached`, `drive_charge`, `temperature`) is an indented sub-item with its
  own formula, status, and time.
- **Realizability** (∀∃) and **Compositional Proof** — greyed **Not run**, because
  they are opt-in; the hint shows the flag that enables each. "Not run" rows do not
  count as failures.

Each row carries its own timing, and the footer shows the total verification time.

#### 4. The schedule and timeline evolution

![Timeline evolution charts for rover2](/img/rover2-schedule.png)

When a schedule is found, the report renders a **Gantt chart** and the **Timeline
Evolution** view — the task bars on top, then one panel per timeline showing how each
resource evolves over time (the `arm` atomic claim, the `location` state, the
continuous `battery`/`temperature` rates). Use the **zoom slider** (top-right, shown
at 100%) to scale a chart down to fit or up for detail; the panel also scrolls and its
bottom edge can be dragged to resize. Click any chart to open it full-size.

#### 5. A compositional verification

![Compositional verification of tasknet67_two_missions](/img/two-missions.png)

`tasknet67_two_missions` chains repeated **Mission** sessions and declares an
`invariant { mode = idle; }`. Verified with **Compositional** enabled, the checks card
adapts to compositional mode:

- **Validity** notes the schedule exists *for the projected single session* — the
  compositional proof reasons about one representative session rather than the whole
  N-instance chain.
- The **Compositional Proof** row (`∀∀·∀∃`) reports **holds**, combining the two
  required sub-checks — **safety** (every run keeps the invariant `P` true) and
  **realizability** (some run keeps `P` true) — over session `mission1`. The plain-
  language note explains the `{P}S{P} ⇒ ∀N. {P}Sᴺ{P}` argument: verify one session,
  and any-length sequence of it preserves the invariant (assuming no timing-gap drift
  between sessions).

### Optional: VS Code Syntax Highlighting

For better editing experience with `.tn` files:

```bash
cd vscode-dsl
code --install-extension tasknet-0.0.1.vsix --force
```






