"""
Tests for time variable and task boundary (task.start, task.end) features.
"""

import pytest
import sys
import os

# Add src/smt to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'smt'))

from tasknet_parser import parse_tasknet
from tasknet_smt import TaskNetTL


def test_time_variable_simple():
    """Test that 'time' variable works in constraints"""
    code = '''
    tasknet Test {
      end = 100;
      task T1 { duration 10; }
      constraints {
        prop early: time < 50;
      }
    }
    '''
    tn = parse_tasknet(code)
    smt = TaskNetTL(tn, use_optimization=False)
    model, _ = smt.solve()
    assert model is not None, "Should find schedule with time < 50"


def test_task_boundary_ordering():
    """Test task.start and task.end for ordering constraints"""
    code = '''
    tasknet Test {
      end = 100;
      task T1 { duration 10; }
      task T2 { duration 10; }
      constraints {
        prop order: T1.start >= T2.end;
      }
    }
    '''
    tn = parse_tasknet(code)
    smt = TaskNetTL(tn, use_optimization=False)
    model, _ = smt.solve()
    assert model is not None, "Should find schedule with T1 after T2"

    # Verify ordering in schedule
    t1_start = model.eval(smt.start_vars["T1"]).as_long()
    t2_end = model.eval(smt.end_vars["T2"]).as_long()
    assert t1_start >= t2_end, f"T1.start ({t1_start}) should be >= T2.end ({t2_end})"


def test_task_boundary_time_window():
    """Test constraining task start times with boundaries"""
    code = '''
    tasknet Test {
      end = 100;
      task T1 { duration 10; }
      constraints {
        prop early: T1.start <= 20;
        prop late: T1.end >= 15;
      }
    }
    '''
    tn = parse_tasknet(code)
    smt = TaskNetTL(tn, use_optimization=False)
    model, _ = smt.solve()
    assert model is not None, "Should find schedule in time window"

    # Verify ordering in schedule
    t1_start = model.eval(smt.start_vars["T1"]).as_long()
    t1_end = model.eval(smt.end_vars["T1"]).as_long()
    assert t1_start <= 20, f"T1.start ({t1_start}) should be <= 20"
    assert t1_end >= 15, f"T1.end ({t1_end}) should be >= 15"


def test_task_boundary_comparison():
    """Test comparisons between task boundaries"""
    code = '''
    tasknet Test {
      end = 100;
      task T1 { duration 10; }
      task T2 { duration 10; }
      task T3 { duration 10; }
      constraints {
        prop order1: T1.end < T2.start;
        prop order2: T2.end < T3.start;
      }
    }
    '''
    tn = parse_tasknet(code)
    smt = TaskNetTL(tn, use_optimization=False)
    model, _ = smt.solve()
    assert model is not None, "Should find sequential schedule"

    # Verify ordering in schedule
    t1_end = model.eval(smt.end_vars["T1"]).as_long()
    t2_start = model.eval(smt.start_vars["T2"]).as_long()
    t2_end = model.eval(smt.end_vars["T2"]).as_long()
    t3_start = model.eval(smt.start_vars["T3"]).as_long()

    assert t1_end < t2_start, f"T1 should end before T2 starts"
    assert t2_end < t3_start, f"T2 should end before T3 starts"


def test_time_and_task_boundary_mixed():
    """Test mixing time variable with task boundaries"""
    code = '''
    tasknet Test {
      end = 100;
      task T1 { duration 10; }
      task T2 { duration 10; }
      constraints {
        prop T1_early: T1.start < 30;
        prop T2_after_T1: T2.start >= T1.end;
        prop all_before_50: time < 50;
      }
    }
    '''
    tn = parse_tasknet(code)
    smt = TaskNetTL(tn, use_optimization=False)
    model, _ = smt.solve()
    assert model is not None, "Should find schedule satisfying all constraints"


