"""
A dependency on an optional or request task forces that task into the schedule
when the dependent task is scheduled (the semantics requires the task depended
on to be in dom(pi)).

Regression: dependencies were guarded only by the dependent task's inclusion,
so a required task could be scheduled `after` an optional task that was left
out, against that task's unconstrained start and end values.
"""

import sys
import os

import pytest
from z3 import is_true

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'smt'))

from tasknet_parser import parse_tasknet
from tasknet_smt import TaskNetTL


def _solve(code, use_optimization):
    tn = parse_tasknet(code)
    smt = TaskNetTL(tn, use_optimization=use_optimization)
    model, _ = smt.solve()
    assert model is not None
    return smt, model


@pytest.mark.parametrize("use_optimization", [False, True])
def test_after_forces_optional(use_optimization):
    code = '''
    tasknet T {
      end = 100;
      optional task O { id 1; duration_range [5, 5]; }
      task A { id 2; duration_range [5, 5]; after O; }
    }
    '''
    smt, model = _solve(code, use_optimization)
    assert is_true(model.eval(smt.optional_included["O"], model_completion=True))
    assert model.eval(smt.end_vars["O"]).as_long() <= model.eval(smt.start_vars["A"]).as_long()


@pytest.mark.parametrize("use_optimization", [False, True])
def test_containedin_forces_optional(use_optimization):
    code = '''
    tasknet T {
      end = 100;
      optional task O { id 1; duration_range [20, 20]; }
      task A { id 2; duration_range [5, 5]; containedin O; }
    }
    '''
    smt, model = _solve(code, use_optimization)
    assert is_true(model.eval(smt.optional_included["O"], model_completion=True))
    assert model.eval(smt.start_vars["O"]).as_long() <= model.eval(smt.start_vars["A"]).as_long()
    assert model.eval(smt.end_vars["A"]).as_long() <= model.eval(smt.end_vars["O"]).as_long()


def test_optional_dependent_leaves_optional_out():
    """If the dependent task is itself optional and not needed, nothing is forced."""
    code = '''
    tasknet T {
      end = 100;
      optional task O { id 1; duration_range [5, 5]; }
      optional task A { id 2; duration_range [5, 5]; after O; }
    }
    '''
    smt, model = _solve(code, True)
    assert not is_true(model.eval(smt.optional_included["A"], model_completion=True))
    assert not is_true(model.eval(smt.optional_included["O"], model_completion=True))
