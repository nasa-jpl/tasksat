"""Tests for the temporal range visualization's bounds propagation.

These exercise `_propagate_dependency_bounds` — the interval propagation that
turns a spec's start/end/duration ranges and after/containedin dependencies into
per-task feasible windows — plus end-to-end PNG rendering.

Bounds tuples are (start_min, start_max, end_min, end_max, dur_min, dur_max).
A window is infeasible iff start_min > start_max or end_min > end_max.
"""

import sys
import os

# Add src/smt to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "smt"))

import pytest

from tasknet_parser import parse_tasknet
from tasknet_transforms import apply_transforms
from tasknet_temporal_viz import (
    _propagate_dependency_bounds,
    create_temporal_range_visualization,
)


def _bounds(src: str):
    """Parse + transform a tasknet string and return propagated bounds."""
    tn = parse_tasknet(src)
    tn, _ = apply_transforms(tn)
    return tn, _propagate_dependency_bounds(tn)


# ---------------------------------------------------------------------------
# Base ranges (no dependencies)
# ---------------------------------------------------------------------------

def test_explicit_start_and_duration():
    tn, b = _bounds("""
      tasknet T {
        end = 1000;
        task a { start_range [100, 200]; duration_range [30, 50]; }
      }
    """)
    # end = start + duration: [100+30, 200+50] = [130, 250]
    assert b['a'] == (100, 200, 130, 250, 30, 50)


def test_unconstrained_task_spans_horizon():
    tn, b = _bounds("""
      tasknet T {
        end = 500;
        task a {}
      }
    """)
    sm, sM, em, eM, dm, dM = b['a']
    assert sm == 0 and sM == 500
    assert em == 0 and eM == 500


def test_instance_inherits_taskdef_ranges():
    tn, b = _bounds("""
      tasknet T {
        end = 1000;
        taskdef work { start_range [10, 20]; duration_range [5, 5]; }
        task w : work {}
      }
    """)
    assert b['w'] == (10, 20, 15, 25, 5, 5)


# ---------------------------------------------------------------------------
# Bug 1: `after` with no gap is a one-sided (lower) bound only
# ---------------------------------------------------------------------------

def test_after_no_gap_lower_bound_only():
    """`after A` means start >= A.end — NO upper bound on the successor's start."""
    tn, b = _bounds("""
      tasknet T {
        end = 1000;
        taskdef first  { start_range [0, 100]; duration_range [10, 20]; }
        taskdef second { after first; duration_range [10, 20]; }
        task f : first {}
        task s : second {}
      }
    """)
    # f.end in [10, 120]. s.start_min = 10; s.start_max must NOT be pinned to 120.
    assert b['f'] == (0, 100, 10, 120, 10, 20)
    assert b['s'][0] == 10, "successor start_min = predecessor earliest end"
    assert b['s'][1] > 120, "after-with-no-gap must not pin an upper bound on start"


def test_after_with_gap_pins_both_sides():
    """`after A [g0, g1]` constrains start on both sides."""
    tn, b = _bounds("""
      tasknet T {
        end = 1000;
        taskdef first  { start_range [0, 0]; duration_range [10, 10]; }
        taskdef second { after first [5, 8]; duration_range [1, 1]; }
        task f : first {}
        task s : second {}
      }
    """)
    # f.end = 10 exactly; s.start in [10+5, 10+8] = [15, 18].
    assert b['s'][0] == 15
    assert b['s'][1] == 18


# ---------------------------------------------------------------------------
# Bug 2: `containedin` with no offsets is containment, not equality
# ---------------------------------------------------------------------------

def test_containedin_no_offsets_is_containment():
    """`containedin A` means A.start<=child.start AND child.end<=A.end (not ==)."""
    tn, b = _bounds("""
      tasknet T {
        end = 1000;
        taskdef parent { start_range [0, 0]; duration_range [500, 500]; }
        taskdef child  { containedin parent; duration_range [10, 10]; }
        task p : parent {}
        task c : child {}
      }
    """)
    # parent spans [0, 500]. A 10-long child may sit anywhere inside:
    #   start in [0, 490], end in [10, 500].  (NOT forced to 0 / 500)
    assert b['c'][0] == 0 and b['c'][1] == 490
    assert b['c'][2] == 10 and b['c'][3] == 500


