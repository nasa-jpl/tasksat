"""Merging a task instance with its taskdef.

`TaskNetSMT._merge_task_with_definition` combines the two. Every field is "instance wins
if present" except impacts and dependencies, and both exceptions had bugs:

  * impacts were CONCATENATED, so an instance repeating one of its definition's impacts
    applied it twice. Auto-instantiation copies the definition's impacts onto every
    instance it creates, so `maint T += 1` became `+= 2` — overflowing an atomic
    timeline's [0,1] capacity and reporting UNSAT on a satisfiable plan.
  * dependencies were taken from ONE side each, so a type-level dependency written on an
    instance (`task pt : PT { after PH; }`) was silently discarded. The helper task was
    still auto-created; nothing then depended on it.
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src' / 'smt'))

from tasknet_parser import parse_tasknet          # noqa: E402
from tasknet_transforms import apply_transforms   # noqa: E402
from tasknet_smt import TaskNetTL                 # noqa: E402
from tasknet_ast import TaskKind                  # noqa: E402


def encode(src: str):
    tn = apply_transforms(parse_tasknet(src))[0]
    return TaskNetTL(tn, error_trace=False, use_optimization=False)


def net(body: str, timelines: str = "heat : atomic = 0;") -> str:
    return f"tasknet T {{\n  end = 10000;\n  timelines {{ {timelines} }}\n  {body}\n}}\n"


class TestImpactsAreNotDoubled:

    def test_instance_repeating_an_impact_applies_it_once(self):
        """The instance body repeats exactly what the taskdef says. `heat` is atomic, so
        applying it twice would take the value to 2 and break the [0,1] capacity."""
        enc = encode(net(
            "taskdef A { duration_range [10, 10]; impacts { maint { heat += 1; } } }\n"
            "  task a : A { impacts { maint { heat += 1; } } }"))
        a = next(t for t in enc.tn.tasks if t.id == 'a')
        assert len(a.impacts) == 1
        assert enc.solver.check().r == 1        # sat

    def test_a_genuinely_different_impact_still_applies(self):
        """Dedup must compare (timeline, when, how) structurally, not just the timeline:
        two different values on one timeline are two impacts."""
        enc = encode(net(
            "taskdef A { duration_range [10, 10]; impacts { maint { n += 1; } } }\n"
            "  task a : A { impacts { post { n += 5; } } }",
            timelines="n : cumulative [0, 100] = 0;"))
        a = next(t for t in enc.tn.tasks if t.id == 'a')
        assert len(a.impacts) == 2

    def test_the_preheat_maintainheat_pattern_is_satisfiable(self):
        """THE case this was found on. Two helpers both claiming one atomic resource, with
        the primary task after one and inside the other. A valid schedule exists — the
        helpers need not overlap — and the doubled impact made it UNSAT."""
        pattern = (
            "taskdef PH { duration_range [1, 200];  pre { heat = 0; }"
            " impacts { maint { heat += 1; } } }\n"
            "  taskdef MH { duration_range [1, 5000]; pre { heat = 0; }"
            " impacts { maint { heat += 1; } } }\n")
        auto = encode(net(pattern +
            "  taskdef PT { duration_range [60, 690]; after PH; containedin MH; }\n"
            "  task pt : PT { }"))
        explicit = encode(net(pattern +
            "  taskdef PT { duration_range [60, 690]; }\n"
            "  task ph : PH { }\n  task mh : MH { }\n"
            "  task pt : PT { after ph; containedin mh; }"))
        # Same problem written two ways: both must be satisfiable.
        assert str(auto.solver.check()) == 'sat'
        assert str(explicit.solver.check()) == 'sat'


class TestDependenciesSurviveTheMerge:

    @pytest.mark.parametrize("kind,dep", [("after", "after PH;"),
                                          ("containedin", "containedin PH;")])
    def test_type_level_dependency_on_an_instance_is_kept(self, kind, dep):
        """`task pt : PT { after PH; }` — PH is a taskdef, so this is a type-level
        dependency written on an instance. It used to be dropped by the merge while
        auto-instantiation still created PH_auto_0, leaving an unconstrained helper."""
        enc = encode(net(
            "taskdef PH { duration_range [5, 900]; }\n"
            "  taskdef PT { duration_range [10, 10]; }\n"
            f"  task pt : PT {{ {dep} }}"))
        pt = next(t for t in enc.tn.tasks if t.id == 'pt')
        got = pt.after_definitions if kind == "after" else pt.containedin_definitions
        assert [getattr(d, 'task_id', d) for d in (got or [])] == ['PH']
        assert any(f'dependency_{kind}' in str(a) for a in enc.solver.assertions())

    def test_taskdef_and_instance_dependencies_are_unioned(self):
        """A dependency on each side: both must survive, and the auto helper must exist."""
        enc = encode(net(
            "taskdef PH { duration_range [5, 5]; }\n"
            "  taskdef X  { duration_range [5, 5]; }\n"
            "  taskdef PT { duration_range [10, 10]; after PH; }\n"
            "  task x : X { }\n"
            "  task pt : PT { after x; }"))
        pt = next(t for t in enc.tn.tasks if t.id == 'pt')
        assert [getattr(d, 'task_id', d) for d in (pt.after_definitions or [])] == ['PH']
        assert [getattr(d, 'task_id', d) for d in (pt.after_instances or [])] == ['x']
        assert any(t.id == 'PH_auto_0' for t in enc.tn.tasks)

    def test_a_duplicated_dependency_counts_once(self):
        """An auto instance's body repeats its definition's dependencies, for the same
        reason it repeats its impacts."""
        enc = encode(net(
            "taskdef PH { duration_range [5, 5]; }\n"
            "  taskdef PT { duration_range [10, 10]; after PH; }\n"
            "  task pt : PT { after PH; }"))
        pt = next(t for t in enc.tn.tasks if t.id == 'pt')
        assert [getattr(d, 'task_id', d) for d in (pt.after_definitions or [])] == ['PH']


class TestOtherFieldsStillOverride:

    def test_instance_wins_for_pre_inv_duration_priority(self):
        enc = encode(net(
            "taskdef A { duration_range [10, 10]; priority 5; pre { heat = 0; }"
            " inv { heat = 0; } }\n"
            "  task a : A { duration_range [20, 20]; priority 9; }"))
        a = next(t for t in enc.tn.tasks if t.id == 'a')
        assert (int(a.durrng.low), int(a.durrng.high)) == (20, 20)
        assert a.priority == 9
        assert [c.id for c in (a.pre or [])] == ['heat']     # inherited, not dropped
