#!/usr/bin/env python3
"""
Timeline evolution visualization for TaskSAT schedules.

Creates multi-panel plots showing:
- Gantt chart of task execution
- Timeline evolution (resources, states) over time
- Error trace highlighting (optional)
"""

import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from typing import Dict, Tuple, List, Optional
from pathlib import Path

# Session separator (kept in sync with tasknet_transforms.SEP). See tasknet_gantt.py.
SESSION_SEP = "__"


def split_session_id(task_id: str) -> Tuple[Optional[str], str]:
    """'drive1__preheat' -> ('drive1', 'preheat'); 'collect' -> (None, 'collect')."""
    if SESSION_SEP in task_id:
        head, _, tail = task_id.partition(SESSION_SEP)
        return head, tail
    return None, task_id


def create_timeline_evolution_plot(
    schedule: Dict[str, Tuple[int, int]],
    evolution: dict,
    output_path: str,
    title: str = "Schedule & Timeline Evolution",
    violation_zones: Optional[List[int]] = None,
    tasknet = None  # Optional: TaskNet object for accessing impact information
):
    """
    Create multi-panel visualization of schedule + timeline evolution.

    Args:
        schedule: Dict mapping task_id -> (start_time, end_time)
        evolution: Timeline evolution data from extract_timeline_evolution()
        output_path: Path to save the PNG file
        title: Chart title
        violation_zones: Optional list of zone indices where properties violated
    """
    if not schedule or not evolution:
        print("Warning: Empty schedule or evolution data, no chart generated")
        return

    # Determine number of subplots: 1 for Gantt + N for timelines
    num_timelines = len(evolution['timelines'])
    num_subplots = 1 + num_timelines

    # Scale the Gantt panel with the row count so rows never overlap (each task
    # occupies one row; ~0.28in/row keeps labels legible). A fixed panel squashes
    # dozens of session subtasks into an unreadable band (see 20-cycle nets).
    num_rows = max(1, len(schedule))
    gantt_height = max(3.0, num_rows * 0.28)  # inches
    timeline_height = 2.0                      # inches per timeline panel

    # Create figure with subplots; height in inches = Gantt + all timeline panels.
    fig_height = gantt_height + num_timelines * timeline_height
    fig, axes = plt.subplots(
        num_subplots, 1,
        figsize=(16, fig_height),
        gridspec_kw={'height_ratios': [gantt_height] + [timeline_height] * num_timelines}
    )

    # Make axes always a list even if only one subplot
    if num_subplots == 1:
        axes = [axes]

    # ===== PANEL 1: Gantt Chart =====
    ax_gantt = axes[0]
    _draw_gantt_chart(ax_gantt, schedule, evolution, title, violation_zones, tasknet)

    # ===== PANELS 2+: Timeline Evolution =====
    zone_times = evolution['zones']

    for idx, (timeline_id, timeline_data) in enumerate(evolution['timelines'].items(), start=1):
        ax = axes[idx]
        _draw_timeline(
            ax, timeline_id, timeline_data, zone_times,
            evolution['active_tasks'], violation_zones
        )

    # Tight layout
    plt.tight_layout()

    # Save
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"📈 Timeline evolution chart saved to: {output_path}")
    plt.close()


def _draw_gantt_chart(
    ax, schedule, evolution, title, violation_zones, tasknet=None
):
    """Draw Gantt chart showing task execution."""
    # Group session siblings together, otherwise order by start time (matches
    # tasknet_gantt.py: each session instance forms a contiguous band).
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

    def _clean_label(name):
        """Row label for a task: `drive1__preheat` reads as `drive1 / preheat`."""
        head, tail = split_session_id(name)
        return f"{head} / {tail}" if head is not None else name

    task_names = [_clean_label(t[0]) for t in tasks]

    # Color palette
    colors = plt.cm.Set3.colors

    # Build task -> color-key mapping: session subtasks color by session instance,
    # others by taskdef (matches tasknet_gantt.py).
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
            linewidth=1, edgecolor='black', facecolor=color, alpha=0.7
        )
        ax.add_patch(rect)

        # Add task name on the bar (abbreviated if too long)
        if duration > 0:
            # Estimate how much space we have: roughly 1 char per 0.7 time units at fontsize 9
            # For session subtasks show the short child name (instance is in the y-label).
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

    # Highlight violation zones with red background
    if violation_zones:
        for zone_idx in violation_zones:
            if 0 <= zone_idx < len(evolution['zones']) - 1:
                z_start = evolution['zones'][zone_idx]
                z_end = evolution['zones'][zone_idx + 1]
                ax.axvspan(z_start, z_end, color='red', alpha=0.2, zorder=0)

    # Set labels and title
    ax.set_yticks(range(len(task_names)))
    ax.set_yticklabels(task_names)
    ax.set_xlabel('Time', fontsize=11, weight='bold')
    ax.set_ylabel('Tasks', fontsize=11, weight='bold')
    ax.set_title(title, fontsize=13, weight='bold')

    # Set x-axis limits to match timeline plots (full time range from zones)
    zone_times = evolution['zones']
    min_time = zone_times[0]
    max_time = zone_times[-1]
    # Add small padding (1% of range) to make end events more visible
    time_range = max_time - min_time
    padding = time_range * 0.01
    ax.set_xlim(min_time, max_time + padding)

    # Set y-axis limits
    ax.set_ylim(-0.5, len(task_names) - 0.5 + 0.8)

    # Grid
    ax.grid(axis='x', alpha=0.3, linewidth=0.5)
    ax.set_axisbelow(True)