def test_optional_task_conditional_boundary():
    """Test that referencing task.start/end is conditional for optional tasks"""
    code = '''
    tasknet Test {
      end = 100;
      task required { duration 10; }
      optional task opt { duration 10; }
      constraints {
        prop order: opt.start >= required.end;
      }
    }
    '''
    tn = parse_tasknet(code)
    smt = TaskNetTL(tn, use_optimization=True)
    model, _ = smt.solve()
    assert model is not None, "Should find schedule"

    # Verify optional task is NOT forced (optimizer minimizes optional tasks)
    opt_included = model.eval(smt.optional_included["opt"])
    # Since constraint is conditional, opt should not be included (minimized)
    assert not opt_included, "Optional task should not be forced when constraint is conditional"


def test_request_task_conditional_boundary():
    """Test that referencing task.start/end is conditional for request tasks"""
    code = '''
    tasknet Test {
      end = 100;
      task required { duration 10; }
      request task req { duration 10; }
      constraints {
        prop order: req.end <= required.start;
      }
    }
    '''
    tn = parse_tasknet(code)
    smt = TaskNetTL(tn, use_optimization=True)
    model, _ = smt.solve()
    assert model is not None, "Should find schedule"

    # Verify request task CAN be included (optimizer maximizes request tasks)
    # But the constraint is conditional, so it only applies if req is scheduled
    req_included = model.eval(smt.request_included["req"])
    # Request tasks are maximized, so it should be included if possible
    if req_included:
        # If included, verify ordering
        req_end = model.eval(smt.end_vars["req"]).as_long()
        required_start = model.eval(smt.start_vars["required"]).as_long()
        assert req_end <= required_start, "If request task is scheduled, ordering must hold"


def test_unsat_impossible_ordering():
    """Test that impossible orderings result in UNSAT"""
    code = '''
    tasknet Test {
      end = 100;
      task T1 { duration 10; }
      task T2 { duration 10; }
      constraints {
        prop impossible1: T1.start >= T2.end;
        prop impossible2: T2.start >= T1.end;
      }
    }
    '''
    tn = parse_tasknet(code)
    smt = TaskNetTL(tn, use_optimization=False)
    model, _ = smt.solve()
    assert model is None, "Circular dependency should be UNSAT"


def test_time_before_task_start():
    """Test time comparisons with task.start in temporal formulas"""
    code = '''
    tasknet Test {
      end = 100;
      task T1 { duration 10; start 50; }
      constraints {
        prop before_T1: always (time < T1.start);
      }
    }
    '''
    tn = parse_tasknet(code)
    smt = TaskNetTL(tn, use_optimization=False)
    result = smt.solve()
    # This should be UNSAT because time ranges over all zones with 'always',
    # and some zones will be >= T1.start
    # When UNSAT, solve() returns (None, unsat_core_data) tuple
    assert result[0] is None, "always (time < T1.start) cannot hold at all zones"


def test_complex_boundary_constraints():
    """Test complex constraints with multiple task boundaries"""
    code = '''
    tasknet Test {
      end = 100;
      task A { duration 10; }
      task B { duration 10; }
      task C { duration 10; }
      constraints {
        prop A_before_B: A.end <= B.start;
        prop B_before_C: B.end <= C.start;
        prop A_early: A.start < 20;
        prop C_late: C.end > 30;
      }
    }
    '''
    tn = parse_tasknet(code)
    smt = TaskNetTL(tn, use_optimization=False)
    model, _ = smt.solve()
    assert model is not None, "Should find schedule satisfying all constraints"

    # Verify ordering in schedule
    a_start = model.eval(smt.start_vars["A"]).as_long()
    a_end = model.eval(smt.end_vars["A"]).as_long()
    b_start = model.eval(smt.start_vars["B"]).as_long()
    b_end = model.eval(smt.end_vars["B"]).as_long()
    c_start = model.eval(smt.start_vars["C"]).as_long()
    c_end = model.eval(smt.end_vars["C"]).as_long()

    assert a_end <= b_start, "A should end before or when B starts"
    assert b_end <= c_start, "B should end before or when C starts"
    assert a_start < 20, "A should start early"
    assert c_end > 30, "C should end late"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
