"""Tests for the realizability check (--realizability).

Semantics: forall initial state i . exists schedule s . valid(i, s) — every
initial state admitted by the spec (declared initials + `initial {...}` block +
zone-0 ranges) must admit some valid schedule. Verified by a CEGIS loop in
src/smt/tasknet_realizability.py.
"""

import pytest
from .conftest import *


class TestRealizability:
    """End-to-end tests via the verifier CLI."""

    def test_holds(self):
        """All initial battery values in [30,59] are schedulable -> HOLDS."""
        verify_out('tasknet52_realizability_holds.tn',
                   extra_args=['--realizability'])(
            "*** NEW SCHEDULE***",
            "Checking realizability",
            "→ HOLDS",
            "schedule skeleton",
        )

    def test_violated(self):
        """Initial battery in [0,59] but the task needs >= 30: validity passes
        (picks a chargeable state), but battery < 30 admits NO schedule ->
        VIOLATED with a concrete counterexample initial state."""
        verify_out('tasknet53_realizability_violated.tn',
                   extra_args=['--realizability'])(
            "*** NEW SCHEDULE***",
            "Checking realizability",
            "→ VIOLATED",
            "Initial state with no valid schedule",
            "battery",
            "realizability_pin",  # the pin appears in the printed unsat core
        )

    def test_holds_multiple_skeletons(self):
        """No single schedule covers the initial region: low batteries must run
        the optional charge task, high batteries must not (range overflow). The
        CEGIS loop needs two iterations/skeletons -> HOLDS with 2 skeletons.
        Exercises the generalization + blocking interplay across iterations."""
        verify_out('tasknet55_realizability_multiskeleton.tn',
                   extra_args=['--realizability'])(
            "Checking realizability",
            "[iter 1]",
            "[iter 2]",
            "→ HOLDS",
            "2 schedule skeleton(s)",
        )

    def test_single_point_shortcut(self):
        """All timelines declare initial values -> the check coincides with the
        validity check and returns HOLDS without any CEGIS iterations."""
        verify_out('tasknet54_realizability_singlepoint.tn',
                   extra_args=['--realizability'])(
            "→ HOLDS",
            "fully determined",
        )

    def test_flag_off_no_check(self):
        """Without --realizability the check must not run."""
        output = verify('tasknet53_realizability_violated.tn')
        assert "Checking realizability" not in output


class TestInitRegionRecording:
    """Unit guard: init_region_constraints must only mention zone-0 variables
    (protects the recording sites in tasknet_smt.py against drift)."""

    def test_init_region_vars_are_zone0_only(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent / 'src' / 'smt'))
        from tasknet_parser import parse_tasknet_file
        from tasknet_transforms import apply_transforms
        from tasknet_smt import TaskNetTL
        from tasknet_realizability import _zone0_vars
        from z3 import And
        from z3.z3util import get_vars

        tn = parse_tasknet_file(
            'tests/tasknet_files/valid/tasknet52_realizability_holds.tn')
        tn, _ = apply_transforms(tn)
        enc = TaskNetTL(tn, error_trace=False, use_optimization=False, track=False)

        assert enc.init_region_constraints, "init region must not be empty"
        zone0_names = {str(v) for v in _zone0_vars(enc)}
        free = get_vars(And(*enc.init_region_constraints))
        offenders = [str(v) for v in free if str(v) not in zone0_names]
        assert not offenders, (
            f"init_region_constraints mention non-zone-0 variables: {offenders}")

    def test_invariant_folds_into_zone0_region(self):
        """After the `invariant {}` desugar folds P into the initial block, the
        recorded init region must STILL mention only zone-0 vars — the extra
        P@0 conjunction must not leak evolution/schedule variables. Guards the
        compositional AE path (init region = P-region)."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent / 'src' / 'smt'))
        from tasknet_parser import parse_tasknet_file
        from tasknet_transforms import apply_transforms
        from tasknet_smt import TaskNetTL
        from tasknet_compositional import project_single_session
        from tasknet_realizability import _zone0_vars
        from z3 import And
        from z3.z3util import get_vars

        tn = parse_tasknet_file(
            'tests/tasknet_files/valid/tasknet62_compositional_holds.tn')
        projected, _ = project_single_session(tn)
        projected, _ = apply_transforms(projected)
        enc = TaskNetTL(projected, error_trace=False,
                        use_optimization=False, track=False)

        assert enc.init_region_constraints, "init region must not be empty"
        zone0_names = {str(v) for v in _zone0_vars(enc)}
        free = get_vars(And(*enc.init_region_constraints))
        offenders = [str(v) for v in free if str(v) not in zone0_names]
        assert not offenders, (
            f"init_region_constraints mention non-zone-0 variables after "
            f"invariant desugar: {offenders}")
