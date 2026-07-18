#!/usr/bin/env python3
"""
Static TaskNet structure visualization.

Renders the STRUCTURE of a tasknet *specification* (as opposed to a solved
schedule) as TWO Graphviz images:

  Graph 1 - Task / taskdef relations  (<base>_relations.png):
      nodes  = tasks + taskdefs (styled by TaskKind)
      edges  = after, containedin, instance->taskdef (defines),
               mutex (no-overlap), sequence (ordering chain)

  Graph 2 - Task <-> timeline interactions  (<base>_timelines.png):
      nodes  = tasks + timelines (timelines shaped by type)
      edges  = impacts (writes, colored by pre/maint/post) and
               pre/inv/post reads
      layout = bipartite: tasks in the left column, timelines in the right

The two graphs share no edges, so rendering them separately (rather than as two
panels on one canvas) gives each natural, readable proportions.

IMPORTANT: this operates on the RAW parsed AST (parse only, NOT apply_transforms).
mutex/sequence survive as TLMutex/TLSequence only before desugaring, so callers
must pass a pre-transform TaskNet to see those edges.

Usage as script:
    python src/smt/tasknet_structure_viz.py foo.tn [output.png]

Usage as module:
    from tasknet_structure_viz import create_structure_visualization
    create_structure_visualization(tn, "structure.png")
"""

from __future__ import annotations

import sys
import argparse
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass

from tasknet_ast import (
    TaskNet, Task, TaskKind, Timeline,
    StateTimeline, AtomicTimeline, RateTimeline, CumulativeTimeline, ClaimableTimeline,
    Impact, ImpactAssign, ImpactCumulative, ImpactRateCumulative, ImpactRateAssignment,
    TlCon, ConVal, ConIntRange, ConRealRange,
    IntVal, RealVal, StrVal, BoolVal, ParamRef,
    AfterDependency, ContainedinDependency,
    Formula, TLMutex, TLSequence,
    TLAnd, TLOr, TLNot, TLImplies, TLAlways, TLEventually, TLSoFar, TLOnce,
    TLUntil, TLSince,
)


# ============================================================================
# DOT primitives
# ============================================================================

@dataclass
class Node:
    id: str
    label: str
    shape: str = "box"
    fillcolor: str = "white"
    style: str = "filled"


@dataclass
class Edge:
    from_id: str
    to_id: str
    label: str = ""
    style: str = "solid"
    color: str = "black"
    dir: str = "forward"  # "forward" | "none" (for symmetric mutex edges)


