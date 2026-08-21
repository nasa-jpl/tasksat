---
sidebar_position: 1
sidebar_label: "Property Verification"
slug: /property-verification-enhancements
---

# Property Verification Enhancements

This document describes the enhancements made to TaskSAT's property verification and error trace reporting system.

## Overview

We've enhanced TaskSAT to provide comprehensive property verification reporting with detailed error traces for temporal property violations. The system now tracks which properties pass/fail, generates structured reports, and provides rich visualizations in the web UI.

## Key Features

### 1. Property Verification Summary Report

**Location**: `.tasksat/schedules/<tasknet>/latest/properties.json`

Each verification run now generates a JSON file with detailed results for each property:

```json
[
  {
    "name": "battery_safe",
    "status": "violated",
    "duration_sec": 0.027,
    "formula": "TLAlways(sub=TLNumCmp(tl='battery', op='>=', bound=20.0))",
    "violation_zones": [0, 2, 4]
  },
  {
    "name": "battery_exists",
    "status": "holds",
    "duration_sec": 0.006,
    "formula": "TLAlways(sub=TLNumCmp(tl='battery', op='>=', bound=0.0))"
  }
]
```

**Fields**:
- `name`: Property identifier
- `status`: One of `"holds"`, `"violated"`, or `"unknown"`
- `duration_sec`: Time taken to verify this property
- `formula`: String representation of the temporal logic formula
- `violation_zones`: (Only for violated properties) List of zone indices where the violation occurs

### 2. Violation Zone Identification

The verifier now identifies which specific time zones violate a property. For `always` formulas, it evaluates the inner formula at each zone position to pinpoint violations.

**Algorithm**:
```python
def _identify_violation_zones(self, enc, model, formula):
    """
    For 'always' formulas, check each zone position.
    Returns list of zone indices where the formula is false.
    """
    violation_zones = []
    if formula.op == 'always':
        for pos in range(num_zones):
            if not model.evaluate(encode_formula_at_pos(inner, pos)):
                violation_zones.append(pos)
    return violation_zones
```

**Output Example**:
```
🔴 Generating 1 error trace visualization(s)...
  📉 Error trace for 'battery_safe' saved to: .tasksat/schedules/tasknet/2026-06-08_14-05-31/errors/battery_safe_timeline.png
      Violation detected at zones: [0, 2, 4]
```

### 3. Error Trace Artifacts

For each violated property, the following files are generated in `.tasksat/schedules/<tasknet>/<timestamp>/errors/`:

- `<property>_schedule.json` - The counterexample schedule
- `<property>_timeline.json` - Timeline evolution data
- `<property>_timeline.png` - Visual timeline with violation zones highlighted

**Note**: Error traces are stored per-verification-run, so each timestamped run keeps its own error traces. This ensures:
- All artifacts for one verification are together
- No name collisions between tasknets
- Deleting a verification cleans up its errors automatically

### 4. Web UI Enhancements

#### Property Verification Table

The verification report page now displays a comprehensive table showing all properties:

![Property Table Example]
```
┌─────────┬──────────────┬────────────────────────────────┬──────────┬──────────────┐
│ Status  │ Property     │ Formula                         │ Time     │ Actions      │
├─────────┼──────────────┼────────────────────────────────┼──────────┼──────────────┤
│ ✓       │ battery_ok   │ always (battery >= 20.0)       │ 0.027s   │              │
│ ✗       │ battery_safe │ always (battery >= 0.0)        │ 0.006s   │ Error Trace  │
└─────────┴──────────────┴────────────────────────────────┴──────────┴──────────────┘
```

**Features**:
- ✓ Green checkmark for properties that hold
- ✗ Red X for violated properties
- ? Gray question mark for unknown results
- Timing information for each property
- "Error Trace" button for violated properties

#### Summary Badge

The property verification card header shows a summary:
- Total properties checked
- Number passed/failed/unknown
- Color-coded header (green = all pass, red = any failures)

```
Property Verification Results  [2/3 passed] [1 failed]
```

#### Error Trace Viewer

Each violated property displays:
1. **Error trace visualization** - Timeline plot showing the counterexample
2. **Compare button** - Side-by-side comparison with valid schedule
3. **Violation zone highlights** - Red shading on zones where violation occurs
4. **Explanatory text** - Description of what the error trace shows

#### Side-by-Side Comparison Modal

Clicking "Compare with Valid Schedule" opens a full-screen modal showing:
- **Left panel**: Valid schedule timeline
- **Right panel**: Error trace (counterexample)
- Synchronized scrolling for easy comparison

### 5. Code Structure

