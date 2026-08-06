"""Test session sugar: nested `task` declarations inside a taskdef, flattened
into qualified instances by flatten_sessions() (Phase 1 of compositional scaling).
"""

import sys
import os

# Add src/smt to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "smt"))

from tasknet_parser import parse_tasknet
from tasknet_transforms import apply_transforms
from tasknet_printer import print_tasknet_to_string
from tasknet_ast import TaskKind


SESSION_SPEC = """
tasknet Rover {
    end = 1000;

    timelines {
        battery     : rate [10.0, 100.0] bounds [0.0, 100.0] = 60.0;
        temperature : rate [5.0, 40.0]  bounds [0.0, 100.0] = 30.0;
    }

    taskdef PreHeat {
        duration_range [30, 40];
        impacts { maint { temperature +~ 1.0; } }
    }
    taskdef Drive {
        duration_range [60, 80];
        pre { temperature in [25.0, 40.0]; }
        impacts { maint { battery -~ 1.0; } }
    }

    taskdef DriveSession {
        task preheat : PreHeat;
        task drive   : Drive { after preheat; }
    }

    task drive1 : DriveSession;
    task drive2 : DriveSession { after drive1; }
}
"""


def _by_id(tn):
    return {t.id: t for t in tn.tasks}


def test_nested_tasks_parse_into_children():
    """A taskdef with nested `task` declarations exposes them as `children`."""
    tn = parse_tasknet(SESSION_SPEC)
    session = _by_id(tn)["DriveSession"]
    assert session.kind == TaskKind.DEFINITION
    assert [c.id for c in session.children] == ["preheat", "drive"]
    # Children carry their own taskdef reference and sibling dependency.
    preheat, drive = session.children
    assert preheat.definition == "PreHeat"
    assert drive.definition == "Drive"
    assert [d.task_id for d in (drive.after_instances or [])] == ["preheat"]


def test_flatten_replaces_sessions_with_qualified_instances():
    """flatten_sessions drops the session taskdef and its instances, emitting
    one qualified child instance each."""
    tn = parse_tasknet(SESSION_SPEC)
    tn, occurred = apply_transforms(tn)
    assert occurred is True  # structural rewrite happened

    ids = {t.id for t in tn.tasks}
    # Session taskdef is gone; the child taskdefs remain as definitions.
    assert "DriveSession" not in ids
    assert "drive1" not in ids and "drive2" not in ids
    # Six qualified instances.
    for q in ["drive1__preheat", "drive1__drive", "drive2__preheat", "drive2__drive"]:
        assert q in ids
    # PreHeat/Drive survive as definitions (manual instances suppress auto-inst).
    tasks = _by_id(tn)
    assert tasks["PreHeat"].kind == TaskKind.DEFINITION
    assert tasks["Drive"].kind == TaskKind.DEFINITION


def test_sibling_dependency_is_qualified():
    """A child's bare sibling reference is rewritten to the qualified sibling."""
    tn = parse_tasknet(SESSION_SPEC)
    tn, _ = apply_transforms(tn)
    tasks = _by_id(tn)
    d1_drive = tasks["drive1__drive"]
    after = {d.task_id for d in (d1_drive.after_instances or [])}
    assert "drive1__preheat" in after
    # It must NOT point at the bare sibling name or the other session's child.
    assert "preheat" not in after
    assert "drive2__preheat" not in after


def test_session_dependency_fans_out_to_all_children():
    """`drive2 after drive1` (session→session) fans out onto every drive1 child
    for every drive2 child (conservative 'after the whole predecessor session')."""
    tn = parse_tasknet(SESSION_SPEC)
    tn, _ = apply_transforms(tn)
    tasks = _by_id(tn)

    d2_preheat_after = {d.task_id for d in (tasks["drive2__preheat"].after_instances or [])}
    assert d2_preheat_after == {"drive1__preheat", "drive1__drive"}

    d2_drive_after = {d.task_id for d in (tasks["drive2__drive"].after_instances or [])}
    # Its own sibling plus the whole predecessor session.
    assert d2_drive_after == {"drive2__preheat", "drive1__preheat", "drive1__drive"}


def test_children_round_trip_through_printer():
    """Printing a pre-flatten AST emits the nested tasks so they re-parse."""
    tn = parse_tasknet(SESSION_SPEC)
    printed = print_tasknet_to_string(tn)
    assert "taskdef DriveSession {" in printed
    assert "task preheat : PreHeat" in printed
    tn2 = parse_tasknet(printed)
    session = _by_id(tn2)["DriveSession"]
    assert [c.id for c in session.children] == ["preheat", "drive"]


def test_no_sessions_is_noop():
    """A network with no nested tasks is unaffected by flattening."""
    spec = """
    tasknet Flat {
        end = 100;
        timelines { battery : rate [0.0, 100.0] bounds [0.0, 100.0] = 50.0; }
        task a { duration 10; }
        task b { duration 10; after a; }
    }
    """
    tn = parse_tasknet(spec)
    tn, occurred = apply_transforms(tn)
    assert occurred is False
    assert {t.id for t in tn.tasks} == {"a", "b"}


def test_flatten_reported_even_when_task_count_unchanged():
    """Regression: with ONE session instance of a TWO-child session, flattening
    removes 2 tasks (the session taskdef + its instance) and adds 2 (the two
    qualified children), leaving len(tn.tasks) unchanged. The rewrite must still
    be reported (occurred=True) — a count-delta heuristic would miss it and
    --transform-only would decline to write the inspection file (the tasknet59
    symptom). Guards flatten_sessions' structural changed flag."""
    spec = """
    tasknet TwoChildOneInstance {
        end = 100;
        timelines { location : state(home, target) = home; }
        taskdef PreHeat { duration_range [5, 10]; }
        taskdef Drive   { duration_range [10, 20]; }
        taskdef DriveSession {
            task preheat : PreHeat;
            task drive   : Drive { after preheat; }
        }
        task d1 : DriveSession;
    }
    """
    tn = parse_tasknet(spec)
    # Before flatten: PreHeat, Drive, DriveSession, d1 = 4 tasks.
    count_before = len(tn.tasks)
    assert count_before == 4
    tn, occurred = apply_transforms(tn)
    # After flatten: PreHeat, Drive, d1__preheat, d1__drive = 4 tasks (unchanged!).
    assert len(tn.tasks) == count_before  # the count trap
    assert occurred is True               # ...yet the rewrite is reported
    ids = {t.id for t in tn.tasks}
    assert "DriveSession" not in ids and "d1" not in ids
    assert "d1__preheat" in ids and "d1__drive" in ids