def _draw_timeline(
    ax, timeline_id, timeline_data, zone_times, active_tasks, violation_zones
):
    """Draw a single timeline evolution plot."""
    timeline_type = timeline_data['type']
    values = timeline_data['values']

    # Create x-axis for step/line plots
    # values[i] represents the state at the END of zone interval i (at boundary i+1)
    # For step plots with where='post', we plot at zone START so the step happens at zone END
    x_times_step = zone_times[:-1]  # Zone start times for step plots
    x_times_line = zone_times[1:]   # Zone end times for line plots

    if timeline_type in ['state', 'atomic']:
        # Step plot for discrete values
        _draw_step_plot(ax, timeline_id, timeline_type, x_times_step, values, zone_times)

    elif timeline_type in ['cumulative', 'claimable']:
        # Step plot: piecewise constant, changes only via impacts at boundaries
        _draw_line_plot(ax, timeline_id, x_times_step, values, zone_times)

    elif timeline_type == 'rate':
        # Special handling for rate timelines (value + rate)
        _draw_rate_plot(ax, timeline_id, x_times_line, values, zone_times)

    # Highlight violation zones
    if violation_zones:
        for zone_idx in violation_zones:
            if 0 <= zone_idx < len(zone_times) - 1:
                z_start = zone_times[zone_idx]
                z_end = zone_times[zone_idx + 1]
                ax.axvspan(z_start, z_end, color='red', alpha=0.2, zorder=0)

    # Add vertical lines for zone boundaries
    for z in zone_times:
        ax.axvline(z, color='gray', linestyle=':', alpha=0.3, linewidth=0.8)

    # Set x-axis limits to match Gantt chart (with padding to show end events)
    min_time = zone_times[0]
    max_time = zone_times[-1]
    time_range = max_time - min_time
    padding = time_range * 0.01
    ax.set_xlim(min_time, max_time + padding)

    ax.set_ylabel(f'{timeline_id}\n({timeline_type})', fontsize=10, weight='bold')
    ax.set_xlabel('Time', fontsize=9)
    ax.grid(True, alpha=0.3, linewidth=0.5)


def _draw_step_plot(ax, timeline_id, timeline_type, x_times, values, zone_times):
    """Draw step plot for state/atomic timelines."""
    if not values:
        return

    # Extend to the final boundary so the last zone's value is drawn to the end
    xs = list(x_times) + [zone_times[-1]]

    if timeline_type == 'atomic':
        # Boolean values: 0 or 1
        numeric_values = [1 if v else 0 for v in values]
        numeric_values.append(numeric_values[-1])
        ax.step(xs, numeric_values, where='post', linewidth=2, color='blue', marker='o')
        ax.set_ylim(-0.2, 1.2)
        ax.set_yticks([0, 1])
        ax.set_yticklabels(['False', 'True'])

    else:  # state timeline
        # Map states to numeric indices for plotting
        unique_states = sorted(set(values))
        state_to_idx = {state: idx for idx, state in enumerate(unique_states)}
        numeric_values = [state_to_idx[v] for v in values]
        numeric_values.append(numeric_values[-1])

        ax.step(xs, numeric_values, where='post', linewidth=2, color='green', marker='o')
        ax.set_yticks(range(len(unique_states)))
        ax.set_yticklabels(unique_states)


