#!/usr/bin/env python3
"""
Visualize a task schedule as a Gantt chart.

Usage:
    python3 tools/visualize_schedule.py schedule.json [--output gantt.png] [--grouped]
"""

import json
import sys
import argparse
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

def create_gantt_chart(schedule_path, output_path='gantt.png', grouped=False):
    """Create a Gantt chart from a schedule JSON file."""

    with open(schedule_path) as f:
        schedule = json.load(f)

    tasks = schedule['tasks']

    if grouped:
        create_grouped_gantt(tasks, output_path)
    else:
        create_flat_gantt(tasks, output_path)

def create_flat_gantt(tasks, output_path):
    """Create a Gantt chart with one line per task."""

    # Group tasks by type for coloring
    task_types = {}
    for task_id in tasks.keys():
        # Extract type from task name (first component before _)
        task_type = task_id.split('_')[0]
        if task_type not in task_types:
            task_types[task_type] = []
        task_types[task_type].append(task_id)

    # Assign colors to task types
    color_palette = [
        '#3498db', '#e74c3c', '#f39c12', '#27ae60', '#9b59b6',
        '#1abc9c', '#e91e63', '#ff9800', '#795548', '#607d8b'
    ]
    colors = {task_type: color_palette[i % len(color_palette)]
              for i, task_type in enumerate(sorted(task_types.keys()))}

    # Create figure
    fig, ax = plt.subplots(figsize=(16, max(12, len(tasks) * 0.3)))

    # Build task list sorted by start time
    sorted_tasks = sorted(tasks.items(), key=lambda x: x[1]['start'])

    y_pos = 0
    y_labels = []
    y_ticks = []

    for task_id, times in sorted_tasks:
        start = times['start']
        end = times['end']
        duration = end - start

        # Get color based on task type
        task_type = task_id.split('_')[0]
        color = colors.get(task_type, '#95a5a6')

        # Draw task bar
        ax.barh(y_pos, duration, left=start, height=0.8,
               color=color, alpha=0.85, edgecolor='black', linewidth=0.5)

        # Add task label
        y_labels.append(task_id)
        y_ticks.append(y_pos)
        y_pos += 1

    # Set labels and title
    ax.set_yticks(y_ticks)
    ax.set_yticklabels(y_labels, fontsize=8)
    ax.set_xlabel('Time', fontsize=12, fontweight='bold')
    ax.set_title(f'Task Schedule Gantt Chart ({len(tasks)} tasks)',
                 fontsize=14, fontweight='bold')
    ax.grid(True, axis='x', alpha=0.6, linewidth=1.0, linestyle='-', color='gray')

    # Create legend
    legend_elements = [
        mpatches.Patch(facecolor=color, label=task_type, alpha=0.85)
        for task_type, color in sorted(colors.items())
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=10)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Gantt chart saved to {output_path}")

