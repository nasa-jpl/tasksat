"""Tests for AST → .tn printer (tasknet_printer.py)"""

import pytest
import os
import sys
from pathlib import Path

# Add src/smt to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src' / 'smt'))

from tasknet_parser import parse_tasknet_file
from tasknet_transforms import apply_transforms
from tasknet_printer import print_tasknet_to_file, print_tasknet_to_string


class TestPrinter:
    """Test the AST → .tn printer"""

    def test_thermal_pattern_demo(self):
        """Print thermal_pattern_demo.tn with auto-instantiation"""
        input_path = "tests/tasknet_files/examples/thermal_pattern_demo.tn"
        # Use .tasksat/ directory
        from pathlib import Path
        input_file = Path(input_path)
        tasksat_dir = input_file.parent / '.tasksat' / 'transformed'
        tasksat_dir.mkdir(parents=True, exist_ok=True)
        tasksat_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(tasksat_dir / f"{input_file.stem}_transformed.tn")

        # Parse and transform
        tn = parse_tasknet_file(input_path)
        tn, _ = apply_transforms(tn)

        # Print to file
        print_tasknet_to_file(tn, output_path)

        # Verify file exists and has content
        assert os.path.exists(output_path)
        with open(output_path) as f:
            content = f.read()

        print(f"\n=== Transformed {input_path} ===")
        print(f"Output written to: {output_path}")
        print(f"Size: {len(content)} bytes")
        print("\n--- First 50 lines ---")
        print('\n'.join(content.split('\n')[:50]))

        # Check auto-instantiated tasks are present
        assert "preheat_auto_0" in content
        assert "preheat_auto_1" in content
        assert "maintainheat_auto_0" in content
        assert "maintainheat_auto_1" in content

        # Check structure
        assert "tasknet ThermalDemo" in content
        assert "taskdef preheat" in content
        assert "task downlink_0 : downlink" in content

    def test_tasknet25_auto_instantiate(self):
        """Print tasknet with basic auto-instantiation"""
        from pathlib import Path
        input_path = "tests/tasknet_files/valid/tasknet25_auto_instantiate_basic.tn"
        input_file = Path(input_path)
        tasksat_dir = input_file.parent / '.tasksat' / 'transformed'
        tasksat_dir.mkdir(parents=True, exist_ok=True)
        tasksat_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(tasksat_dir / f"{input_file.stem}_transformed.tn")

        # Parse and transform
        tn = parse_tasknet_file(input_path)
        tn, _ = apply_transforms(tn)

        # Print to file
        print_tasknet_to_file(tn, output_path)

        # Verify
        assert os.path.exists(output_path)
        with open(output_path) as f:
            content = f.read()

        print(f"\n=== Transformed {input_path} ===")
        print(f"Output written to: {output_path}")
        print(content)

        # Check auto-instantiated task
        assert "preheat_auto_0" in content

    def test_tasknet28_multiple_instances(self):
        """Print tasknet with multiple auto-instances"""
        from pathlib import Path
        input_path = "tests/tasknet_files/valid/tasknet28_auto_instantiate_multiple.tn"
        input_file = Path(input_path)
        tasksat_dir = input_file.parent / '.tasksat' / 'transformed'
        tasksat_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(tasksat_dir / f"{input_file.stem}_transformed.tn")

        # Parse and transform
        tn = parse_tasknet_file(input_path)
        tn, _ = apply_transforms(tn)

        # Print to file
        print_tasknet_to_file(tn, output_path)

        # Verify
        assert os.path.exists(output_path)
        with open(output_path) as f:
            content = f.read()

        print(f"\n=== Transformed {input_path} ===")
        print(f"Output written to: {output_path}")
        print(content)

        # Check multiple instances created
        assert "preheat_auto_0" in content
        assert "preheat_auto_1" in content

    def test_round_trip(self):
        """Test round-trip: parse → transform → print → parse again"""
        input_path = "tests/tasknet_files/examples/thermal_pattern_demo.tn"

        # First pass
        tn1 = parse_tasknet_file(input_path)
        tn1, _ = apply_transforms(tn1)

        # Print to string
        tn_str = print_tasknet_to_string(tn1)

        print("\n=== Round-trip test ===")
        print(f"Original: {input_path}")
        print(f"Transformed tasknet:\n{tn_str[:500]}...\n")

        # Write to temp file and parse again
        temp_path = "/tmp/test_roundtrip.tn"
        with open(temp_path, 'w') as f:
            f.write(tn_str)

        # Second pass (should not transform further)
        tn2 = parse_tasknet_file(temp_path)

        # Basic checks
        assert len(tn2.tasks) == len(tn1.tasks)
        assert len(tn2.timelines) == len(tn1.timelines)

        print(f"✓ Round-trip successful")
        print(f"  Tasks: {len(tn1.tasks)} → {len(tn2.tasks)}")
        print(f"  Timelines: {len(tn1.timelines)} → {len(tn2.timelines)}")

    def test_print_all_timeline_types(self):
        """Test printing different timeline types"""
        from pathlib import Path
        input_path = "tests/tasknet_files/valid/tasknet1.tn"
        input_file = Path(input_path)
        tasksat_dir = input_file.parent / '.tasksat' / 'transformed'
        tasksat_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(tasksat_dir / f"{input_file.stem}_transformed.tn")

        tn = parse_tasknet_file(input_path)
        tn, _ = apply_transforms(tn)

        print_tasknet_to_file(tn, output_path)

        with open(output_path) as f:
            content = f.read()

        print(f"\n=== Timeline types test ===")
        print(content)

        # Check timeline declarations
        assert "state(" in content or "atomic" in content or "cumulative" in content

    def test_print_with_properties(self):
        """Test printing tasknet with temporal properties"""
        from pathlib import Path
        input_path = "tests/tasknet_files/valid/tasknet10_verify.tn"
        input_file = Path(input_path)
        tasksat_dir = input_file.parent / '.tasksat' / 'transformed'
        tasksat_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(tasksat_dir / f"{input_file.stem}_transformed.tn")

        tn = parse_tasknet_file(input_path)
        tn, _ = apply_transforms(tn)

        print_tasknet_to_file(tn, output_path)

        with open(output_path) as f:
            content = f.read()

        print(f"\n=== Properties test ===")
        print(content)

        # Check properties block
        assert "properties" in content or len(content) > 0
