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

# Session separator (kept in sync with tasknet_transforms.SEP). flatten_sessions()
# names each session subtask `{instance}__{child}`; splitting on it recovers the
# session grouping for the schedule charts.
SESSION_SEP = "__"


def split_session_id(task_id: str) -> Tuple[Optional[str], str]:
    """'drive1__preheat' -> ('drive1', 'preheat'); 'collect' -> (None, 'collect')."""
    if SESSION_SEP in task_id:
        head, _, tail = task_id.partition(SESSION_SEP)
        return head, tail
    return None, task_id


def parse_schedule_json(json_data: Union[str, dict]) -> Dict[str, Tuple[int, int]]:
    """
    Parse schedule from JSON format.

    Expected format (dict mapping task_id -> [start, end])::

        {
            "task1": [10, 20],
            "task2": [30, 40]
        }

    Or nested format with 'tasks' key::

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

    # Group session siblings together, otherwise order by start time. Each
    # session instance (drive1, drive2, ...) forms a contiguous band ordered by
    # its earliest task; standalone tasks are their own singleton group.
    def _group_key(item):
        """The band a task belongs to: its session instance, or itself."""
        name, (start, _end) = item
        head, _tail = split_session_id(name)
        return head if head is not None else name

    group_min_start = {}
    for name, (start, _end) in schedule.items():
        g = _group_key((name, (start, _end)))
        group_min_start[g] = min(group_min_start.get(g, start), start)

    tasks = sorted(
        schedule.items(),
        key=lambda x: (group_min_start[_group_key(x)], _group_key(x), x[1][0], x[0])
    )

    # Clean, grouped y-labels: 'drive1__preheat' -> 'drive1 / preheat'.
    def _clean_label(name):
        """Row label for a task: `drive1__preheat` reads as `drive1 / preheat`."""
        head, tail = split_session_id(name)
        return f"{head} / {tail}" if head is not None else name

    task_names = [_clean_label(t[0]) for t in tasks]

    # Grow the figure height with the row count so rows never overlap (each task
    # is one row). The caller's figsize sets the width and the floor height; tall
    # schedules (e.g. 20-cycle session nets) expand beyond it at ~0.28in/row.
    fig_w, fig_h = figsize
    fig_h = max(fig_h, len(task_names) * 0.28 + 1.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    # Color palette
    colors = plt.cm.Set3.colors

    # Build task -> color-key mapping. Session subtasks color by their SESSION
    # INSTANCE (so drive1__preheat and drive1__drive share a color, distinct
    # from drive2__*); other tasks color by taskdef, matching the Timeline
    # Evolution chart.
    task_to_family = {}
    family_to_color = {}
    for task_name in schedule:
        head, _tail = split_session_id(task_name)
        if head is not None:
            task_to_family[task_name] = f"session:{head}"
    if tasknet:
        for task in tasknet.tasks:
            if task.id in task_to_family:
                continue
            task_to_family[task.id] = task.definition if task.definition else task.id
    # Any task not yet mapped (no tasknet, non-session) falls back to its own name.
    for task_name in schedule:
        task_to_family.setdefault(task_name, task_name)

    unique_families = sorted(set(task_to_family.values()))
    for i, fam in enumerate(unique_families):
        family_to_color[fam] = colors[i % len(colors)]

    # Draw bars for each task
    for i, (task_name, (start, end)) in enumerate(tasks):
        duration = end - start

        # Color by family (session instance or taskdef); fall back to row index.
        if task_name in task_to_family:
            color = family_to_color[task_to_family[task_name]]
        else:
            color = colors[i % len(colors)]

        # Draw task bar
        rect = patches.Rectangle(
            (start, i), duration, 0.8,
            linewidth=1, edgecolor='black', facecolor=color
        )
        ax.add_patch(rect)

        # Add task name on the bar (abbreviated if too long). For session
        # subtasks use the short child name (the session instance is already
        # shown in the y-axis label and by color).
        # Estimate how much space we have: roughly 1 char per 0.7 time units at fontsize 9
        available_width = duration * 0.7
        _head, display_name = split_session_id(task_name)

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
    """CLI entry point: turn a schedule JSON file into a Gantt chart PNG.

    Standalone counterpart to the chart the verifier produces automatically;
    useful for re-rendering a schedule saved earlier.
    """
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
