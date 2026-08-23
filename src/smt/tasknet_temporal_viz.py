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

    # ------------------------------------------------------------------
    # Pass 1: resolve every task's geometry so the axis extent and the
    # right-hand label column can be laid out before anything is drawn.
    # ------------------------------------------------------------------
    horizon = tn.endTime or 1

    def _kind_suffix(task):
        """Label marker for a non-required task: ` (opt)`, ` (req)`, or nothing."""
        if task.kind == TaskKind.OPTIONAL:
            return " (opt)"
        if task.kind == TaskKind.REQUEST:
            return " (req)"
        return ""

    def _range_label(sm, sM, em, eM, dm, dM):
        """Compact constraint text; omit ranges that are just the full horizon."""
        parts = []
        if sm != 0 or sM != horizon:
            parts.append(f"s [{sm}, {sM}]")
        if em != 0 or eM != horizon:
            parts.append(f"e [{em}, {eM}]")
        if dm != 0 or dM != horizon:
            parts.append(f"d [{dm}, {dM}]")
        return "   ".join(parts)

    rows = []
    min_time = float('inf')
    max_time = 0
    for idx, task in enumerate(tasks):
        sm, sM, em, eM, dm, dM = _get_task_ranges(task, tn, propagated_bounds)
        feasible = sm <= sM and em <= eM
        rows.append({
            'task': task, 'y': len(tasks) - idx - 1,
            'color': color_map.get(task.id, '#cccccc'),
            'sm': sm, 'sM': sM, 'em': em, 'eM': eM, 'dm': dm, 'dM': dM,
            'feasible': feasible,
        })
        # Feasible windows drive the time axis; an inverted window contributes
        # only its (still finite) endpoints.
        min_time = min(min_time, sm, sM)
        max_time = max(max_time, em, eM)

    span = max(max_time - min_time, 1)
    infeasible_tasks = [r['task'].id for r in rows if not r['feasible']]

    # ------------------------------------------------------------------
    # Pass 2: draw. Thin, edgeless fills; a light "full possible window"
    # wash with a darker "core window" nested inside it.
    # ------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(14, max(6, len(tasks) * 0.55)))

    INK = '#2b2b2b'        # primary text
    MUTED = '#8a8a8a'      # secondary/label text
    DANGER = '#c0392b'     # infeasible
    full_h = 0.62          # full-window bar thickness
    core_h = 0.62          # core sits at same height, darker

    for r in rows:
        y, color = r['y'], r['color']
        sm, sM, em, eM = r['sm'], r['sM'], r['em'], r['eM']

        if not r['feasible']:
            # Over-constrained: a compact hatched danger marker, no misleading width.
            mx = min(sm, sM)
            mw = max(0.02 * span, 1)
            ax.add_patch(mpatches.Rectangle(
                (mx, y - full_h / 2), mw, full_h,
                facecolor='none', edgecolor=DANGER, hatch='xxx', linewidth=1.2))
            ax.text(-0.012 * span, y, r['task'].id + _kind_suffix(r['task']),
                    ha='right', va='center', fontsize=9, color=DANGER, fontweight='bold')
            continue

        # Full possible window (earliest start -> latest end): a light tint of
        # the hue. Alpha is high enough to stay visible on white (the pastel
        # Set3 hues wash out below ~0.5); a thin same-hue edge keeps very narrow
        # windows from disappearing.
        ax.add_patch(mpatches.Rectangle(
            (sm, y - full_h / 2), max(eM - sm, 0), full_h,
            facecolor=color, edgecolor=color, linewidth=0.5, alpha=0.55, zorder=2))

        # Core window (latest start -> earliest end): the guaranteed-overlap
        # region, drawn at full saturation so it reads clearly darker.
        if sM <= em:
            ax.add_patch(mpatches.Rectangle(
                (sM, y - core_h / 2), max(em - sM, 0), core_h,
                facecolor=color, edgecolor='none', alpha=1.0, zorder=3))

        # Task name (left gutter, ink).
        ax.text(-0.012 * span, y, r['task'].id + _kind_suffix(r['task']),
                ha='right', va='center', fontsize=9, color=INK)

    # ------------------------------------------------------------------
    # Right-hand constraint column: fixed x, left-aligned, tabular figures
    # so the bracketed numbers line up into a readable column.
    # ------------------------------------------------------------------
    label_x = max_time + 0.03 * span
    for r in rows:
        if not r['feasible']:
            txt = f"⚠ infeasible  s [{r['sm']}, {r['sM']}]  e [{r['em']}, {r['eM']}]"
            ax.text(label_x, r['y'], txt, ha='left', va='center',
                    fontsize=8, color=DANGER, family='monospace')
            continue
        txt = _range_label(r['sm'], r['sM'], r['em'], r['eM'], r['dm'], r['dM'])
        if txt:
            ax.text(label_x, r['y'], txt, ha='left', va='center',
                    fontsize=8, color=MUTED, family='monospace')

    # ------------------------------------------------------------------
    # Axes & chrome — recessive, hairline, solid.
    # ------------------------------------------------------------------
    ax.set_ylim(-1, len(tasks))
    ax.set_xlim(min_time - 0.04 * span, label_x + 0.30 * span)

    # Zero and horizon reference lines (faint, solid).
    for xref in (0, horizon):
        if min_time - 0.04 * span <= xref <= max_time + 0.02 * span:
            ax.axvline(xref, color='#c8c8c8', linewidth=1, zorder=1)
    ax.text(horizon, len(tasks) - 0.5, 'horizon', ha='center', va='bottom',
            fontsize=7.5, color=MUTED, style='italic')

    ax.set_xlabel('Time', fontsize=10, color=INK)
    ax.set_title(f'Temporal ranges — {tn.id}',
                 fontsize=13, fontweight='bold', color=INK, pad=12)
    ax.set_yticks([])

    # Solid hairline grid, one step off surface; drop the top/right spines.
    ax.grid(axis='x', color='#e6e6e6', linewidth=1, linestyle='-', zorder=0)
    ax.set_axisbelow(True)
    for side in ('top', 'right', 'left'):
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color('#c8c8c8')
    ax.tick_params(axis='x', colors=MUTED, labelsize=8, length=0)

    # Legend via proxy artists (robust vs. hand-placed annotations).
    handles = [
        mpatches.Patch(facecolor='#9e9e9e', alpha=0.35, edgecolor='none',
                       label='Full possible window (earliest start → latest end)'),
        mpatches.Patch(facecolor='#6e6e6e', alpha=0.9, edgecolor='none',
                       label='Core window (latest start → earliest end)'),
    ]
    if infeasible_tasks:
        handles.append(mpatches.Patch(facecolor='none', edgecolor=DANGER,
                                      hatch='xxx', label='Over-constrained (no feasible window)'))
    ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.10),
              ncol=len(handles), frameon=False, fontsize=8.5,
              handlelength=1.4, columnspacing=1.8, labelcolor=INK)

    # tight_layout can warn when long right-side labels don't fit; savefig uses
    # bbox_inches='tight' anyway, so suppress the noise.
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
