"""Test the mutex construct."""

import sys
import os

# Add src/smt to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "smt"))

import pytest

from tasknet_parser import parse_tasknet
from tasknet_transforms import apply_transforms
from tasknet_ast import TLMutex, TLAnd, TLOr, TLTimeCmp
from tasknet_smt import TaskNetTL

# Directory holding the numbered end-to-end .tn fixtures
VALID_DIR = os.path.join(os.path.dirname(__file__), "tasknet_files", "valid")


def _overlaps(smt, model, x, y):
    """True if task instances x and y overlap in the solved schedule."""
    xs = model.eval(smt.start_vars[x]).as_long()
    xe = model.eval(smt.end_vars[x]).as_long()
    ys = model.eval(smt.start_vars[y]).as_long()
    ye = model.eval(smt.end_vars[y]).as_long()
    return xs < ye and ys < xe


def _mutex_pairs(formula):
    """Extract the set of excluded task-name pairs from a desugared mutex formula.

    Each non-overlap pair is an OR of two TLTimeCmp boundary comparisons; the two
    task names identify the pair. Returns a set of frozensets.
    """
    if isinstance(formula, TLOr) and isinstance(formula.left, TLTimeCmp):
        return {frozenset((formula.left.left.task, formula.left.right.task))}
    if isinstance(formula, (TLAnd, TLOr)):
        return _mutex_pairs(formula.left) | _mutex_pairs(formula.right)
    return set()


def test_mutex_parsing_within_group():
    """Test that mutex syntax parses correctly for within-group exclusion."""
    tasknet_text = """
    tasknet Test {
        end = 100;

        task t1 {
            duration 10;
        }

        task t2 {
            duration 10;
        }

        task t3 {
            duration 10;
        }

        constraints {
            prop exclusive: mutex [t1, t2, t3];
        }
    }
    """
    tn = parse_tasknet(tasknet_text)
    assert tn.id == "Test"
    assert len(tn.constraints) == 1

    # Check that it parsed as a TLMutex
    formula = tn.constraints[0].formula
    assert isinstance(formula, TLMutex)
    assert formula.group_a == ["t1", "t2", "t3"]
    assert formula.group_b is None


def test_mutex_parsing_between_groups():
    """Test that mutex syntax parses correctly for between-group exclusion."""
    tasknet_text = """
    tasknet Test {
        end = 100;

        task a1 {
            duration 10;
        }

        task a2 {
            duration 10;
        }

        task b1 {
            duration 10;
        }

        task b2 {
            duration 10;
        }

        constraints {
            prop exclusive: mutex [a1, a2] with [b1, b2];
        }
    }
    """
    tn = parse_tasknet(tasknet_text)
    assert tn.id == "Test"
    assert len(tn.constraints) == 1

    # Check that it parsed as a TLMutex with both groups
    formula = tn.constraints[0].formula
    assert isinstance(formula, TLMutex)
    assert formula.group_a == ["a1", "a2"]
    assert formula.group_b == ["b1", "b2"]


def test_mutex_desugaring_two_tasks():
    """Test that mutex [A, B] desugars to (A.end <= B.start) or (B.end <= A.start)."""
    tasknet_text = """
    tasknet Test {
        end = 100;

        task t1 {
            duration 10;
        }

        task t2 {
            duration 10;
        }

        constraints {
            prop exclusive: mutex [t1, t2];
        }
    }
    """
    tn = parse_tasknet(tasknet_text)

    # Apply transformations
    tn, _ = apply_transforms(tn)

    # After desugaring, should be a single OR of two time comparisons
    formula = tn.constraints[0].formula
    assert isinstance(formula, TLOr)

    # Check left side: t1.end <= t2.start
    left = formula.left
    assert isinstance(left, TLTimeCmp)
    assert left.left.task == "t1"
    assert left.left.boundary == "end"
    assert left.op == "<="
    assert left.right.task == "t2"
    assert left.right.boundary == "start"

    # Check right side: t2.end <= t1.start
    right = formula.right
    assert isinstance(right, TLTimeCmp)
    assert right.left.task == "t2"
    assert right.left.boundary == "end"
    assert right.op == "<="
    assert right.right.task == "t1"
    assert right.right.boundary == "start"