def _esc(text: str) -> str:
    """Escape a string for a DOT double-quoted label.

    Real newline characters are converted to the DOT newline escape `\\n`.
    Labels in this module use actual "\n" characters (not the two-char sequence)
    so that this is the single place newlines are rendered.
    """
    return (text.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n"))


def _fmt_value(v) -> str:
    """Render a Value wrapper as a short string."""
    if isinstance(v, (IntVal, RealVal)):
        return str(v.v)
    if isinstance(v, StrVal):
        return v.v
    if isinstance(v, BoolVal):
        return "true" if v.v else "false"
    if isinstance(v, ParamRef):
        return v.name
    return str(v)


def _fmt_gap(gap) -> str:
    """Label for an after-dependency gap IntRange."""
    if gap is None:
        return "after"
    return f"after [{gap.low}, {gap.high}]"


def _fmt_containedin(dep: ContainedinDependency) -> str:
    """Label for a containedin dependency with optional offsets."""
    parts = []
    if dep.start_offset is not None:
        parts.append(f"s[{dep.start_offset.low}, {dep.start_offset.high}]")
    if dep.end_offset is not None:
        parts.append(f"e[{dep.end_offset.low}, {dep.end_offset.high}]")
    return "containedin" + ((" " + " ".join(parts)) if parts else "")


# ============================================================================
# Panel 1: task / taskdef relations
# ============================================================================

# matplotlib "Set3" palette (hex), used by the Gantt / timeline-evolution charts.
# Kept in sync here so a task colored teal in the schedule chart is teal here too.
_SET3 = [
    "#8dd3c7", "#ffffb3", "#bebada", "#fb8072", "#80b1d3", "#fdb462",
    "#b3de69", "#fccde5", "#d9d9d9", "#bc80bd", "#ccebc5", "#ffed6f",
]


def _taskdef_color_map(tn: TaskNet) -> dict:
    """Map each task id -> a Set3 color keyed by its taskdef family.

    Mirrors the schedule charts (tasknet_gantt.py / tasknet_timeline_viz.py):
    each task belongs to the family `task.definition or task.id`; families are
    sorted and indexed into Set3 so all instances of a taskdef share a color.
    Taskdef DEFINITION nodes get the same color as their instances.
    """
    family = {}
    for task in tn.tasks:
        # A taskdef instance -> its definition; a taskdef itself or a bare task -> own id.
        family[task.id] = task.definition if task.definition else task.id
    unique = sorted(set(family.values()))
    fam_color = {fam: _SET3[i % len(_SET3)] for i, fam in enumerate(unique)}
    return {tid: fam_color[fam] for tid, fam in family.items()}


def _task_node(task: Task, color_map: dict) -> Node:
    label = task.id

    # Add range information if available
    range_info = []
    if task.startrng:
        range_info.append(f"start: [{task.startrng.low}, {task.startrng.high}]")
    if task.endrng:
        range_info.append(f"end: [{task.endrng.low}, {task.endrng.high}]")
    if task.durrng:
        range_info.append(f"dur: [{task.durrng.low}, {task.durrng.high}]")

    if range_info:
        label += "\n" + "\n".join(range_info)

    # Taskdef DEFINITION nodes are drawn double-bordered; optional/request noted in label.
    if task.kind == TaskKind.DEFINITION:
        label += "\n(taskdef)"
        style = "filled,rounded,bold"
    elif task.kind == TaskKind.OPTIONAL:
        label += "\n(optional)"
        style = "filled,rounded,dashed"
    elif task.kind == TaskKind.REQUEST:
        label += "\n(request)"
        style = "filled,rounded,dashed"
    else:
        style = "filled,rounded"
    fill = color_map.get(task.id, "white")
    return Node(id=task.id, label=label, shape="box", fillcolor=fill, style=style)


def _iter_after(task: Task):
    """Yield (AfterDependency) from both instance- and definition-level lists."""
    for lst in (task.after_instances, task.after_definitions):
        if lst:
            for dep in lst:
                yield dep


def _iter_containedin(task: Task):
    for lst in (task.containedin_instances, task.containedin_definitions):
        if lst:
            for dep in lst:
                yield dep


def _mutex_edges_from_formula(f: Formula, taskdef_ids: set,
                              edges: List[Edge], seen: set) -> None:
    """Walk a (pre-transform) formula, emitting symmetric mutex edges and
    directed sequence edges. Operates at the OPERAND level: taskdef operands are
    drawn as-is (a taskdef node), not expanded to instances, which keeps the
    static view compact.
    """
    if isinstance(f, TLMutex):
        def pairs():
            if f.group_b is None:
                if f.cross_only:
                    # cross-only: only pairs across distinct operands
                    ops = f.group_a
                    for i in range(len(ops)):
                        for j in range(i + 1, len(ops)):
                            yield ops[i], ops[j]
                else:
                    # flatten all pairs
                    ops = f.group_a
                    for i in range(len(ops)):
                        for j in range(i + 1, len(ops)):
                            yield ops[i], ops[j]
            else:
                for a in f.group_a:
                    for b in f.group_b:
                        yield a, b

        label = "mutex" + (" (cross)" if (f.group_b is None and f.cross_only) else "")
        for a, b in pairs():
            key = ("mutex", frozenset((a, b)))
            if key in seen:
                continue
            seen.add(key)
            edges.append(Edge(from_id=a, to_id=b, label=label,
                              style="bold", color="red", dir="none"))
    elif isinstance(f, TLSequence):
        tasks = f.tasks
        for i in range(len(tasks) - 1):
            edges.append(Edge(from_id=tasks[i], to_id=tasks[i + 1],
                              label="sequence", style="solid", color="darkorange"))
    # Recurse into compound formulas so mutex/sequence nested in and/or/etc. show.
    elif isinstance(f, (TLAnd, TLOr, TLUntil, TLSince, TLImplies)):
        _mutex_edges_from_formula(f.left, taskdef_ids, edges, seen)
        _mutex_edges_from_formula(f.right, taskdef_ids, edges, seen)
    elif isinstance(f, (TLNot, TLAlways, TLEventually, TLSoFar, TLOnce)):
        _mutex_edges_from_formula(f.sub, taskdef_ids, edges, seen)


def build_task_relation_graph(tn: TaskNet) -> Tuple[List[Node], List[Edge]]:
    """Panel 1: task/taskdef nodes and after/containedin/defines/mutex/sequence edges."""
    nodes: List[Node] = []
    edges: List[Edge] = []
    task_ids = {t.id for t in tn.tasks}
    taskdef_ids = {t.id for t in tn.tasks if t.kind == TaskKind.DEFINITION}
    color_map = _taskdef_color_map(tn)

    for task in tn.tasks:
        nodes.append(_task_node(task, color_map))

    for task in tn.tasks:
        # instance -> taskdef (defines/of)
        if task.definition and task.definition in task_ids:
            edges.append(Edge(from_id=task.id, to_id=task.definition,
                              label="of", style="dotted", color="gray"))

        # after (dependent -> prerequisite)
        for dep in _iter_after(task):
            if dep.task_id in task_ids:
                edges.append(Edge(from_id=task.id, to_id=dep.task_id,
                                  label=_fmt_gap(dep.gap), style="solid", color="blue"))

        # containedin (child -> parent)
        for dep in _iter_containedin(task):
            if dep.task_id in task_ids:
                edges.append(Edge(from_id=task.id, to_id=dep.task_id,
                                  label=_fmt_containedin(dep), style="dashed", color="purple"))

    # mutex / sequence from constraints + properties (pre-transform formulas)
    seen: set = set()
    for prop in list(tn.constraints) + list(tn.properties):
        _mutex_edges_from_formula(prop.formula, taskdef_ids, edges, seen)

    return nodes, edges


# ============================================================================
# Panel 2: task <-> timeline interactions
# ============================================================================

def _timeline_node(tl: Timeline) -> Node:
    tid = tl.id
    if isinstance(tl, StateTimeline):
        return Node(tid, f"{tid}\nstate", shape="hexagon", fillcolor="yellow", style="filled")
    if isinstance(tl, AtomicTimeline):
        return Node(tid, f"{tid}\natomic", shape="diamond", fillcolor="plum", style="filled")
    if isinstance(tl, RateTimeline):
        return Node(tid, f"{tid}\nrate", shape="box", fillcolor="lightcoral", style="filled,rounded")
    if isinstance(tl, CumulativeTimeline):
        return Node(tid, f"{tid}\ncumulative", shape="box", fillcolor="lightcyan", style="filled,rounded")
    if isinstance(tl, ClaimableTimeline):
        return Node(tid, f"{tid}\nclaimable", shape="oval", fillcolor="pink", style="filled")
    return Node(tid, f"{tid}", shape="box", fillcolor="gray", style="filled")


def _impact_op(impact: Impact) -> str:
    how = impact.how
    if isinstance(how, ImpactAssign):
        return f"= {_fmt_value(how.v)}"
    if isinstance(how, ImpactCumulative):
        return f"+= {how.v}"
    if isinstance(how, ImpactRateCumulative):
        return f"+~ {how.delta}"
    if isinstance(how, ImpactRateAssignment):
        return f"=~ {how.r}"
    return "?"


_WHEN_COLOR = {"pre": "green", "maint": "blue", "post": "red"}


def build_timeline_interaction_graph(tn: TaskNet) -> Tuple[List[Node], List[Edge]]:
    """Panel 2: task + timeline nodes; impact (write) and pre/inv/post (read) edges."""
    nodes: List[Node] = []
    edges: List[Edge] = []
    timeline_ids = {tl.id for tl in tn.timelines}
    color_map = _taskdef_color_map(tn)

    # Task nodes: same taskdef-family color as the schedule charts and Panel 1.
    for task in tn.tasks:
        nodes.append(Node(id=task.id, label=task.id, shape="box",
                          fillcolor=color_map.get(task.id, "white"),
                          style="filled,rounded"))
    for tl in tn.timelines:
        nodes.append(_timeline_node(tl))

    for task in tn.tasks:
        # reads: pre / inv / post
        for when, conlist in (("pre", task.pre), ("inv", task.inv), ("post", task.post)):
            if not conlist:
                continue
            for tlcon in conlist:
                if tlcon.id in timeline_ids:
                    edges.append(Edge(from_id=task.id, to_id=tlcon.id,
                                      label=f"{when} (read)", style="dotted",
                                      color="gray40"))
        # writes: impacts
        if task.impacts:
            for imp in task.impacts:
                if imp.id in timeline_ids:
                    edges.append(Edge(from_id=task.id, to_id=imp.id,
                                      label=f"{imp.when}: {_impact_op(imp)}",
                                      style="solid",
                                      color=_WHEN_COLOR.get(imp.when, "black")))

    return nodes, edges


# ============================================================================
# DOT generation
#
# The structure is rendered as TWO separate graphs (each its own image) rather
# than two panels in one canvas: the panels share no edges, so Graphviz would
# stack them into a tall, cramped strip. Separate graphs each get natural,
# readable proportions.
# ============================================================================

def _prepare(tn: TaskNet) -> TaskNet:
    """Expand TaskRange nodes into concrete Task instances before building graphs.

    The pre-transform AST may contain TaskRange nodes (e.g. `task T[2..4]`), which
    have no `.kind`/dependency fields. `expand_task_ranges` turns them into Task
    instances WITHOUT desugaring mutex/sequence, so those edges remain visible.
    Falls back to dropping any residual TaskRange nodes if expansion is unavailable.
    """
    try:
        import copy
        from tasknet_transforms import expand_task_ranges
        return expand_task_ranges(copy.deepcopy(tn))
    except Exception:
        from tasknet_ast import Task
        tn.tasks = [t for t in tn.tasks if isinstance(t, Task)]
        return tn


def _node_line(n: Node) -> str:
    return (f'  "{n.id}" [label="{_esc(n.label)}", shape={n.shape}, '
            f'fillcolor="{n.fillcolor}", style="{n.style}"];')


def _edge_line(e: Edge) -> str:
    attrs = [f'color="{e.color}"']
    if e.label:
        attrs.append(f'label="{_esc(e.label)}"')
        attrs.append(f'fontcolor="{e.color}"')
    if e.style != "solid":
        attrs.append(f'style={e.style}')
    if e.dir != "forward":
        attrs.append(f'dir={e.dir}')
    return f'  "{e.from_id}" -> "{e.to_id}" [{", ".join(attrs)}];'


def generate_relations_dot(tn: TaskNet) -> str:
    """Graph 1: task / taskdef relations (after, containedin, of, mutex, sequence)."""
    nodes, edges = build_task_relation_graph(_prepare(tn))

    lines: List[str] = []
    lines.append("digraph tasknet_relations {")
    # No graph-level label: the title is supplied by the HTML card header / CLI
    # caption, avoiding a duplicated title in a mismatched font.
    lines.append('  dpi=78;')
    lines.append('  rankdir=LR;')
    lines.append('  splines=true;')
    lines.append('  overlap=false;')
    lines.append('  node [fontname="Helvetica", fontsize=10, margin="0.11,0.055"];')
    lines.append('  edge [fontname="Helvetica", fontsize=9];')
    lines.append('  nodesep=0.3;')
    lines.append('  ranksep=0.9;')
    lines.append('')
    for n in nodes:
        lines.append(_node_line(n))
    lines.append('')
    for e in edges:
        lines.append(_edge_line(e))
    lines.append("}")
    return "\n".join(lines)


def generate_timeline_dot(tn: TaskNet) -> str:
    """Graph 2: task <-> timeline interactions, laid out as a clean bipartite
    graph (tasks on the left column, timelines on the right)."""
    tn = _prepare(tn)
    nodes, edges = build_timeline_interaction_graph(tn)
    timeline_ids = {tl.id for tl in tn.timelines}
    task_ids = [t.id for t in tn.tasks]

    lines: List[str] = []
    lines.append("digraph tasknet_timelines {")
    # No graph-level label: title comes from the HTML card header / CLI caption.
    lines.append('  dpi=78;')
    lines.append('  rankdir=LR;')
    lines.append('  splines=true;')
    lines.append('  concentrate=true;')  # merge shared edge segments -> less spaghetti
    lines.append('  node [fontname="Helvetica", fontsize=10, margin="0.11,0.055"];')
    lines.append('  edge [fontname="Helvetica", fontsize=8];')
    lines.append('  nodesep=0.22;')
    lines.append('  ranksep=1.6;')
    lines.append('')
    for n in nodes:
        lines.append(_node_line(n))
    lines.append('')
    # Pin the two columns: tasks at the source rank, timelines at the sink rank.
    if task_ids:
        lines.append('  { rank=source; ' + " ".join(f'"{t}";' for t in task_ids) + ' }')
    if timeline_ids:
        lines.append('  { rank=sink; ' + " ".join(f'"{t}";' for t in sorted(timeline_ids)) + ' }')
    lines.append('')
    for e in edges:
        lines.append(_edge_line(e))
    lines.append("}")
    return "\n".join(lines)


# ============================================================================
# Rendering
# ============================================================================

def check_dot_available() -> bool:
    """Return True if the Graphviz `dot` binary is available."""
    try:
        subprocess.run(['dot', '-V'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _render(dot_text: str, out_png: Path) -> bool:
    """Write a .dot next to out_png and render it to PNG. Returns success."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    dot_path = out_png.with_suffix('.dot')
    with open(dot_path, 'w') as f:
        f.write(dot_text)
    try:
        subprocess.run(['dot', '-Tpng', str(dot_path), '-o', str(out_png)],
                       capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Failed to render {out_png.name}: {e}", file=sys.stderr)
        return False


def _load_title_font(size: int):
    """Best-effort load of a bold TrueType font for panel titles; fall back to
    PIL's default bitmap font if none of the common paths resolve."""
    from PIL import ImageFont
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",   # macOS
        "/System/Library/Fonts/Helvetica.ttc",                 # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _compose_side_by_side(left_png: Path, right_png: Path, out_png: Path,
                          left_title: str = "", right_title: str = "",
                          gap: int = 90, pad: int = 20, title_h: int = 34,
                          bg=(255, 255, 255)) -> bool:
    """Composite two PNGs side by side into one image at NATIVE resolution, with
    a title over each panel and a divider line between them.

    Rendering both panels into a single image guarantees a shared scale, so a
    node box in the left panel is exactly the same on-screen size as one in the
    right panel (two separate <img> tags would each scale independently).
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    left = Image.open(left_png).convert("RGBA")
    right = Image.open(right_png).convert("RGBA")

    panels_top = pad + (title_h if (left_title or right_title) else 0)
    left_x = pad
    right_x = pad + left.width + gap
    width = right_x + right.width + pad
    height = panels_top + max(left.height, right.height) + pad

    canvas = Image.new("RGBA", (width, height), bg + (255,))
    canvas.paste(left, (left_x, panels_top), left)
    canvas.paste(right, (right_x, panels_top), right)

    draw = ImageDraw.Draw(canvas)

    # Vertical divider centered in the gap between the two panels.
    divider_x = pad + left.width + gap // 2
    draw.line([(divider_x, pad), (divider_x, height - pad)],
              fill=(210, 210, 210, 255), width=2)

    # Centered title above each panel.
    if left_title or right_title:
        font = _load_title_font(19)

        def _centered(text: str, region_x: int, region_w: int):
            if not text:
                return
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            tx = region_x + max(0, (region_w - tw) // 2)
            draw.text((tx, pad // 2), text, fill=(40, 40, 40, 255), font=font)

        _centered(left_title, left_x, left.width)
        _centered(right_title, right_x, right.width)

    canvas.convert("RGB").save(out_png)
    return True


def create_structure_visualization(tn: TaskNet, output_path: str) -> List[str]:
    """Render the structure of a (pre-transform) TaskNet to a single PNG.

    Two graphs are drawn — task/taskdef relations and task<->timeline
    interactions — then composited side by side into `output_path` so both share
    one scale (equal box sizes) and appear next to each other.

    Returns the list of created PNG paths (empty if Graphviz `dot` is
    unavailable), so callers can degrade gracefully. If PIL is missing, falls
    back to writing the two panels as separate files.
    """
    if not check_dot_available():
        print("⚠️  Structure visualization skipped (Graphviz 'dot' not found)")
        return []

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Note: the generate_*_dot functions each call _prepare() to expand ranges.
    rel_png = out.with_name(f"{out.stem}_relations.png")
    tl_png = out.with_name(f"{out.stem}_timelines.png")
    ok_rel = _render(generate_relations_dot(tn), rel_png)
    ok_tl = _render(generate_timeline_dot(tn), tl_png)
    if not (ok_rel and ok_tl):
        return [str(p) for p, ok in ((rel_png, ok_rel), (tl_png, ok_tl)) if ok]

    # Composite into a single side-by-side image; clean up the intermediates.
    if _compose_side_by_side(rel_png, tl_png, out,
                             left_title="Task / taskdef relations",
                             right_title="Task ↔ timeline interactions"):
        rel_png.unlink(missing_ok=True)
        tl_png.unlink(missing_ok=True)
        out.with_name(f"{out.stem}_relations.dot").unlink(missing_ok=True)
        out.with_name(f"{out.stem}_timelines.dot").unlink(missing_ok=True)
        return [str(out)]
    # PIL unavailable: keep the two separate panels.
    return [str(rel_png), str(tl_png)]


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Visualize the static structure of a TaskNet specification."
    )
    parser.add_argument('tasknet_file', help='Path to .tn tasknet file')
    parser.add_argument('output', nargs='?', default=None,
                        help='Output PNG path (default: <dir>/visualizations/<name>_structure.png)')
    args = parser.parse_args()

    # Parse ONLY - no apply_transforms, so mutex/sequence remain visible.
    from tasknet_parser import parse_tasknet_file
    try:
        tn = parse_tasknet_file(args.tasknet_file)
    except Exception as e:
        print(f"Error parsing {args.tasknet_file}: {e}", file=sys.stderr)
        sys.exit(1)

    src = Path(args.tasknet_file)
    if args.output is None:
        out_dir = src.parent / 'visualizations'
        output_path = out_dir / f"{src.stem}_structure.png"
    else:
        output_path = Path(args.output)

    print(f"Generating structure visualization for {tn.id}...")
    created = create_structure_visualization(tn, str(output_path))
    if created:
        for p in created:
            print(f"  → {p}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