def _draw_line_plot(ax, timeline_id, x_times, values, zone_times):
    """Draw step plot for cumulative/claimable timelines.

    These timelines are piecewise constant: values[i] holds throughout zone
    interval (zone_times[i], zone_times[i+1]] and changes only via impacts at
    boundaries. A step plot (where='post') shows the jump at the boundary;
    linear interpolation would misleadingly render impacts as rate-like ramps.
    """
    if not values:
        return

    # Extend to the final boundary so the last zone's value is drawn to the end
    xs = list(x_times) + [zone_times[-1]]
    ys = list(values) + [values[-1]]
    ax.step(xs, ys, where='post', linewidth=2, color='blue', marker='o', markersize=4)

    # Add min/max horizontal lines if there are bounds
    # (would need to extract bounds from timeline definition - skip for now)

    # Auto-scale y-axis with some padding
    y_min = min(values)
    y_max = max(values)
    y_range = y_max - y_min if y_max > y_min else 1
    ax.set_ylim(y_min - 0.1 * y_range, y_max + 0.1 * y_range)


def _draw_rate_plot(ax, timeline_id, x_times, values, zone_times):
    """Draw plot for rate timelines (shows value evolution with linear interpolation).

    The extraction stores both start_value and end_value for each zone interval::

        values[i] = {'start_value': value at zone_times[i],
                     'end_value': value at zone_times[i+1],
                     'rate': rate during zone}

    Assignments can happen at zone boundaries (PRE/POST impacts). We detect them
    by checking if values jump discontinuously, and draw vertical lines for assignments.
    """
    plot_times = []
    plot_values = []

    prev_end_value = None

    for i, zone_value in enumerate(values):
        zone_start = zone_times[i]
        zone_end = zone_times[i + 1]
        duration = zone_end - zone_start

        start_value = zone_value['start_value']  # Value at zone START
        end_value = zone_value['end_value']      # Value at zone END
        rate = zone_value['rate']

        # Check for assignment at START of this zone (PRE impact)
        if prev_end_value is not None and abs(start_value - prev_end_value) > 1e-6:
            # Discontinuity at zone start: add vertical jump
            plot_times.append(zone_start)
            plot_values.append(start_value)

        # Add point at zone start (if not already added by assignment above)
        if len(plot_times) == 0 or plot_times[-1] != zone_start:
            plot_times.append(zone_start)
            plot_values.append(start_value)

        # Calculate where we'd end up with just rate evolution
        expected_end_value = start_value + rate * duration

        # Check for assignment at END of this zone (POST impact)
        if abs(end_value - expected_end_value) > 1e-6:
            # Assignment at zone end: draw to expected value, then vertical drop
            plot_times.append(zone_end)
            plot_values.append(expected_end_value)
            # Vertical drop to actual end value
            plot_times.append(zone_end)
            plot_values.append(end_value)
        else:
            # No assignment: just rate-based evolution
            plot_times.append(zone_end)
            plot_values.append(end_value)

        prev_end_value = end_value

    # Plot with linear segments
    # Use purple color for rate timelines
    # Note: matplotlib connects points in order, so duplicate x-values create vertical lines
    ax.plot(plot_times, plot_values, linewidth=2, color='#800080', marker='o', markersize=3, solid_capstyle='butt')

    # Auto-scale y-axis
    if plot_values:
        y_min = min(plot_values)
        y_max = max(plot_values)
        y_range = y_max - y_min if y_max > y_min else 1
        ax.set_ylim(y_min - 0.1 * y_range, y_max + 0.1 * y_range)


def main():
    """Test the visualization with sample data."""
    import sys

    if len(sys.argv) < 3:
        print("Usage: python tasknet_timeline_viz.py <schedule.json> <evolution.json> [output.png]")
        sys.exit(1)

    schedule_file = sys.argv[1]
    evolution_file = sys.argv[2]
    output_file = sys.argv[3] if len(sys.argv) > 3 else "timeline_evolution.png"

    # Load schedule
    with open(schedule_file, 'r') as f:
        schedule_data = json.load(f)

    # Parse schedule format
    if 'tasks' in schedule_data and isinstance(schedule_data['tasks'], dict):
        # Legacy format: {"tasks": {"task1": {"start": 10, "end": 20}}}
        schedule = {}
        for task_id, times in schedule_data['tasks'].items():
            if isinstance(times, dict):
                schedule[task_id] = (times['start'], times['end'])
            elif isinstance(times, (list, tuple)):
                schedule[task_id] = tuple(times[:2])
    else:
        # Simple format: {"task1": [10, 20]}
        schedule = {k: tuple(v[:2]) if isinstance(v, (list, tuple)) else v
                   for k, v in schedule_data.items()}

    # Load evolution
    with open(evolution_file, 'r') as f:
        evolution = json.load(f)

    # Create visualization
    create_timeline_evolution_plot(schedule, evolution, output_file)
    print(f"✓ Visualization created: {output_file}")


if __name__ == '__main__':
    main()