def test_mutex_desugaring_three_tasks():
    """Test that mutex [A, B, C] desugars to all pairwise non-overlaps."""
    tasknet_text = """
    tasknet Test {
        end = 100;

        task t1 {
            duration 10;
        }

        task t2 {
            duration 10;
        }

        task t3 {
            duration 10;
        }

        constraints {
            prop exclusive: mutex [t1, t2, t3];
        }
    }
    """
    tn = parse_tasknet(tasknet_text)
    tn, _ = apply_transforms(tn)

    # After desugaring, should be AND of 3 non-overlap conditions
    # Structure: ((t1,t2) AND (t1,t3)) AND (t2,t3)
    formula = tn.constraints[0].formula
    assert isinstance(formula, TLAnd)

    # Each non-overlap is an OR of two comparisons
    # Left should be another AND
    assert isinstance(formula.left, TLAnd)
    assert isinstance(formula.left.left, TLOr)   # t1 vs t2
    assert isinstance(formula.left.right, TLOr)  # t1 vs t3

    # Right should be an OR
    assert isinstance(formula.right, TLOr)  # t2 vs t3


def test_mutex_desugaring_between_groups():
    """Test that mutex [A, B] with [C, D] desugars to cross-product."""
    tasknet_text = """
    tasknet Test {
        end = 100;

        task a1 {
            duration 10;
        }

        task a2 {
            duration 10;
        }

        task b1 {
            duration 10;
        }

        task b2 {
            duration 10;
        }

        constraints {
            prop exclusive: mutex [a1, a2] with [b1, b2];
        }
    }
    """
    tn = parse_tasknet(tasknet_text)
    tn, _ = apply_transforms(tn)

    # After desugaring, should be AND of 4 non-overlap conditions
    # (a1,b1), (a1,b2), (a2,b1), (a2,b2)
    formula = tn.constraints[0].formula
    assert isinstance(formula, TLAnd)

    # All leaves should be OR of time comparisons
    def count_or_nodes(f):
        if isinstance(f, TLOr):
            return 1
        elif isinstance(f, TLAnd):
            return count_or_nodes(f.left) + count_or_nodes(f.right)
        else:
            return 0

    # Should have 4 OR nodes (one per cross-product pair)
    assert count_or_nodes(formula) == 4


def test_mutex_in_properties():
    """Test that mutex works in properties block too."""
    tasknet_text = """
    tasknet Test {
        end = 100;

        task t1 {
            duration 10;
        }

        task t2 {
            duration 10;
        }

        properties {
            prop exclusive: mutex [t1, t2];
        }
    }
    """
    tn = parse_tasknet(tasknet_text)
    tn, _ = apply_transforms(tn)

    # Should desugar in properties too
    formula = tn.properties[0].formula
    assert isinstance(formula, TLOr)
    assert isinstance(formula.left, TLTimeCmp)
    assert isinstance(formula.right, TLTimeCmp)


def test_mutex_unnamed():
    """Test that unnamed mutex constraints work with auto-generated names."""
    tasknet_text = """
    tasknet Test {
        end = 100;

        task t1 {
            duration 10;
        }

        task t2 {
            duration 10;
        }

        task t3 {
            duration 10;
        }

        constraints {
            mutex [t1, t2];
            mutex [t2, t3];
        }
    }
    """
    tn = parse_tasknet(tasknet_text)

    # Should parse as unnamed constraints with auto-generated names
    assert len(tn.constraints) == 2
    assert tn.constraints[0].name == "mutex_t1_t2"
    assert isinstance(tn.constraints[0].formula, TLMutex)
    assert tn.constraints[1].name == "mutex_t2_t3"
    assert isinstance(tn.constraints[1].formula, TLMutex)

    # Should still desugar correctly
    tn, _ = apply_transforms(tn)
    assert isinstance(tn.constraints[0].formula, TLOr)
    assert isinstance(tn.constraints[1].formula, TLOr)


