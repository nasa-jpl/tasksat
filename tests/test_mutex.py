"""Test the mutex construct."""

import sys
import os

# Add src/smt to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "smt"))

from tasknet_parser import parse_tasknet
from tasknet_transforms import apply_transforms
from tasknet_ast import TLMutex, TLAnd, TLOr, TLTimeCmp


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
