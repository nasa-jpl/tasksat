#!/usr/bin/env python3
"""
Validate a schedule against a tasknet using Lean semantics.

Usage:
    python tools/validate_schedule.py tasknet.tn schedule.json
"""

import json
import subprocess
import sys
from pathlib import Path

def main():
    if len(sys.argv) < 3:
        print("Usage: validate_schedule.py tasknet.tn schedule.json")
        sys.exit(1)

    tasknet_path = sys.argv[1]
    schedule_path = sys.argv[2]

    # Convert tasknet to Lean JSON
    converter_path = Path(__file__).parent / 'lean_converter.py'
    tasknet_json = '/tmp/tasknet.lean.json'

    result = subprocess.run(
        ['python3', str(converter_path), tasknet_path, tasknet_json],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"✗ Conversion failed:\n{result.stderr}")
        sys.exit(1)

    # Call Lean validator
    lean_dir = Path(__file__).parent.parent / 'src/lean/TaskNetExec'
    result = subprocess.run(
        ['lake', 'exe', 'tasknet-validate',
         '--tasknet', tasknet_json,
         '--schedule', schedule_path],
        cwd=lean_dir,
        capture_output=True,
        text=True
    )

    if result.returncode == 0 or result.returncode == 1:
        # Parse and display result
        try:
            validation_result = json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"✗ Failed to parse validation result:\n{result.stdout}")
            sys.exit(1)

        if validation_result['valid']:
            print("✅ Schedule is VALID")
            return 0
        else:
            print("❌ Schedule is INVALID")
            if validation_result.get('violations'):
                print("\nViolations:")
                for v in validation_result['violations']:
                    print(f"  • {v}")
            return 1
    else:
        print(f"✗ Validation failed:\n{result.stderr}")
        sys.exit(1)

if __name__ == '__main__':
    sys.exit(main())