def create_grouped_gantt(tasks, output_path):
    """Create a Gantt chart with tasks of the same type on the same line."""

    # Group tasks by type
    task_groups = {}
    for task_id, times in tasks.items():
        # Extract base type (more granular than just first component)
        if 'preheat' in task_id:
            if 'comm' in task_id:
                group_key = 'comm_preheat'
            elif 'global' in task_id:
                group_key = 'global_localization_preheat'
            elif 'route' in task_id:
                group_key = 'route_segment_preheat'
            else:
                group_key = 'other_preheat'
        elif 'maintainheat' in task_id:
            if 'comm' in task_id:
                group_key = 'comm_maintainheat'
            elif 'global' in task_id:
                group_key = 'global_localization_maintainheat'
            elif 'route' in task_id:
                group_key = 'route_segment_maintainheat'
            else:
                group_key = 'other_maintainheat'
        elif 'downlink' in task_id:
            group_key = 'downlink'
        elif 'orbiter_visible' in task_id:
            group_key = 'orbiter_visible'
        elif 'orbiter_available' in task_id:
            group_key = 'orbiter_available'
        elif 'battery' in task_id:
            group_key = 'battery_recharge'
        elif 'global_localization_request' in task_id:
            group_key = 'global_localization_request'
        elif 'route_segment_request_request' in task_id:
            group_key = 'route_segment_request'
        else:
            # Fallback: use first two components
            parts = task_id.split('_')
            group_key = '_'.join(parts[:2]) if len(parts) > 1 else parts[0]

        if group_key not in task_groups:
            task_groups[group_key] = []
        task_groups[group_key].append((task_id, times))

    # Color scheme
    colors = {
        'orbiter_visible': '#2c3e50',
        'orbiter_available': '#3498db',
        'comm_preheat': '#e74c3c',
        'comm_maintainheat': '#f39c12',
        'downlink': '#27ae60',
        'global_localization_preheat': '#c39bd3',
        'global_localization_maintainheat': '#a569bd',
        'global_localization_request': '#8e44ad',
        'battery_recharge': '#16a085',
        'route_segment_preheat': '#f8b4d9',
        'route_segment_maintainheat': '#f093c3',
        'route_segment_request': '#e91e63'
    }

    # Default color for unknown types
    default_color = '#95a5a6'

    # Create figure
    fig, ax = plt.subplots(figsize=(18, max(10, len(task_groups) * 0.8)))

    # Build task list with one line per group
    y_pos = 0
    y_labels = []
    y_ticks = []

    for group_key in sorted(task_groups.keys()):
        group_tasks = task_groups[group_key]
        color = colors.get(group_key, default_color)

        # Draw all tasks of this type on the same line
        for task_id, times in sorted(group_tasks, key=lambda x: x[1]['start']):
            start = times['start']
            end = times['end']
            duration = end - start

            # Draw task bar
            ax.barh(y_pos, duration, left=start, height=0.7,
                   color=color, alpha=0.85, edgecolor='black', linewidth=0.5)

            # Extract instance identifier for label
            # Handle patterns: task__1, task_1, task1
            label = None
            if '__' in task_id:
                # Pattern: comm_maintainheat__1 -> "1"
                label = task_id.split('__')[-1]
            elif '_' in task_id:
                # Pattern: downlink_all1 -> "all1", or orbiter_visible_0 -> "0"
                parts = task_id.split('_')
                # Try to find a numeric suffix
                for part in reversed(parts):
                    if part.isdigit() or (len(part) > 0 and part[-1].isdigit()):
                        label = part
                        break

            # Add label to bar
            if label:
                # Adjust font size based on duration
                if duration > 300:
                    fontsize = 8
                elif duration > 100:
                    fontsize = 7
                else:
                    fontsize = 6

                ax.text(start + duration/2, y_pos, label,
                       ha='center', va='center', fontsize=fontsize,
                       fontweight='bold', color='white')

        # Group label
        label = f"{group_key.replace('_', ' ').title()} ({len(group_tasks)})"
        y_labels.append(label)
        y_ticks.append(y_pos)
        y_pos += 1

    # Set labels and title
    ax.set_yticks(y_ticks)
    ax.set_yticklabels(y_labels, fontsize=10)
    ax.set_xlabel('Time', fontsize=12, fontweight='bold')
    ax.set_title('Task Schedule Gantt Chart - Grouped by Task Type',
                 fontsize=14, fontweight='bold')
    ax.grid(True, axis='x', alpha=0.6, linewidth=1.0, linestyle='-', color='gray')

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Grouped Gantt chart saved to {output_path}")

def main():
    parser = argparse.ArgumentParser(
        description='Visualize a task schedule as a Gantt chart',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic Gantt chart
  python3 tools/visualize_schedule.py schedule.json

  # Grouped by task type
  python3 tools/visualize_schedule.py schedule.json --grouped

  # Custom output file
  python3 tools/visualize_schedule.py schedule.json --output my_gantt.png --grouped
        """
    )

    parser.add_argument('schedule', help='Path to schedule JSON file')
    parser.add_argument('--output', '-o', default='gantt.png',
                       help='Output PNG file (default: gantt.png)')
    parser.add_argument('--grouped', '-g', action='store_true',
                       help='Group tasks of same type on one line')

    args = parser.parse_args()

    try:
        create_gantt_chart(args.schedule, args.output, args.grouped)
    except FileNotFoundError:
        print(f"Error: Schedule file not found: {args.schedule}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in schedule file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