def test_containedin_with_offsets_pins_sides():
    # No child duration constraint, so the start/end offset windows aren't
    # further narrowed by end = start + duration coupling.
    tn, b = _bounds("""
      tasknet T {
        end = 1000;
        taskdef parent { start_range [0, 0]; duration_range [500, 500]; }
        taskdef child  { containedin parent [5, 10] [5, 10]; }
        task p : parent {}
        task c : child {}
      }
    """)
    # start in [parent.start+5, parent.start+10] = [5, 10]
    # end   in [parent.end-10, parent.end-5]     = [490, 495]
    assert b['c'][0] == 5 and b['c'][1] == 10
    assert b['c'][2] == 490 and b['c'][3] == 495


def test_containedin_offsets_incompatible_with_duration_is_infeasible():
    """Offsets demanding a wide span but a tiny duration => empty window."""
    tn, b = _bounds("""
      tasknet T {
        end = 1000;
        taskdef parent { start_range [0, 0]; duration_range [500, 500]; }
        taskdef child  { containedin parent [5, 10] [5, 10]; duration_range [1, 1]; }
        task p : parent {}
        task c : child {}
      }
    """)
    # start forced near ~7 but end forced near ~492 with only 1 unit of duration.
    assert b['c'][0] > b['c'][1], "should be infeasible via duration back-coupling"


# ---------------------------------------------------------------------------
# Infeasibility detection
# ---------------------------------------------------------------------------

def test_over_constrained_window_is_infeasible():
    """A task pinned early but forced after a late task has an empty window."""
    tn, b = _bounds("""
      tasknet T {
        end = 1000;
        taskdef early { start_range [0, 10]; duration_range [5, 5]; }
        taskdef late  { start_range [900, 950]; duration_range [5, 5]; }
        task l : late {}
        task bad : early { after l; }
      }
    """)
    sm, sM = b['bad'][0], b['bad'][1]
    assert sm > sM, "bad must be flagged infeasible (start_min > start_max)"


def test_feasible_tasks_not_flagged():
    tn, b = _bounds("""
      tasknet T {
        end = 1000;
        task a { start_range [0, 100]; duration_range [10, 10]; }
      }
    """)
    sm, sM, em, eM, _, _ = b['a']
    assert sm <= sM and em <= eM


# ---------------------------------------------------------------------------
# Transitive propagation
# ---------------------------------------------------------------------------

def test_transitive_after_chain():
    """a -> b -> c chains should accumulate the gap through the chain."""
    tn, b = _bounds("""
      tasknet T {
        end = 10000;
        taskdef ta { start_range [0, 0]; duration_range [100, 100]; }
        taskdef tb { after ta [10, 10]; duration_range [100, 100]; }
        taskdef tc { after tb [10, 10]; duration_range [100, 100]; }
        task a : ta {}
        task b : tb {}
        task c : tc {}
      }
    """)
    # a.end = 100; b.start_min = 110, b.end_min = 210; c.start_min = 220.
    assert b['a'][2] == 100
    assert b['b'][0] == 110
    assert b['c'][0] == 220


# ---------------------------------------------------------------------------
# End-to-end rendering
# ---------------------------------------------------------------------------

def test_render_png(tmp_path):
    tn = parse_tasknet("""
      tasknet T {
        end = 1000;
        taskdef work { start_range [10, 20]; duration_range [5, 5]; }
        task w : work {}
        task free {}
      }
    """)
    tn, _ = apply_transforms(tn)
    out = tmp_path / "temporal.png"
    ok = create_temporal_range_visualization(tn, str(out))
    assert ok is True
    assert out.exists() and out.stat().st_size > 0


def test_render_infeasible_png(tmp_path):
    """Rendering must not crash when a task's window is infeasible."""
    tn = parse_tasknet("""
      tasknet T {
        end = 1000;
        taskdef early { start_range [0, 10]; duration_range [5, 5]; }
        taskdef late  { start_range [900, 950]; duration_range [5, 5]; }
        task l : late {}
        task bad : early { after l; }
      }
    """)
    tn, _ = apply_transforms(tn)
    out = tmp_path / "temporal.png"
    ok = create_temporal_range_visualization(tn, str(out))
    assert ok is True
    assert out.exists() and out.stat().st_size > 0
