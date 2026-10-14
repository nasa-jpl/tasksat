"""
A task may assign a timeline at most once at each boundary (`pre`, `post`).

Regression: two assignments to the same timeline in one block were only
forbidden by an encoder constraint, so the tasknet came out unsatisfiable with
an empty unsat core. Well-formedness now reports it.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'smt'))

from tasknet_parser import parse_tasknet
from tasknet_transforms import apply_transforms
from tasknet_wellformedness import WellFormednessChecker


def _errors(code):
    tn, _ = apply_transforms(parse_tasknet(code))
    return WellFormednessChecker(tn).check()


def _tasknet(impacts):
    return f'''
    tasknet T {{
      end = 50;
      timelines {{
        m : state(a, b) = a;
        r : rate [0.0, 100.0] bounds [0.0, 100.0] = 50.0;
      }}
      task t {{ id 1; duration 5; impacts {{ {impacts} }} }}
    }}
    '''


def test_two_assignments_same_block_rejected():
    errors = _errors(_tasknet("post { m = b; m = a; }"))
    assert any("more than one '=' assignment" in e.message for e in errors)


def test_identical_assignments_same_block_rejected():
    errors = _errors(_tasknet("pre { m = b; m = b; }"))
    assert any("more than one '=' assignment" in e.message for e in errors)


def test_two_rate_assignments_same_block_rejected():
    errors = _errors(_tasknet("pre { r =~ 1.0; r =~ 2.0; }"))
    assert any("more than one '=~' assignment" in e.message for e in errors)


def test_pre_and_post_assignment_allowed():
    errors = _errors(_tasknet("pre { m = b; } post { m = a; }"))
    assert not errors


def test_assignment_and_rate_assignment_allowed():
    errors = _errors(_tasknet("pre { r = 10.0; r =~ 1.0; }"))
    assert not any("more than one" in e.message for e in errors)