**Backend changes** ([tasknet_smt.py:2303]):
- `check_temporal_properties()` now returns `(property_results, violations)` tuple
- Added `_identify_violation_zones()` method for zone-level analysis
- Enhanced with timing and status tracking per property

**Verifier changes** ([tasknet_verifier.py:136]):
- Saves `properties.json` alongside schedule/timeline data
- Passes violation zones to visualization
- Enhanced metadata with verification timing breakdown

**Web UI changes** ([tasknet_web.py:166], [verification_report.html]):
- Loads and displays `properties.json`
- Property verification table with status indicators
- Error trace section with comparison modal
- JavaScript for trace navigation and comparison

## Usage Examples

### Command Line

```bash
# Run verification (automatically generates all reports)
python src/smt/tasknet_verifier.py example.tn

# View results
ls .tasksat/schedules/example/latest/
# → metadata.json
# → properties.json        # ← NEW: Property verification summary
# → schedule.json
# → timeline.json
# → gantt.png
# → timeline.png

# View error traces (if any violations)
ls .tasksat/errors/
# → example_error_prop1_timeline.png
# → example_error_prop1_schedule.json
# → example_error_prop1_timeline.json
```

### Web UI

1. **Start the web server**:
   ```bash
   python src/smt/tasknet_web.py
   ```

2. **Navigate to verification report**:
   - Home page → Click tasknet name → Latest verification report
   - Or directly: `http://localhost:5000/report/<tasknet_name>`

3. **View property results**:
   - Property verification table shows all properties
   - Click "Error Trace" button for violated properties
   - Click "Compare with Valid Schedule" for side-by-side view

## Implementation Details

### Violation Zone Detection

The algorithm evaluates temporal formulas at each zone boundary:

1. For `always φ` formulas:
   - Iterate through all zone positions (0 to num_zones-1)
   - Evaluate inner formula φ at each position
   - Mark positions where φ evaluates to false

2. For other formulas:
   - Mark position 0 as violation point (conservative default)

3. Store violation zones in the property result

### Timeline Visualization Enhancement

The `create_timeline_evolution_plot()` function accepts `violation_zones` parameter:
- Highlights violation zones with red background shading
- Draws vertical red lines at zone boundaries
- Adds legend entry for violation markers

### Web UI Data Flow

```
Verifier → properties.json → Flask route → Template → JavaScript → User
           └─ violations  → .tasksat/errors/ ─────┘
```

1. Verifier generates `properties.json` with structured data
2. Flask loads JSON and passes to template
3. Template renders table with Jinja2 loops and filters
4. JavaScript adds interactivity (navigation, modal, comparison)

## Testing

### Test Case: Property Violation

File: `test_property_violation.tn`

```tasknet
tasknet TestPropertyViolation {
  end = 100;
  timelines {
    battery: rate [0.0, 100.0] bounds [0.0, 100.0] = 100.0;
  }
  task drain1 {
    duration 10;
    impacts { post { battery +~ -40.0; } }
  }
  task drain2 {
    duration 10;
    after drain1;
    impacts { post { battery +~ -50.0; } }  // Violation!
  }
  properties {
    prop battery_safe: always (battery >= 20.0);  // VIOLATED
    prop battery_exists: always (battery >= 0.0); // HOLDS
  }
}
```

**Expected Output**:
- `battery_safe`: violated (counterexample generated)
- `battery_exists`: holds (no error trace)

**Verification**:
```bash
python src/smt/tasknet_verifier.py test_property_violation.tn
# → properties.json shows 1 violated, 1 holds
# → Error trace generated in .tasksat/errors/
# → Web UI displays property table with status indicators
```

## Future Enhancements

Potential improvements for future work:

1. **Violation explanation** - Natural language explanation of why property violated
2. **Repair suggestions** - Automated suggestions for fixing violations
3. **Minimal counterexample** - Minimize schedule to smallest violation
4. **Timeline scrubbing** - Interactive timeline player in web UI
5. **Export formats** - PDF reports, LaTeX tables, CSV export
6. **Property templates** - Library of common property patterns
7. **Batch verification** - Verify multiple tasknets in parallel
8. **Regression tracking** - Track property status over time

## References

- **Temporal Logic Encoding**: [SMT Encoding](../theory/smt-encoding.md)
- **TaskNet Language**: [Manual](../reference/manual.md)
- **Web UI Architecture**: [tasknet_web.py](https://github.com/nasa-jpl/tasksat/blob/main/src/smt/tasknet_web.py)
- **Visualization**: [tasknet_timeline_viz.py](https://github.com/nasa-jpl/tasksat/blob/main/src/smt/tasknet_timeline_viz.py)