def test_mutex_parsing_cross_keyword():
    """Test that `mutex cross [...]` parses with cross_only=True."""
    tn = parse_tasknet("""
    tasknet Test {
        end = 100;
        task t1 { duration 10; }
        task t2 { duration 10; }
        constraints { prop m: mutex cross [t1, t2]; }
    }
    """)
    formula = tn.constraints[0].formula
    assert isinstance(formula, TLMutex)
    assert formula.group_a == ["t1", "t2"]
    assert formula.group_b is None
    assert formula.cross_only is True


def test_mutex_cross_unnamed_naming():
    """Unnamed `mutex cross` gets a distinct auto-name."""
    tn = parse_tasknet("""
    tasknet Test {
        end = 100;
        task t1 { duration 10; }
        task t2 { duration 10; }
        constraints { mutex cross [t1, t2]; }
    }
    """)
    assert tn.constraints[0].name == "mutex_cross_t1_t2"


def test_mutex_cross_on_instances_equals_plain():
    """For plain instances, `mutex cross [t1, t2]` == `mutex [t1, t2]`."""
    tn = parse_tasknet("""
    tasknet Test {
        end = 100;
        task t1 { duration 10; }
        task t2 { duration 10; }
        constraints { prop m: mutex cross [t1, t2]; }
    }
    """)
    tn, _ = apply_transforms(tn)
    assert _mutex_pairs(tn.constraints[0].formula) == {frozenset(("t1", "t2"))}


_TASKDEF_NET = """
tasknet Test {{
    end = 100;
    taskdef A {{ duration 10; }}
    taskdef B {{ duration 10; }}
    task a0 : A {{}}
    task a1 : A {{}}
    task b0 : B {{}}
    task b1 : B {{}}
    constraints {{ prop m: {constraint}; }}
}}
"""


def test_mutex_taskdef_default_flattens_all_pairs():
    """`mutex [A, B]` on taskdefs excludes EVERY pair, including same-taskdef pairs."""
    tn = parse_tasknet(_TASKDEF_NET.format(constraint="mutex [A, B]"))
    tn, _ = apply_transforms(tn)
    pairs = _mutex_pairs(tn.constraints[0].formula)
    assert pairs == {
        frozenset(("a0", "a1")),
        frozenset(("b0", "b1")),
        frozenset(("a0", "b0")),
        frozenset(("a0", "b1")),
        frozenset(("a1", "b0")),
        frozenset(("a1", "b1")),
    }


def test_mutex_taskdef_cross_excludes_only_cross_pairs():
    """`mutex cross [A, B]` excludes only cross-operand pairs; same-taskdef allowed."""
    tn = parse_tasknet(_TASKDEF_NET.format(constraint="mutex cross [A, B]"))
    tn, _ = apply_transforms(tn)
    pairs = _mutex_pairs(tn.constraints[0].formula)
    assert pairs == {
        frozenset(("a0", "b0")),
        frozenset(("a0", "b1")),
        frozenset(("a1", "b0")),
        frozenset(("a1", "b1")),
    }
    assert frozenset(("a0", "a1")) not in pairs
    assert frozenset(("b0", "b1")) not in pairs


def test_mutex_taskdef_with_cross_product():
    """`mutex [A] with [B]` is the cross-product of the two flattened groups."""
    tn = parse_tasknet(_TASKDEF_NET.format(constraint="mutex [A] with [B]"))
    tn, _ = apply_transforms(tn)
    pairs = _mutex_pairs(tn.constraints[0].formula)
    assert pairs == {
        frozenset(("a0", "b0")),
        frozenset(("a0", "b1")),
        frozenset(("a1", "b0")),
        frozenset(("a1", "b1")),
    }


