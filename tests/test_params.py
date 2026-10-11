"""Parameters: positions, instance overrides, range-valued parameters, and the
solver choice that makes preferred durations/starts matter.

Regression coverage for four defects found while auditing the documentation:

1. A range-valued parameter (`param R = [a, b];`) crashed the parser
   (`IntRange(min=..., max=...)` against positional `(low, high)` fields).
2. A tasknet with timelines but no tasks crashed `resolve_parameters()`
   (`env` unbound outside the per-task loop).
3. An instance-level `param { X = 45; }` had no effect on the taskdef's
   `duration X;` unless the instance repeated the statement.
4. Z3 `Optimize` was only constructed when optional/request tasks existed, so a
   net with only required tasks ignored preferred `start`/`duration` and
   priorities even in optimize mode.
"""

import sys
from pathlib import Path

from .conftest import verify, PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT / 'src' / 'smt'))


def _parse(text):
    from tasknet_parser import parse_tasknet
    return parse_tasknet(text)


def _transform(text):
    from tasknet_transforms import apply_transforms
    tn, _ = apply_transforms(_parse(text))
    return tn


def _task(tn, name):
    return next(t for t in tn.tasks if t.id == name)


HEADER = "tasknet P { end = 300; timelines { b : rate [0.0, 100.0] = 50.0; }"


class TestParameterPositions:
    """Every position the grammar accepts a parameter name in."""

    def test_duration_start_priority(self):
        tn = _transform(HEADER + " param D = 20; param S = 100; param P = 7; "
                        "task t { duration D; start S; priority P; } }")
        t = _task(tn, 't')
        assert (t.dur, t.start, t.priority) == (20, 100, 7)

    def test_range_valued_parameters(self):
        from tasknet_ast import IntRange
        tn = _transform(HEADER + " param DR = [30, 30]; param SR = [10, 50]; param ER = [40, 90]; "
                        "task t { duration_range DR; start_range SR; end_range ER; } }")
        t = _task(tn, 't')
        assert t.durrng == IntRange(30, 30)
        assert t.startrng == IntRange(10, 50)
        assert t.endrng == IntRange(40, 90)

    def test_real_range_parameter_declaration_parses(self):
        # The crash was in the declaration itself, independent of any use.
        tn = _parse(HEADER + " param RR = [0.5, 2.5]; task t { duration_range [1, 2]; } }")
        from tasknet_ast import RealRange
        assert tn.params[0].value == RealRange(0.5, 2.5)


class TestInstanceOverride:
    """A taskdef's parameterised field is re-resolved in each instance's scope."""

    def test_override_without_restating_duration(self):
        tn = _transform(HEADER + " param D = 20; "
                        "taskdef work { param { X = D; } duration X; priority X; } "
                        "task t1 : work {} "
                        "task t2 : work { param { X = 45; } } }")
        assert _task(tn, 't1').dur == 20            # inherited field, resolved in t1's scope
        assert _task(tn, 't2').dur == 45            # override materialised on the instance
        assert _task(tn, 't2').priority == 45
        assert _task(tn, 'work').dur == 20          # the definition keeps its own value

    def test_override_applies_to_instance_range(self):
        tn = _transform(HEADER + " param D = 20; "
                        "taskdef work { param { X = D; } duration X; } "
                        "task sci[2] : work { param { X = 33; } } }")
        assert _task(tn, 'sci_0').dur == 33
        assert _task(tn, 'sci_1').dur == 33


class TestNoTasks:
    def test_no_task_tasknet_does_not_crash(self):
        tn = _transform("tasknet N { end = 100; timelines { b : rate [0.0, 100.0] = 50.0; } }")
        assert tn.tasks == []

    def test_no_task_fixture_verifies(self):
        out = verify('tasknet71_no_tasks.tn')
        assert 'Schedule for TaskNet `NoTasks`' in out
        assert 'Traceback' not in out


class TestOptimizeEngagement:
    """Preferences and priorities need Optimize even without optional tasks."""

    def test_preferences_honoured_without_optional_tasks(self):
        from tasknet_smt import TaskNetTL
        from z3 import Optimize
        tn = _transform("tasknet D { end = 200; timelines { b : rate [0.0, 100.0] = 50.0; } "
                        "task t { duration 30; duration_range [1, 60]; } "
                        "task u { start 100; duration_range [5, 5]; } }")
        enc = TaskNetTL(tn, error_trace=False, use_optimization=True, track=False)
        assert isinstance(enc.solver, Optimize)
        model, _ = enc.solve()
        assert model is not None
        s = lambda v: model.eval(v).as_long()
        assert s(enc.end_vars['t']) - s(enc.start_vars['t']) == 30
        assert s(enc.start_vars['u']) == 100

    def test_plain_solver_when_nothing_to_optimize(self):
        from tasknet_smt import TaskNetTL
        from z3 import Solver
        tn = _transform("tasknet D { end = 200; timelines { b : rate [0.0, 100.0] = 50.0; } "
                        "task t { duration_range [1, 60]; } }")
        enc = TaskNetTL(tn, error_trace=False, use_optimization=True, track=False)
        assert isinstance(enc.solver, Solver)


class TestPrinterRoundTrip:
    """Pre-transform ASTs print parameter names, not dataclass reprs."""

    def test_round_trip_is_stable(self):
        from tasknet_parser import parse_tasknet_file, parse_tasknet
        from tasknet_printer import print_tasknet_to_string
        src = Path(PROJECT_ROOT, 'tests/tasknet_files/valid/tasknet70_params_extended.tn')
        once = print_tasknet_to_string(parse_tasknet_file(str(src)))
        twice = print_tasknet_to_string(parse_tasknet(once))
        assert once == twice
        assert 'ParamRef(' not in once
        for frag in ('duration X;', 'priority P;', 'duration_range DR;', 'start_range SR;', 'start S;'):
            assert frag in once


class TestEndToEnd:
    def test_extended_fixture_schedules_with_preferences(self):
        out = verify('tasknet70_params_extended.tn')
        assert 'Schedule for TaskNet `ParamsExtended`' in out
        # t1 prefers 20, t2 overrides to 45, t3 is pinned to 30, t4 prefers start 100
        import re
        def span(name):
            m = re.search(rf"{name}\s*: start =\s*(\d+), end =\s*(\d+)", out)
            return int(m.group(1)), int(m.group(2))
        assert span('t1')[1] - span('t1')[0] == 20
        assert span('t2')[1] - span('t2')[0] == 45
        assert span('t3')[1] - span('t3')[0] == 30
        assert span('t4')[0] == 100
        assert 'Traceback' not in out
