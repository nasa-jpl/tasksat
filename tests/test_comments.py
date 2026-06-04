"""Test that both # and // comment styles work."""

import sys
import os

# Add src/smt to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "smt"))

from tasknet_parser import parse_tasknet


def test_hash_comments():
    """Test traditional # comments."""
    tasknet_text = """
    tasknet Test {
        end = 100;  # This is a comment

        # Another comment
        timelines {
            battery : rate [0.0, 100.0] bounds [0.0, 100.0] = 50.0 initial_rate = 0.0;  # inline comment
        }

        task t1 {
            duration 10;
        }
    }
    """
    tn = parse_tasknet(tasknet_text)
    assert tn.id == "Test"
    assert tn.endTime == 100
    assert len(tn.timelines) == 1
    assert len(tn.tasks) == 1


def test_double_slash_comments():
    """Test C-style // comments."""
    tasknet_text = """
    tasknet Test {
        end = 100;  // This is a comment

        // Another comment
        timelines {
            battery : rate [0.0, 100.0] bounds [0.0, 100.0] = 50.0 initial_rate = 0.0;  // inline comment
        }

        task t1 {
            duration 10;
        }
    }
    """
    tn = parse_tasknet(tasknet_text)
    assert tn.id == "Test"
    assert tn.endTime == 100
    assert len(tn.timelines) == 1
    assert len(tn.tasks) == 1


def test_mixed_comments():
    """Test mixing both comment styles."""
    tasknet_text = """
    tasknet Test {
        end = 100;  # Hash comment

        // Double slash comment
        timelines {
            battery : rate [0.0, 100.0] bounds [0.0, 100.0] = 50.0 initial_rate = 0.0;
            # Another hash comment
        }

        // C-style comment
        task t1 {
            duration 10;  # inline hash
        }

        task t2 {
            duration 20;  // inline slash
        }
    }
    """
    tn = parse_tasknet(tasknet_text)
    assert tn.id == "Test"
    assert tn.endTime == 100
    assert len(tn.timelines) == 1
    assert len(tn.tasks) == 2


if __name__ == "__main__":
    test_hash_comments()
    print("✓ Hash comments work")

    test_double_slash_comments()
    print("✓ Double slash comments work")

    test_mixed_comments()
    print("✓ Mixed comments work")

    print("\nAll comment tests passed!")
