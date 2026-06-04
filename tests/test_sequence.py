"""Test the sequence construct."""

import sys
import os

# Add src/smt to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "smt"))

from tasknet_parser import parse_tasknet
from tasknet_transforms import apply_transforms
from tasknet_ast import TLSequence, TLAnd, TLTimeCmp


def test_sequence_parsing():
    """Test that sequence syntax parses correctly."""
    tasknet_text = """
    tasknet Test {
        end = 100;

        timelines {
            battery : rate [0.0, 100.0] bounds [0.0, 100.0] = 50.0 initial_rate = 0.0;
        }

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
            prop ordering: sequence [t1, t2, t3];
        }
    }
    """
    tn = parse_tasknet(tasknet_text)
    assert tn.id == "Test"
    assert len(tn.constraints) == 1

    # Check that it parsed as a TLSequence
    formula = tn.constraints[0].formula
    assert isinstance(formula, TLSequence)
    assert formula.tasks == ["t1", "t2", "t3"]


def test_sequence_desugaring():
    """Test that sequence desugars to pairwise constraints."""
    tasknet_text = """
    tasknet Test {
        end = 100;

        timelines {
            battery : rate [0.0, 100.0] bounds [0.0, 100.0] = 50.0 initial_rate = 0.0;
        }

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
            prop ordering: sequence [t1, t2, t3];
        }
    }
    """
    tn = parse_tasknet(tasknet_text)

    # Apply transformations
    tn, _ = apply_transforms(tn)

    # After desugaring, should be AND of time comparisons
    formula = tn.constraints[0].formula
    assert isinstance(formula, TLAnd)

    # Check left side: t1.end <= t2.start
    left = formula.left
    assert isinstance(left, TLTimeCmp)
    assert left.left.task == "t1"
    assert left.left.boundary == "end"
    assert left.op == "<="
    assert left.right.task == "t2"
    assert left.right.boundary == "start"

    # Check right side: t2.end <= t3.start
    right = formula.right
    assert isinstance(right, TLTimeCmp)
    assert right.left.task == "t2"
    assert right.left.boundary == "end"
    assert right.op == "<="
    assert right.right.task == "t3"
    assert right.right.boundary == "start"


def test_sequence_with_two_tasks():
    """Test sequence with just two tasks."""
    tasknet_text = """
    tasknet Test {
        end = 100;

        timelines {
            battery : rate [0.0, 100.0] bounds [0.0, 100.0] = 50.0 initial_rate = 0.0;
        }

        task t1 {
            duration 10;
        }

        task t2 {
            duration 10;
        }

        constraints {
            prop ordering: sequence [t1, t2];
        }
    }
    """
    tn = parse_tasknet(tasknet_text)
    tn, _ = apply_transforms(tn)

    # With two tasks, should be a single TLTimeCmp (no AND needed)
    formula = tn.constraints[0].formula
    assert isinstance(formula, TLTimeCmp)
    assert formula.left.task == "t1"
    assert formula.left.boundary == "end"
    assert formula.op == "<="
    assert formula.right.task == "t2"
    assert formula.right.boundary == "start"


def test_sequence_in_properties():
    """Test that sequence works in properties block too."""
    tasknet_text = """
    tasknet Test {
        end = 100;

        timelines {
            battery : rate [0.0, 100.0] bounds [0.0, 100.0] = 50.0 initial_rate = 0.0;
        }

        task t1 {
            duration 10;
        }

        task t2 {
            duration 10;
        }

        properties {
            prop ordering: sequence [t1, t2];
        }
    }
    """
    tn = parse_tasknet(tasknet_text)
    tn, _ = apply_transforms(tn)

    # Should desugar in properties too
    formula = tn.properties[0].formula
    assert isinstance(formula, TLTimeCmp)
    assert formula.left.task == "t1"
    assert formula.right.task == "t2"


if __name__ == "__main__":
    test_sequence_parsing()
    print("✓ Sequence parsing works")

    test_sequence_desugaring()
    print("✓ Sequence desugaring works")

    test_sequence_with_two_tasks()
    print("✓ Two-task sequence works")

    test_sequence_in_properties()
    print("✓ Sequence in properties works")

    print("\nAll sequence tests passed!")
