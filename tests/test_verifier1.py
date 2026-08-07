import pytest
from .conftest import *


class TestVerifier:
    """Test the TaskNet verifier on valid task networks"""

    def test_tasknet1_1(self):
        """Finds a valid schedule, properties hold"""
        verify_out('tasknet1.tn')(
            "*** NEW SCHEDULE***",
            "heating       : start =",
            "driving       : start =",
            "communicating : start =",
            "[1/3] Checking property 'p1'...",
            "  → HOLDS",
            "[2/3] Checking property 'p2'...",
            "  → HOLDS",
            "[3/3] Checking property 'p3'...",
            "  → HOLDS",
            "Summary: 3 hold, 0 violated, 0 unknown"
        )

    def test_tasknet2(self):
        """
        Modifiation of tasknet1:
        Loosening start and end ranges, finds different schedule, p2 violated
        """
        verify_out('tasknet2.tn')(
            "heating       : start =",
            "driving       : start =",
            "communicating : start =",
            "[1/3] Checking property 'p1'...",
            "  → VIOLATED!",
            "[2/3] Checking property 'p2'...",
            "  → VIOLATED!",
            "[3/3] Checking property 'p3'...",
            "  → HOLDS",
            "Summary: 1 hold, 2 violated, 0 unknown"
        )

    def test_tasknet3(self):
        """
        Modification of tasknet2:
        Adds property as a constraint. Now all properties hold again.
        """
        verify_out('tasknet3.tn')(
            "heating       : start =",
            "driving       : start =",
            "communicating : start =",
            "[1/3] Checking property 'p1'...",
            "  → VIOLATED!",
            "[2/3] Checking property 'p2'...",
            "  → HOLDS",
            "[3/3] Checking property 'p3'...",
            "  → HOLDS",
            "Summary: 2 hold, 1 violated, 0 unknown"
        )

    def test_tasknet4_containedin(self):
        """Simplest possible test."""
        verify_out('tasknet4_containedin.tn')(
            "parent_task   : start =    1, end =    4",
            "child_task    : start =    2, end =    3",
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet5_containedin(self):
        """..."""
        verify_out('tasknet5_containedin.tn')(
            "power_session : start =    1, end =    4",
            "sensor_reading: start =    2, end =    3",
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet6_simple_optional(self):
        """Test simple optional task that is not included in schedule"""
        verify_out('tasknet6_optional.tn')(
            "*** NEW SCHEDULE***",
            "T1            : start =   50, end =   70",
            "T2            : [OPTIONAL - NOT INCLUDED]",
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet7_comprehensive_optional(self):
        """Test comprehensive example with task definitions and optional tasks"""
        verify_out('tasknet7_optional.tn')(
            "*** NEW SCHEDULE***",
            "C1            : start =",
            "C2            : start =",
            "C3            : [OPTIONAL - NOT INCLUDED]",
            "C4            : [OPTIONAL - NOT INCLUDED]",
            "[1/1] Checking property 'p1'...",
            "  → HOLDS",
            "Summary: 1 hold, 0 violated, 0 unknown"
        )

    def test_tasknet8_with_definitions_unsat(self):
        """Test overconstrained example with definitions - should be UNSAT"""
        verify_out('tasknet8_defs.tn')(
            "UNSAT",
            "No valid schedule found"
        )

    def test_tasknet9_instances_no_body(self):
        """Testing instances without bodies"""
        verify_out('tasknet9_instances.tn')(
            "T1            : start =",
            "T2            : start =",
            "T3            : [OPTIONAL - NOT INCLUDED]",
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet10_optimize_mode(self):
        """Test with optional tasks and temporal properties

        Main schedule uses Optimize(), but property counterexamples use Solver()
        for faster verification.
        """
        verify_out('tasknet10_verify.tn')(
            "*** NEW SCHEDULE***",
            "T1            : start =",
            "T2            : start =",
            "T3            : [OPTIONAL - NOT INCLUDED]",
            "[1/1] Checking property 'p1'...",
            "  → VIOLATED!",
            "Counterexample:",
            "Summary: 0 hold, 1 violated, 0 unknown"
        )
    
    def test_tasknet10_satisfy_mode(self):
        """Test with optional tasks and temporal properties"""
        verify_out('tasknet10_verify.tn', mode='satisfy')(
            "*** NEW SCHEDULE***",
            "T1            : start =    3, end =    5",
            "T2            : start =    4, end =    6",
            "T3            : [OPTIONAL - NOT INCLUDED]",
            "[1/1] Checking property 'p1'...",
            "  → VIOLATED!",
            "Counterexample:",
            "T1            : start =    1, end =    2",
            "T2            : start =    3, end =    6",
            "T3            : start =    4, end =    5",
            "Summary: 0 hold, 1 violated, 0 unknown"
        )

    def test_tasknet11_priority(self):
        """Test with priorities and preferred start times (higher number = higher priority)"""
        verify_out('tasknet11_priority.tn')(
            "*** NEW SCHEDULE***",
            "T1            : start =",
            "T2            :",
            "T3            : [OPTIONAL - NOT INCLUDED]",
            "T4            : [OPTIONAL - NOT INCLUDED]",
            "T5            :",
            "[1/1] Checking property 'p1'...",
            "  → HOLDS",
            "Summary: 1 hold, 0 violated, 0 unknown"
        )

    def test_tasknet12_assign_numeric(self):
        """Test assignment of numeric values"""
        # Note: Timing changed after fixing rate timeline value impact zone assignment
        # (battery = 60.0 now correctly writes to zone s+1 instead of zone s)
        # The new schedule is valid and satisfies all constraints/properties
        verify_out('tasknet12_assign_numeric.tn')(
            "*** NEW SCHEDULE***",
            "heating       : start =    1, end =    2",
            "driving       : start =    3, end =    4",
            "[1/1] Checking property 'p1'...",
            "  → HOLDS",
            "Summary: 1 hold, 0 violated, 0 unknown"
        )

    def test_tasknet13_task_active(self):
        """Test __T_active syntax"""
        verify_out('tasknet13_task_active.tn')(
            "*** NEW SCHEDULE***",
            "T1            : start =    1, end =    2",
            "T2            : start =    3, end =    4",
            "[1/5] Checking property 'p1'...",
            "  → HOLDS",
            "[2/5] Checking property 'p2'...",
            "  → HOLDS",
            "[3/5] Checking property 'p3'...",
            "  → HOLDS",
            "[4/5] Checking property 'p4'...",
            "  → HOLDS",
            "[5/5] Checking property 'p5'...",
            "  → HOLDS",
            "Summary: 5 hold, 0 violated, 0 unknown"
        )
        
    def test_tasknet14_active_syntax(self):
        """Test state timeline with numeric states"""
        verify_out('tasknet14_active_syntax.tn')(
            "*** NEW SCHEDULE***",
            "T1            : start =    1, end =    2",
            "T2            : start =    3, end =    4",
            "[1/5] Checking property 'p1'...",
            "  → HOLDS",
            "[2/5] Checking property 'p2'...",
            "  → HOLDS",
            "[3/5] Checking property 'p3'...",
            "  → HOLDS",
            "[4/5] Checking property 'p4'...",
            "  → HOLDS",
            "[5/5] Checking property 'p5'...",
            "  → HOLDS",
            "Summary: 5 hold, 0 violated, 0 unknown"
        )

    def test_tasknet15_numeric_states(self):
        """Test active(T) syntax"""
        # Note: Timing changed after fixing rate timeline value impact zone assignment
        # (battery = 60.0 now correctly writes to zone s+1 instead of zone s)
        # The new schedule is valid and satisfies all constraints/properties
        verify_out('tasknet15_numeric_states.tn')(
            "*** NEW SCHEDULE***",
            "heating       : start =  296, end =  297",
            "driving       : start =  298, end =  299",
            "[1/1] Checking property 'p1'...",
            "  → HOLDS",
            "Summary: 1 hold, 0 violated, 0 unknown"
        )

    def test_tasknet23_request(self):
        """Test with request tasks (maximize inclusion)"""
        verify_out('tasknet23_request.tn')(
            "*** NEW SCHEDULE***",
            "T1            : start =",
            "T2            : [OPTIONAL - NOT INCLUDED]",
            "T3            : start =",
            "T4            : start =",
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet25_auto_instantiate_basic(self):
        """Test basic auto-instantiation: task depends on taskdef, creates instance"""
        verify_out('tasknet25_auto_instantiate_basic.tn')(
            "*** Auto-instantiated 1 task(s) from taskdefs:",
            "preheat_auto_0 (from taskdef preheat)",
            "*** NEW SCHEDULE***",
            "operation     : start =",
            "preheat_auto_0: start =",  # Auto-instance inherits INSTANCE kind, so must be scheduled
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet26_auto_instantiate_no_duplicate(self):
        """Test no duplicate: existing instance prevents auto-instantiation"""
        verify_out('tasknet26_auto_instantiate_no_duplicate.tn')(
            "*** NEW SCHEDULE***",
            "preheat_manual: start =",
            "operation     : start =",
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet27_auto_instantiate_no_cascade(self):
        """Test no cascade: auto-created instance's dependencies are not instantiated

        This test verifies that only 1 instance is created (T1_auto_0), not 2 (T1 and T0).
        The test will fail at SMT encoding because T1_auto_0's dependency on T0 is unsatisfied,
        but that failure is expected and proves no cascade occurred.
        """
        from .conftest import verify, contains_all
        output = verify('tasknet27_auto_instantiate_no_cascade.tn', check=False)
        # Verify T1 was auto-instantiated
        contains_all(output, [
            "*** Auto-instantiated 1 task(s) from taskdefs:",
            "T1_auto_0 (from taskdef T1)"
        ])
        # Verify T0 was NOT auto-instantiated (should only show 1 task, not 2)
        assert "T0_auto_0" not in output, "T0 should not be auto-instantiated (no cascade)"

    def test_tasknet28_auto_instantiate_multiple(self):
        """Test multiple instantiation: two tasks depending on same taskdef create two instances"""
        verify_out('tasknet28_auto_instantiate_multiple.tn')(
            "*** Auto-instantiated 2 task(s) from taskdefs:",
            "preheat_auto_0 (from taskdef preheat)",
            "preheat_auto_1 (from taskdef preheat)",
            "*** NEW SCHEDULE***",
            "operation1    : start =",
            "operation2    : start =",
            "preheat_auto_0: start =",  # Auto-instances inherit INSTANCE kind
            "preheat_auto_1: start =",  # Auto-instances inherit INSTANCE kind
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet56_optional_active_impact(self):
        """Regression: an EXCLUDED optional task must not fire its
        auto-generated __T_active timeline. eventually(active(opt1)) must be
        VIOLATED (a schedule excluding opt1 is a counterexample), while the
        required task's property HOLDS. Guards the inclusion-guard on atomic
        timeline impacts in tasknet_smt.py."""
        verify_out('tasknet56_optional_active_impact.tn')(
            "*** NEW SCHEDULE***",
            "[1/2] Checking property 'p1'...",
            "  → VIOLATED!",
            "[2/2] Checking property 'p2'...",
            "  → HOLDS",
            "Summary: 1 hold, 1 violated, 0 unknown"
        )

    def test_tasknet35_instance_range(self):
        """Test instance range expansion (task T[min..max] syntax)"""
        verify_out('tasknet35_instance_range.tn')(
            "*** NEW SCHEDULE***",
            "mission_0",       # Required from task mission[2..4]
            "mission_1",       # Required from task mission[2..4]
            "bonus_0",         # Required from request task bonus[1..3]
            # mission_2, mission_3 are optional (may or may not be scheduled)
            # bonus_1, bonus_2 are request (should be scheduled in optimize mode)
            "[1/3] Checking property 'required1'...",
            "  → HOLDS",
            "[2/3] Checking property 'required2'...",
            "  → HOLDS",
            "[3/3] Checking property 'required3'...",
            "  → HOLDS",
            "Summary: 3 hold, 0 violated, 0 unknown"
        )

    def test_tasknet59_session_basic(self):
        """Session sugar: a taskdef with nested `task` children flattens into
        qualified instances (drive1__preheat, drive1__drive) before the solver
        runs. The child's bare sibling ref `after preheat` is qualified during
        flattening, so drive1__drive is scheduled after drive1__preheat."""
        verify_out('tasknet59_session_basic.tn', mode='satisfy')(
            "*** NEW SCHEDULE***",
            "✓ Valid schedule found!",
            "drive1__preheat: start =",
            "drive1__drive : start =",
        )

    def test_tasknet60_session_sequence(self):
        """Session-to-session sequencing: `drive2 after drive1` fans out
        conservatively onto every child of drive2, referencing all children of
        drive1 (after the whole predecessor session). The entire drive2 session
        follows the entire drive1 session."""
        verify_out('tasknet60_session_sequence.tn', mode='satisfy')(
            "*** NEW SCHEDULE***",
            "✓ Valid schedule found!",
            "drive1__preheat: start =",
            "drive1__drive : start =",
            "drive2__preheat: start =",
            "drive2__drive : start =",
        )

    def test_tasknet61_session_containedin(self):
        """Session with a `containedin` sibling dependency (three children),
        sequenced twice via `drive2 after drive1`. drive1__drive is
        `containedin drive1__maintainheat` and after drive1__preheat — both
        bare sibling refs qualified during flattening (exercises
        qualify_containedin alongside qualify_after). The session-level
        `after drive1` fans out onto every drive2 child, so the whole drive2
        session (its own containment intact) follows the whole drive1 session."""
        verify_out('tasknet61_session_containedin.tn', mode='satisfy')(
            "*** NEW SCHEDULE***",
            "✓ Valid schedule found!",
            "drive1__preheat: start =",
            "drive1__maintainheat: start =",
            "drive1__drive : start =",
            "drive2__preheat: start =",
            "drive2__maintainheat: start =",
            "drive2__drive : start =",
        )

    # Note: the HOLDS fixture (tasknet62) has 20 chained session instances to
    # demonstrate N-independence. Its full-CLI run is slow (~60s) because the
    # standard validity/property phases are not N-independent, so it is covered
    # by a DIRECT check_compositional() call in tests/test_compositional.py
    # instead. The single-instance AE-violated case is fast end-to-end:
    def test_tasknet63_compositional_ae_violated(self):
        """Compositional check catches the vacuity trap: P = {charge in [20,100]}
        but the session's work task needs charge >= 30 with nothing to replenish
        it first. AA safety holds vacuously, but charge = 20 satisfies P with NO
        P-preserving schedule -> AE VIOLATED -> compositional VIOLATED, reported
        with the concrete counterexample initial state."""
        verify_out('tasknet63_compositional_ae_violated.tn',
                   extra_args=['--compositional'])(
            "Checking compositional invariant",
            "→ VIOLATED! (safety (every run keeps P)=holds, "
            "realizability (some run keeps P)=violated)",
            "Realizability VIOLATED",
            "charge = 20",
        )
