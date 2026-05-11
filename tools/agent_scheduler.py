#!/usr/bin/env python3
"""
Agent-based generate-and-test scheduler using Claude Code Agent + Lean validator.

This uses the Agent tool within Claude Code, so no API key is needed.
The main script orchestrates validation, but schedule generation is done by spawning agents.

Usage:
    Run from within Claude Code:
    "Run agent_scheduler.py on test_mexec_10tasks.tn"
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

def convert_tasknet_to_lean(tasknet_path):
    """Convert tasknet to Lean JSON format."""
    lean_json_path = "/tmp/tasknet_agent.lean.json"

    converter_path = Path(__file__).parent / "lean_converter.py"
    result = subprocess.run(
        ["python3", str(converter_path), tasknet_path, lean_json_path],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise Exception(f"Conversion failed: {result.stderr}")

    with open(lean_json_path) as f:
        return json.load(f)

def validate_schedule(tasknet_lean_json_path, schedule_json_path):
    """Validate schedule using Lean validator."""
    lean_dir = Path(__file__).parent.parent / "src/lean/TaskNetExec"

    result = subprocess.run(
        ["lake", "exe", "tasknet-validate",
         "--tasknet", tasknet_lean_json_path,
         "--schedule", schedule_json_path],
        cwd=lean_dir,
        capture_output=True,
        text=True
    )

    if result.returncode not in [0, 1]:
        raise Exception(f"Validation failed: {result.stderr}")

    # Parse JSON output
    output = result.stdout.strip()
    validation_result = json.loads(output)

    return validation_result["valid"], validation_result["violations"]

def main():
    parser = argparse.ArgumentParser(description="Agent-based tasknet scheduler")
    parser.add_argument("tasknet", help="Path to tasknet file (.tn)")
    parser.add_argument("--max-iterations", type=int, default=10, help="Max iterations")
    parser.add_argument("--output", default="/tmp/agent_schedule.json", help="Output schedule path")

    args = parser.parse_args()

    print(f"""
{'='*80}
Agent-Based Scheduler
{'='*80}

This script orchestrates the generate-and-test loop:
1. Python validates schedules with Lean
2. Claude Code Agent generates/fixes schedules based on violations

To run this, you should invoke it through Claude Code with a message like:
"Run the agent scheduler on {args.tasknet}"

The agent will:
- Read the tasknet constraints
- Generate a schedule JSON
- Receive validation feedback
- Iterate until valid

Note: This script is meant to be run THROUGH Claude Code, not standalone.
The actual schedule generation happens via the Agent tool.
""")

    # Convert tasknet
    print(f"\nConverting {args.tasknet}...")
    tasknet_json = convert_tasknet_to_lean(args.tasknet)
    lean_json_path = "/tmp/tasknet_agent.lean.json"

    print(f"✓ Converted tasknet with {len(tasknet_json['tasks'])} tasks")
    print(f"\nTasknet summary:")
    print(f"  - Tasks: {len(tasknet_json['tasks'])}")
    print(f"  - Timelines: {len(tasknet_json['timelines'])}")
    print(f"  - End time: {tasknet_json['endTime']}")

    # Save tasknet summary for agent
    summary_path = "/tmp/tasknet_summary.txt"
    with open(summary_path, 'w') as f:
        f.write(f"Tasknet: {tasknet_json['id']}\n")
        f.write(f"Tasks: {len(tasknet_json['tasks'])}\n")
        f.write(f"End time: {tasknet_json['endTime']}\n\n")
        f.write("Task constraints (first 10):\n")
        for task in tasknet_json['tasks'][:10]:
            f.write(f"  {task['id']}: start=[{task['startrng']['low']}, {task['startrng']['high']}], ")
            f.write(f"dur=[{task['durrng']['low']}, {task['durrng']['high']}]\n")

    print(f"\n{'='*80}")
    print("Ready for agent-based generation!")
    print(f"{'='*80}")
    print("\nNext steps:")
    print(f"1. Full tasknet JSON: {lean_json_path}")
    print(f"2. Summary: {summary_path}")
    print(f"3. Use Claude Code Agent to generate schedule at: /tmp/agent_schedule_iter1.json")
    print(f"4. This script will validate and provide feedback")

    return 0

if __name__ == "__main__":
    sys.exit(main())