def test_mutex_taskdef_single_taskdef():
    """`mutex [A]` means no two instances of taskdef A overlap."""
    tn = parse_tasknet(_TASKDEF_NET.format(constraint="mutex [A]"))
    tn, _ = apply_transforms(tn)
    assert _mutex_pairs(tn.constraints[0].formula) == {frozenset(("a0", "a1"))}


def test_mutex_mixed_taskdef_and_instance():
    """Taskdef and instance operands can be mixed in one group."""
    tn = parse_tasknet(_TASKDEF_NET.format(constraint="mutex [A, b0]"))
    tn, _ = apply_transforms(tn)
    pairs = _mutex_pairs(tn.constraints[0].formula)
    assert pairs == {
        frozenset(("a0", "a1")),
        frozenset(("a0", "b0")),
        frozenset(("a1", "b0")),
    }


def test_mutex_taskdef_includes_auto_instances():
    """Taskdef operands expand to auto-instantiated instances too."""
    tn = parse_tasknet("""
    tasknet Test {
        end = 1000;
        taskdef predrive { duration 10; }
        taskdef drive { after predrive; duration 30; }
        task drive1 : drive {}
        task drive2 : drive {}
        constraints { prop m: mutex [predrive]; }
    }
    """)
    tn, _ = apply_transforms(tn)
    pairs = _mutex_pairs(tn.constraints[0].formula)
    assert pairs == {frozenset(("predrive_auto_0", "predrive_auto_1"))}


def test_mutex_taskdef_zero_instances_errors():
    """A taskdef operand with no instances raises a clear error during transform."""
    tn = parse_tasknet("""
    tasknet Test {
        end = 100;
        taskdef Empty { duration 10; }
        task other { duration 5; }
        constraints { prop m: mutex [Empty]; }
    }
    """)
    with pytest.raises(ValueError, match="taskdef 'Empty' which has no instances"):
        apply_transforms(tn)


def test_mutex_taskdef_cross_end_to_end():
    """End-to-end solve of tasknet57_mutex_taskdef.tn (mutex cross [A, B]).

    Confirms the full pipeline (parse -> transform -> SMT) produces a schedule
    where no A instance overlaps any B instance, while same-taskdef instances
    (a0/a1, b0/b1) are free to overlap.
    """
    with open(os.path.join(VALID_DIR, "tasknet57_mutex_taskdef.tn")) as f:
        tn = parse_tasknet(f.read())
    tn, _ = apply_transforms(tn)

    smt = TaskNetTL(tn, use_optimization=False)
    model, _ = smt.solve()
    assert model is not None, "cross-only mutex over taskdefs should be satisfiable"

    # No A instance may overlap any B instance.
    a_insts = ["a0", "a1"]
    b_insts = ["b0", "b1"]
    for a in a_insts:
        for b in b_insts:
            assert not _overlaps(smt, model, a, b), \
                f"{a} and {b} must not overlap under mutex cross [A, B]"


if __name__ == "__main__":
    test_mutex_parsing_within_group()
    print("✓ Mutex within-group parsing works")

    test_mutex_parsing_between_groups()
    print("✓ Mutex between-groups parsing works")

    test_mutex_desugaring_two_tasks()
    print("✓ Mutex desugaring (2 tasks) works")

    test_mutex_desugaring_three_tasks()
    print("✓ Mutex desugaring (3 tasks) works")

    test_mutex_desugaring_between_groups()
    print("✓ Mutex between-groups desugaring works")

    test_mutex_in_properties()
    print("✓ Mutex in properties works")

    test_mutex_unnamed()
    print("✓ Mutex unnamed constraints work")

    print("\nAll mutex tests passed!")
