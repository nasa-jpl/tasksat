#!/usr/bin/env python3
"""
Temporal Range Visualization for TaskNet specifications.

Shows tasks laid out on a horizontal timeline according to their
start_range, end_range, and duration_range constraints. This visualization
helps understand the temporal structure of a tasknet specification before
solving.

Unlike Gantt charts (which show actual scheduled times), this shows the
POSSIBLE time windows from the specification.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from typing import Dict
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from tasknet_ast import TaskNet, Task, TaskKind, AfterDependency, ContainedinDependency

# Use the same color palette as other visualizations
_SET3 = [
    "#8dd3c7", "#ffffb3", "#bebada", "#fb8072", "#80b1d3", "#fdb462",
    "#b3de69", "#fccde5", "#d9d9d9", "#bc80bd", "#ccebc5", "#ffed6f",
]


def _taskdef_color_map(tn: TaskNet) -> dict:
    """Map each task id -> a Set3 color keyed by its taskdef family."""
    family = {}
    for task in tn.tasks:
        family[task.id] = task.definition if task.definition else task.id
    unique = sorted(set(family.values()))
    fam_color = {fam: _SET3[i % len(_SET3)] for i, fam in enumerate(unique)}
    return {tid: fam_color[fam] for tid, fam in family.items()}


def _base_ranges(task: Task, taskdef_map: dict, horizon: int) -> list:
    """Initial [start_min, start_max, end_min, end_max, dur_min, dur_max] for a task.

    Ranges are inherited from the task's taskdef when the instance does not set
    them. Missing bounds default to the widest feasible interval [0, horizon];
    duration/start/end are cross-coupled so an explicit duration tightens the end
    (and vice versa) even before dependency propagation.
    """
    startrng = task.startrng
    endrng = task.endrng
    durrng = task.durrng

    if task.definition and task.definition in taskdef_map:
        taskdef = taskdef_map[task.definition]
        startrng = startrng or taskdef.startrng
        endrng = endrng or taskdef.endrng
        durrng = durrng or taskdef.durrng

    start_min = startrng.low if startrng else 0
    start_max = startrng.high if startrng else horizon
    dur_min = durrng.low if durrng else 0
    dur_max = durrng.high if durrng else horizon

    if endrng:
        end_min = endrng.low
        end_max = endrng.high
    else:
        end_min = start_min + dur_min
        end_max = min(start_max + dur_max, horizon)

    return [start_min, start_max, end_min, end_max, dur_min, dur_max]


def _tighten(bounds: list, key: int, lo=None, hi=None) -> bool:
    """Narrow bounds[key] (lower) and/or bounds[key+1] (upper). Returns True if changed.

    Only ever shrinks an interval — a new lower bound is applied when it is
    larger than the current one, a new upper bound when it is smaller.
    """
    changed = False
    if lo is not None and lo > bounds[key]:
        bounds[key] = lo
        changed = True
    if hi is not None and hi < bounds[key + 1]:
        bounds[key + 1] = hi
        changed = True
    return changed


def _dependencies(task: Task, taskdef_map: dict) -> list:
    """All after/containedin dependencies for a task, including those on its taskdef."""
    sources = [task]
    if task.definition and task.definition in taskdef_map:
        sources.append(taskdef_map[task.definition])

    deps = []
    for src in sources:
        for attr in ('after_instances', 'after_definitions',
                     'containedin_instances', 'containedin_definitions'):
            deps.extend(getattr(src, attr, None) or [])
    return deps


def _resolve_operand(ref_id: str, bounds: dict, tn: TaskNet) -> list:
    """Resolve a dependency operand (task instance or taskdef) to bounded task ids."""
    if ref_id in bounds:
        return [ref_id]
    # Taskdef reference: every instance of it that we have bounds for.
    return [t.id for t in tn.tasks
            if t.kind != TaskKind.DEFINITION
            and t.definition == ref_id
            and t.id in bounds]


def _propagate_dependency_bounds(tn: TaskNet) -> Dict[str, tuple]:
    """Compute tightened task bounds by propagating through after/containedin deps.

    This is an *approximation* of the schedule's feasible windows: it does interval
    propagation to a fixpoint rather than an exact SMT projection, and for a
    dependency on a taskdef with several instances it uses the conservative union
    over those instances. It never invents an upper/lower bound that the semantics
    don't imply (see the one-sided handling of a missing gap/offset below).

    Returns:
        Dict task_id -> (start_min, start_max, end_min, end_max, dur_min, dur_max).
        A window is infeasible (over-constrained) iff start_min > start_max or
        end_min > end_max; callers should surface that rather than draw it.
    """
    taskdef_map = {t.id: t for t in tn.tasks if t.kind == TaskKind.DEFINITION}

    bounds = {t.id: _base_ranges(t, taskdef_map, tn.endTime)
              for t in tn.tasks if t.kind != TaskKind.DEFINITION}

    # Iterate to a fixpoint (bounded, since every step only shrinks intervals).
    max_iters = 100
    for _ in range(max_iters):
        changed = False

        for task in tn.tasks:
            if task.kind == TaskKind.DEFINITION or task.id not in bounds:
                continue
            b = bounds[task.id]

            for dep in _dependencies(task, taskdef_map):
                if isinstance(dep, AfterDependency):
                    refs = _resolve_operand(dep.task_id, bounds, tn)
                    if not refs:
                        continue
                    # Conservative over instances: earliest of the earliest ends,
                    # latest of the latest ends.
                    pred_end_min = min(bounds[r][2] for r in refs)
                    pred_end_max = max(bounds[r][3] for r in refs)

                    # `after A`      -> start >= A.end                 (lower only)
                    # `after A [g0,g1]` -> start in [A.end+g0, A.end+g1] (both)
                    gap_lo = dep.gap.low if dep.gap else 0
                    gap_hi = (pred_end_max + dep.gap.high) if dep.gap else None
                    changed |= _tighten(b, 0, lo=pred_end_min + gap_lo, hi=gap_hi)

                elif isinstance(dep, ContainedinDependency):
                    refs = _resolve_operand(dep.task_id, bounds, tn)
                    if not refs:
                        continue
                    par_start_min = min(bounds[r][0] for r in refs)
                    par_start_max = max(bounds[r][1] for r in refs)
                    par_end_min = min(bounds[r][2] for r in refs)
                    par_end_max = max(bounds[r][3] for r in refs)

                    # `containedin A` -> A.start <= child.start AND child.end <= A.end
                    #   (containment, NOT equality — start upper / end lower are open)
                    # `containedin A [s0,s1] [e0,e1]` pins both sides via offsets.
                    so = dep.start_offset
                    eo = dep.end_offset
                    start_lo = par_start_min + (so.low if so else 0)
                    start_hi = (par_start_max + so.high) if so else par_end_max
                    end_lo = (par_end_min - eo.high) if eo else par_start_min
                    end_hi = par_end_max - (eo.low if eo else 0)

                    changed |= _tighten(b, 0, lo=start_lo, hi=start_hi)
                    changed |= _tighten(b, 2, lo=end_lo, hi=end_hi)

            # Couple start/end through duration: end = start + duration.
            # end in [start_min+dur_min, start_max+dur_max]; symmetric back-constraint
            # on start from end. Only tightens (never widens) the current window.
            changed |= _tighten(b, 2, lo=b[0] + b[4], hi=b[1] + b[5])
            changed |= _tighten(b, 0, lo=b[2] - b[5], hi=b[3] - b[4])

        if not changed:
            break

    return {tid: tuple(b) for tid, b in bounds.items()}


def _get_task_ranges(task: Task, tn: TaskNet, propagated_bounds: Dict[str, tuple]) -> tuple:
    """Effective (start_min, start_max, end_min, end_max, dur_min, dur_max) for a task.

    Always sourced from the propagated bounds; falls back to base ranges only if
    the task is somehow absent (e.g. a definition slipped through).
    """
    if task.id in propagated_bounds:
        return propagated_bounds[task.id]
    taskdef_map = {t.id: t for t in tn.tasks if t.kind == TaskKind.DEFINITION}
    return tuple(_base_ranges(task, taskdef_map, tn.endTime))


def create_temporal_range_visualization(tn: TaskNet, output_path: str) -> bool:
    """
    Create a horizontal timeline visualization showing task time ranges.

    Args:
        tn: TaskNet (after transforms, so ranges are resolved)
        output_path: Path to save the PNG

    Returns:
        True if successful, False otherwise
    """
    # Filter to non-definition tasks that have time constraints
    tasks = [t for t in tn.tasks if t.kind != TaskKind.DEFINITION]

    if not tasks:
        print("⚠️  No tasks to visualize")
        return False

    # Get color map
    color_map = _taskdef_color_map(tn)

    # Propagate dependency bounds
    propagated_bounds = _propagate_dependency_bounds(tn)

    # Create figure
    fig, ax = plt.subplots(figsize=(14, max(6, len(tasks) * 0.5)))

    # Track min/max time for axis
    min_time = float('inf')
    max_time = 0

    # Tasks whose windows the spec over-constrains (start_min>start_max etc.)
    infeasible_tasks = []

    # Draw each task
    for idx, task in enumerate(tasks):
        y_pos = len(tasks) - idx - 1  # Top to bottom
        color = color_map.get(task.id, '#cccccc')

        # Get effective ranges (with dependency propagation)
        start_min, start_max, end_min, end_max, dur_min, dur_max = _get_task_ranges(task, tn, propagated_bounds)

        min_time = min(min_time, start_min)
        max_time = max(max_time, end_max)

        # Infeasible window: dependency propagation drove a lower bound above its
        # upper bound (the spec over-constrains this task). Flag it rather than
        # drawing a nonsensical negative-width box.
        if start_min > start_max or end_min > end_max:
            infeasible_tasks.append(task.id)
            height = 0.8
            # Small fixed-width marker at the (inverted) start interval — the true
            # window is empty, so any width would be misleading; keep it compact.
            marker_x = min(start_min, start_max)
            marker_w = max(0.02 * (tn.endTime or 1), 1)
            ax.add_patch(mpatches.Rectangle(
                (marker_x, y_pos - height / 2), marker_w, height,
                facecolor='none', edgecolor='red', hatch='xx', linewidth=1.5,
            ))
            label = task.id
            if task.kind == TaskKind.OPTIONAL:
                label += " (opt)"
            elif task.kind == TaskKind.REQUEST:
                label += " (req)"
            ax.text(-0.02 * (max_time - min_time), y_pos, label,
                    ha='right', va='center', fontsize=9, color='red')
            ax.text(marker_x + marker_w + 0.01 * (max_time - min_time), y_pos,
                    f"⚠ infeasible: s:[{start_min},{start_max}] e:[{end_min},{end_max}]",
                    ha='left', va='center', fontsize=8, style='italic', color='red')
            continue

        # Calculate how constrained this task is (ratio of actual range to horizon)
        full_window_width = end_max - start_min
        constraint_ratio = full_window_width / tn.endTime if tn.endTime > 0 else 1.0

        # Tasks with tight constraints (< 10% of horizon) get visual emphasis
        is_highly_constrained = constraint_ratio < 0.1

        # Draw the possible time window as a box
        # The box spans from earliest possible start to latest possible end
        height = 0.8

        # Main box showing full possible window
        # Use higher alpha and thicker border for highly constrained tasks
        light_alpha = 0.5 if is_highly_constrained else 0.3
        light_linewidth = 2 if is_highly_constrained else 1

        rect = mpatches.Rectangle(
            (start_min, y_pos - height/2),
            full_window_width,
            height,
            facecolor=color,
            edgecolor='black',
            alpha=light_alpha,
            linewidth=light_linewidth
        )
        ax.add_patch(rect)

        # Show the "core" window (latest start to earliest end) if it exists
        if start_max <= end_min:
            core_width = end_min - start_max
            core_alpha = 0.85 if is_highly_constrained else 0.7
            core_linewidth = 2.5 if is_highly_constrained else 1.5

            core_rect = mpatches.Rectangle(
                (start_max, y_pos - height/2),
                core_width,
                height,
                facecolor=color,
                edgecolor='black',
                alpha=core_alpha,
                linewidth=core_linewidth
            )
            ax.add_patch(core_rect)

            # Add a marker for highly constrained tasks
            if is_highly_constrained:
                # Add a small diamond marker at the center
                center_x = (start_max + end_min) / 2
                ax.plot(center_x, y_pos, marker='D', markersize=6,
                       color='black', markerfacecolor=color,
                       markeredgewidth=1.5, zorder=10)

        # Task label
        label = task.id
        if task.kind == TaskKind.OPTIONAL:
            label += " (opt)"
        elif task.kind == TaskKind.REQUEST:
            label += " (req)"

        ax.text(-0.02 * (max_time - min_time), y_pos, label,
                ha='right', va='center', fontsize=9)

        # Show ranges as text on the right
        range_text = []
        if start_min != 0 or start_max != tn.endTime:
            range_text.append(f"s:[{start_min},{start_max}]")
        if end_min != start_min or end_max != tn.endTime:
            range_text.append(f"e:[{end_min},{end_max}]")
        if dur_min != 0 or dur_max != (tn.endTime - start_min):
            range_text.append(f"d:[{dur_min},{dur_max}]")

        if range_text:
            ax.text(end_max + 0.01 * (max_time - min_time), y_pos,
                   " ".join(range_text),
                   ha='left', va='center', fontsize=8, style='italic',
                   color='gray')

    # Set up axes
    ax.set_ylim(-1, len(tasks))
    ax.set_xlim(min_time - 0.05 * (max_time - min_time),
                max_time + 0.15 * (max_time - min_time))

    ax.set_xlabel('Time', fontsize=11, fontweight='bold')
    ax.set_title(f'Temporal Range Specification: {tn.id}',
                fontsize=13, fontweight='bold', pad=15)

    # Remove y-axis ticks (we have labels on the left)
    ax.set_yticks([])

    # Grid
    ax.grid(axis='x', alpha=0.3, linestyle='--')

    # Legend - placed below the x-axis label so the two don't overlap
    legend_text = [
        'Light box: Full possible window (earliest start → latest end)',
        'Dark box: Core window (latest start → earliest end)',
    ]
    if infeasible_tasks:
        legend_text.append(
            'Red hatch: over-constrained (no feasible window): '
            + ', '.join(infeasible_tasks))
    ax.annotate('\n'.join(legend_text),
                xy=(0.5, 0), xycoords='axes fraction',
                xytext=(0, -42), textcoords='offset points',
                ha='center', va='top',
                fontsize=9, style='italic',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))

    # tight_layout can warn when long right-side annotations don't fit; the
    # final savefig uses bbox_inches='tight' anyway, so suppress the noise.
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plt.tight_layout()

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=100, bbox_inches='tight')
    plt.close()

    return True


def main():
    """CLI interface."""
    import argparse
    from tasknet_parser import parse_tasknet_file
    from tasknet_transforms import apply_transforms

    parser = argparse.ArgumentParser(
        description="Visualize temporal ranges from TaskNet specification"
    )
    parser.add_argument('tasknet_file', help='Path to .tn file')
    parser.add_argument('output', nargs='?', default=None,
                       help='Output PNG path')
    args = parser.parse_args()

    # Parse and transform
    tn = parse_tasknet_file(args.tasknet_file)
    tn, _ = apply_transforms(tn)

    # Determine output path
    if args.output is None:
        src = Path(args.tasknet_file)
        out_dir = src.parent / 'visualizations'
        output_path = out_dir / f"{src.stem}_temporal.png"
    else:
        output_path = Path(args.output)

    print(f"Generating temporal range visualization for {tn.id}...")
    success = create_temporal_range_visualization(tn, str(output_path))

    if success:
        print(f"  → {output_path}")
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
