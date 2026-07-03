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

    def test_final_within_initial(self):
        """`final within initial` checks initial's constraints (mode = idle)
        plus the added battery constraint; both hold -> HOLDS."""
        verify_out('tasknet48_final_within.tn')(
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

    def test_final_within_initial_blockless(self):
        """Blockless form `final within initial;`: the final property is exactly
        the initial constraints. mode starts idle and ends idle -> HOLDS."""
        verify_out('tasknet51_final_within_blockless.tn')(
            "*** NEW SCHEDULE***",
            "work          : start =   10, end =   30",
            "[1/1] Checking final state property 'final'...",
            "  → HOLDS",
            "Summary: 1 hold, 0 violated, 0 unknown"
        )

    def test_final_within_blockless_roundtrip(self):
        """Parse -> print -> re-parse preserves the blockless within form."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent / 'src' / 'smt'))
        from tasknet_parser import parse_tasknet_file, parse_tasknet
        from tasknet_printer import print_tasknet_to_string

        tn = parse_tasknet_file(
            'tests/tasknet_files/valid/tasknet51_final_within_blockless.tn')
        assert tn.final_extends_initial is True
        assert tn.final_constraints == []

        printed = print_tasknet_to_string(tn)
        assert "final within initial;" in printed

        tn2 = parse_tasknet(printed)
        assert tn2.final_extends_initial is True
        assert tn2.final_constraints == []

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
