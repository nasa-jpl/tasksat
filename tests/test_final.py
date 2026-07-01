"""Tests for the `final {...}` block.

The final block is checked as a property: for every valid schedule, the terminal
state (right after the last scheduled task ends) must satisfy the constraints.
"""

import pytest
from .conftest import *


class TestFinalBlock:
    """Test the `final {...}` terminal-state property."""

    def test_final_holds(self):
        """battery ends at 70 (in [55,100]) and mode = idle -> final HOLDS."""
        verify_out('tasknet46_final_holds.tn')(
            "*** NEW SCHEDULE***",
            "work          : start =   10, end =   30",
            "[1/1] Checking final state property 'final'...",
            "  → HOLDS",
            "Summary: 1 hold, 0 violated, 0 unknown"
        )

    def test_final_violated(self):
        """battery ends at 70, which is not in [80,100] -> final VIOLATED."""
        verify_out('tasknet47_final_violated.tn')(
            "*** NEW SCHEDULE***",
            "[1/1] Checking final state property 'final'...",
            "  → VIOLATED!",
            "Summary: 0 hold, 1 violated, 0 unknown"
        )

    def test_final_extends_initial(self):
        """`final extends initial` checks initial's constraints (mode = idle)
        plus the added battery constraint; both hold -> HOLDS."""
        verify_out('tasknet48_final_extends.tn')(
            "*** NEW SCHEDULE***",
            "[1/1] Checking final state property 'final'...",
            "  → HOLDS",
            "Summary: 1 hold, 0 violated, 0 unknown"
        )

    def test_final_rate_makespan(self):
        """Rate timeline: fuel = 75 right after the last task (t=25), 0 at the
        horizon (t=100). final { fuel in [70,80] } is checked at the makespan,
        so it HOLDS -- guarding the makespan-vs-endTime distinction."""
        verify_out('tasknet49_final_rate_makespan.tn')(
            "*** NEW SCHEDULE***",
            "burn          : start =    5, end =   25",
            "[1/1] Checking final state property 'final'...",
            "  → HOLDS",
            "Summary: 1 hold, 0 violated, 0 unknown"
        )

    def test_final_bad_timeline_rejected(self):
        """Wellformedness: a final constraint on a non-existent timeline is a
        clear error, not a crash."""
        output = verify('final_bad_timeline.tn', valid=False, check=False)
        contains_all(output, [
            "WELL-FORMEDNESS ERRORS DETECTED",
            "final_constraints final condition references non-existent timeline 'nonexistent'",
        ])

    def test_initial_state_name_resolved(self):
        """Regression: a state-NAME constraint in an `initial` block (mode = idle)
        must be resolved to a state and enforced. If resolution were broken the
        constraint would be unsatisfiable (UNSAT); a valid schedule proves it
        works. Also confirms a final state-name constraint (mode = busy) holds."""
        verify_out('tasknet50_initial_state_name.tn')(
            "*** NEW SCHEDULE***",
            "work          : start =   10, end =   30",
            "[1/1] Checking final state property 'final'...",
            "  → HOLDS",
            "Summary: 1 hold, 0 violated, 0 unknown"
        )
