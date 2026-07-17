#!/usr/bin/env python3
"""
Generate Gantt charts from TaskSAT schedules.

Can be used as a standalone script or imported as a module.

Usage as script:
    python src/smt/tasknet_gantt.py schedule.json output.png

Usage as module:
    from tasknet_gantt import create_gantt_from_schedule
    create_gantt_from_schedule(schedule_dict, 'output.png')
"""

import sys
import json
import argparse
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from typing import Dict, Tuple, List, Optional, Union
from pathlib import Path


def parse_schedule_json(json_data: Union[str, dict]) -> Dict[str, Tuple[int, int]]:
    """
    Parse schedule from JSON format.

    Expected format (dict mapping task_id -> [start, end]):
        {
            "task1": [10, 20],
            "task2": [30, 40]
        }

    Or nested format with 'tasks' key:
        {
            "tasks": {
                "task1": {"start": 10, "end": 20},
                "task2": {"start": 30, "end": 40}
            }
        }

    Args:
        json_data: Either a JSON string or already-parsed dict

    Returns:
        Dict mapping task_id -> (start_time, end_time)
    """
    if isinstance(json_data, str):
        data = json.loads(json_data)
    else:
        data = json_data

    schedule = {}

    # Handle nested format with 'tasks' key
    if 'tasks' in data:
        tasks_data = data['tasks']
    else:
        tasks_data = data

    # Parse tasks
    for task_id, task_info in tasks_data.items():
        if isinstance(task_info, (list, tuple)) and len(task_info) >= 2:
            # Format: [start, end]
            schedule[task_id] = (int(task_info[0]), int(task_info[1]))
        elif isinstance(task_info, dict):
            # Format: {"start": 10, "end": 20}
            if 'start' in task_info and 'end' in task_info:
                schedule[task_id] = (int(task_info['start']), int(task_info['end']))

    return schedule


def create_gantt_from_schedule(
    schedule: Dict[str, Tuple[int, int]],
    output_path: str,
    title: str = "Task Schedule",
    figsize: Tuple[int, int] = (12, 6),
    tasknet=None
):
    """
    Create a Gantt chart from a schedule dictionary.

    Args:
        schedule: Dict mapping task_id -> (start_time, end_time)
        output_path: Path to save the PNG file
        title: Chart title
        figsize: Figure size (width, height)
        tasknet: Optional TaskNet AST. When provided, tasks are colored by their
            taskdef so that all instances of the same taskdef share a color.
            Without it, coloring falls back to per-row index.
    """
    if not schedule:
        print("Warning: Empty schedule, no chart generated")
        return

    # Sort tasks by start time, then by name
    tasks = sorted(schedule.items(), key=lambda x: (x[1][0], x[0]))
    task_names = [t[0] for t in tasks]

    # Create figure
    fig, ax = plt.subplots(figsize=figsize)

    # Color palette
    colors = plt.cm.Set3.colors

    # Build task -> taskdef mapping for coloring so that all instances of the
    # same taskdef share a color (matches the Timeline Evolution chart).
    task_to_taskdef = {}
    taskdef_to_color = {}
    if tasknet:
        # Map each task to its taskdef (or use task name as fallback)
        for task in tasknet.tasks:
            if task.definition:
                task_to_taskdef[task.id] = task.definition
            else:
                # No taskdef - use task name itself
                task_to_taskdef[task.id] = task.id

        # Assign colors to each unique taskdef
        unique_taskdefs = sorted(set(task_to_taskdef.values()))
        for i, taskdef in enumerate(unique_taskdefs):
            taskdef_to_color[taskdef] = colors[i % len(colors)]

    # Draw bars for each task
    for i, (task_name, (start, end)) in enumerate(tasks):
        duration = end - start

        # Color by taskdef if available, otherwise by task index
        if tasknet and task_name in task_to_taskdef:
            color = taskdef_to_color[task_to_taskdef[task_name]]
        else:
            color = colors[i % len(colors)]

        # Draw task bar
        rect = patches.Rectangle(
            (start, i), duration, 0.8,
            linewidth=1, edgecolor='black', facecolor=color
        )
        ax.add_patch(rect)

        # Add task name on the bar (abbreviated if too long)
        # Estimate how much space we have: roughly 1 char per 0.7 time units at fontsize 9
        available_width = duration * 0.7
        display_name = task_name

        # Abbreviate if needed
        if len(display_name) > available_width:
            # Allow some overflow (1.3x) before abbreviating
            if len(display_name) > available_width * 1.3:
                max_chars = max(3, int(available_width * 1.3))
                if max_chars < len(display_name):
                    # Smart abbreviation: try to keep meaningful parts
                    if '_' in display_name:
                        # For names like "comm_preheat_auto_0", try to keep prefix and suffix
                        parts = display_name.split('_')
                        if len(parts) >= 2:
                            # Keep first part and last part, abbreviate middle
                            prefix = parts[0][:max_chars//2]
                            suffix = parts[-1]
                            display_name = f"{prefix}..{suffix}"
                        else:
                            display_name = display_name[:max_chars-2] + ".."
                    else:
                        display_name = display_name[:max_chars-2] + ".."

        ax.text(
            start + duration/2, i + 0.4, display_name,
            ha='center', va='center', fontsize=9, weight='bold'
        )

    # Set labels and title
    ax.set_yticks(range(len(task_names)))
    ax.set_yticklabels(task_names)
    ax.set_xlabel('Time', fontsize=12)
    ax.set_ylabel('Tasks', fontsize=12)
    ax.set_title(title, fontsize=14, weight='bold')

    # Set x-axis limits with some padding
    if schedule:
        all_starts = [s for s, e in schedule.values()]
        all_ends = [e for s, e in schedule.values()]
        min_time = min(all_starts)
        max_time = max(all_ends)
        padding = (max_time - min_time) * 0.05
        ax.set_xlim(min_time - padding, max_time + padding)

    # Set y-axis limits to show all tasks (bars have height 0.8, so need space above)
    ax.set_ylim(-0.5, len(task_names) - 0.5 + 0.8)

    # Grid
    ax.grid(axis='x', alpha=0.3)
    ax.set_axisbelow(True)

    # Tight layout
    plt.tight_layout()

    # Save
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Gantt chart saved to: {output_path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description='Generate Gantt chart from TaskSAT schedule JSON file'
    )
    parser.add_argument(
        'schedule_file',
        help='Path to schedule JSON file (e.g., {"task1": [10, 20], "task2": [30, 40]})'
    )
    parser.add_argument(
        'output',
        nargs='?',
        default=None,
        help='Output PNG file (default: same directory as schedule_file, named <tasknet>_gantt.png)'
    )

    args = parser.parse_args()

    # Read schedule file
    with open(args.schedule_file, 'r') as f:
        schedule_json = f.read()

    # Parse schedule
    try:
        schedule = parse_schedule_json(schedule_json)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"Error: Could not parse schedule JSON: {e}")
        return 1

    if not schedule:
        print("Error: No schedule found in input file")
        return 1

    # Determine output path and title from input filename
    input_path = Path(args.schedule_file)
    if args.output:
        output_path = args.output
    else:
        # Default: same directory as input, replace extension with _gantt.png
        output_path = str(input_path.parent / f"{input_path.stem}_gantt.png")

    # Use filename (without _schedule suffix) as title
    title = input_path.stem.replace('_schedule', '').replace('_', ' ').title()

    # Generate chart
    create_gantt_from_schedule(schedule, output_path, title)

    return 0


if __name__ == '__main__':
    sys.exit(main())
