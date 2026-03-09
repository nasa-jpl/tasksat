#!/usr/bin/env python3
"""
TaskNet Visualization Tool

Generates Graphviz DOT files for visualizing TaskNet schedules:
1. Task dependency graph (task relationships: after, containedin)
2. Task-timeline interaction graph (constraints and impacts)

Usage:
    python src/smt/tasknet_visualize.py <file.tn> [--detail] [--output-dir DIR]
"""

from __future__ import annotations
import sys
import os
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Set, Tuple
from dataclasses import dataclass

# Import TaskNet parser and AST
from tasknet_parser import parse_tasknet_file
from tasknet_ast import (
    TaskNet, Task, TaskKind,
    Timeline, StateTimeline, AtomicTimeline, ClaimableTimeline,
    CumulativeTimeline, RateTimeline,
    Impact, ImpactAssign, ImpactCumulative, ImpactRate,
    TlCon, ConVal, ConRealRange, ConIntRange,
    IntVal, RealVal, StrVal, BoolVal
)


# ============================================================================
# GRAPH DATA STRUCTURES
# ============================================================================

@dataclass
class Node:
    """Graph node with styling information"""
    id: str
    label: str
    shape: str = "box"
    color: str = "black"
    fillcolor: str = "white"
    style: str = "filled"


@dataclass
class Edge:
    """Graph edge with styling information"""
    from_id: str
    to_id: str
    label: str = ""
    style: str = "solid"
    color: str = "black"
    arrowhead: str = "normal"


# ============================================================================
# TASK DEPENDENCY GRAPH EXTRACTION
# ============================================================================

def find_implicit_dependencies(tasknet: TaskNet) -> List[Tuple[str, str, str]]:
    """
    Find implicit task ordering from boolean/atomic timeline patterns.

    Returns list of (prerequisite_task, dependent_task, timeline_name) tuples where:
    - prerequisite_task sets timeline to a value in post
    - dependent_task requires that value in pre
    - Therefore prerequisite_task must execute before dependent_task
    """
    implicit_deps = []

    # Build mapping: timeline → {value → tasks that require it in pre}
    pre_requires: Dict[str, Dict[str, List[str]]] = {}
    for task in tasknet.tasks:
        if task.kind == TaskKind.DEFINITION:
            continue
        if task.pre:
            for tlcon in task.pre:
                timeline_id = tlcon.id
                # Get required value(s)
                for con in tlcon.cons:
                    if isinstance(con, ConVal):
                        val = _format_value(con.v)
                        if timeline_id not in pre_requires:
                            pre_requires[timeline_id] = {}
                        if val not in pre_requires[timeline_id]:
                            pre_requires[timeline_id][val] = []
                        pre_requires[timeline_id][val].append(task.id)

    # Find tasks that set timeline values in post
    for task in tasknet.tasks:
        if task.kind == TaskKind.DEFINITION:
            continue
        if task.impacts:
            for impact in task.impacts:
                if impact.when == "post" and isinstance(impact.how, ImpactAssign):
                    timeline_id = impact.id
                    val = _format_value(impact.how.v)

                    # Check if any tasks require this value
                    if timeline_id in pre_requires and val in pre_requires[timeline_id]:
                        for dependent_task in pre_requires[timeline_id][val]:
                            if dependent_task != task.id:  # Don't self-reference
                                implicit_deps.append((task.id, dependent_task, timeline_id))

    return implicit_deps


def build_task_dependency_graph(tasknet: TaskNet, detail: bool, show_definitions: bool = False) -> Tuple[List[Node], List[Edge]]:
    """
    Extract task dependency graph from TaskNet.

    Returns nodes (tasks) and edges (dependencies: after, containedin, implicit).

    Args:
        tasknet: Parsed TaskNet
        detail: Include detailed information (ranges, priorities)
        show_definitions: Include task definitions (templates) in graph
    """
    nodes = []
    edges = []

    # Find implicit dependencies from boolean/atomic timeline patterns
    implicit_deps = find_implicit_dependencies(tasknet)

    for task in tasknet.tasks:
        # Skip definitions if not requested
        if not show_definitions and task.kind == TaskKind.DEFINITION:
            continue

        # Create node for this task
        node = _create_task_node(task, detail)
        nodes.append(node)

        # Add edges for task relationships

        # 1. Instance -> Definition relationship (only if showing definitions)
        if show_definitions and task.definition:
            edges.append(Edge(
                from_id=task.id,
                to_id=task.definition,
                label="instance of",
                style="dotted",
                color="gray"
            ))

        # 2. After relationships (dependency direction: dependent → prerequisite)
        if task.after:
            for prerequisite in task.after:
                edges.append(Edge(
                    from_id=task.id,           # dependent task
                    to_id=prerequisite,        # prerequisite task
                    label="after",
                    style="solid",
                    color="blue"
                ))

        # 3. ContainedIn relationships (hierarchical)
        if task.containedin:
            for container in task.containedin:
                edges.append(Edge(
                    from_id=task.id,
                    to_id=container,
                    label="contained in",
                    style="dashed",
                    color="purple"
                ))

    # 4. Add implicit dependency edges from boolean/atomic timeline patterns
    for (prerequisite_task, dependent_task, timeline) in implicit_deps:
        edges.append(Edge(
            from_id=dependent_task,      # dependent task
            to_id=prerequisite_task,     # prerequisite task (sets the timeline value)
            label=f"assumes {timeline}",
            style="dashed",
            color="darkgreen"
        ))

    return nodes, edges


def _create_task_node(task: Task, detail: bool) -> Node:
    """Create a styled node for a task"""
    # Base label
    label = task.id

    # Add details if requested
    if detail:
        details = []
        if task.durrng:
            details.append(f"dur: [{task.durrng.low}, {task.durrng.high}]")
        if task.startrng:
            details.append(f"start: [{task.startrng.low}, {task.startrng.high}]")
        if task.priority is not None:
            details.append(f"pri: {task.priority}")

        if details:
            label += "\\n" + "\\n".join(details)

    # Style based on task kind
    if task.kind == TaskKind.DEFINITION:
        fillcolor = "lightblue"
        shape = "box"
    elif task.kind == TaskKind.OPTIONAL:
        fillcolor = "orange"
        shape = "box"
    else:  # INSTANCE
        fillcolor = "lightgreen"
        shape = "box"

    return Node(
        id=task.id,
        label=label,
        shape=shape,
        fillcolor=fillcolor,
        style="filled"
    )


# ============================================================================
# TIMELINE INTERACTION GRAPH EXTRACTION
# ============================================================================

def build_timeline_interaction_graph(tasknet: TaskNet, detail: bool) -> Tuple[List[Node], List[Edge]]:
    """
    Extract task-timeline interaction graph from TaskNet.

    Returns nodes (tasks + timelines) and edges (constraints + impacts).
    """
    nodes = []
    edges = []

    # Add task nodes
    for task in tasknet.tasks:
        node = _create_task_node(task, detail=False)  # Simple labels for this view
        nodes.append(node)

    # Add timeline nodes
    for timeline in tasknet.timelines:
        node = _create_timeline_node(timeline, detail)
        nodes.append(node)

    # Add edges for task-timeline interactions
    for task in tasknet.tasks:
        # Constraints (reads)
        if task.pre:
            for tlcon in task.pre:
                edges.append(_create_constraint_edge(task.id, tlcon, "pre", detail))

        if task.inv:
            for tlcon in task.inv:
                edges.append(_create_constraint_edge(task.id, tlcon, "inv", detail))

        if task.post:
            for tlcon in task.post:
                edges.append(_create_constraint_edge(task.id, tlcon, "post", detail))

        # Impacts (writes)
        if task.impacts:
            for impact in task.impacts:
                edges.append(_create_impact_edge(task.id, impact, detail))

    return nodes, edges


def _create_timeline_node(timeline: Timeline, detail: bool) -> Node:
    """Create a styled node for a timeline"""
    label = timeline.id

    # Add type and details
    if isinstance(timeline, StateTimeline):
        tl_type = "state"
        shape = "hexagon"
        fillcolor = "yellow"
        if detail:
            states_str = ", ".join(timeline.states[:3])
            if len(timeline.states) > 3:
                states_str += "..."
            label += f"\\n{tl_type}\\n{states_str}"
        else:
            label += f"\\n{tl_type}"
    elif isinstance(timeline, AtomicTimeline):
        tl_type = "atomic"
        shape = "diamond"
        fillcolor = "plum"
        label += f"\\n{tl_type}"
    elif isinstance(timeline, RateTimeline):
        tl_type = "rate"
        shape = "box"
        fillcolor = "lightcoral"
        if detail:
            label += f"\\n{tl_type}\\n[{timeline.range.low}, {timeline.range.high}]"
        else:
            label += f"\\n{tl_type}"
    elif isinstance(timeline, CumulativeTimeline):
        tl_type = "cumulative"
        shape = "box"
        fillcolor = "lightcyan"
        if detail:
            label += f"\\n{tl_type}\\n[{timeline.range.low}, {timeline.range.high}]"
        else:
            label += f"\\n{tl_type}"
    elif isinstance(timeline, ClaimableTimeline):
        tl_type = "claimable"
        shape = "oval"
        fillcolor = "pink"
        if detail:
            label += f"\\n{tl_type}\\n[{timeline.range.low}, {timeline.range.high}]"
        else:
            label += f"\\n{tl_type}"
    else:
        tl_type = "unknown"
        shape = "box"
        fillcolor = "gray"
        label += f"\\n{tl_type}"

    return Node(
        id=timeline.id,
        label=label,
        shape=shape,
        fillcolor=fillcolor,
        style="filled,rounded" if shape == "box" else "filled"
    )


def _create_constraint_edge(task_id: str, tlcon: TlCon, when: str, detail: bool) -> Edge:
    """Create edge for a constraint (task reads timeline)"""
    label = when

    if detail:
        # Add constraint value details
        con_strs = []
        for con in tlcon.cons:
            if isinstance(con, ConVal):
                val = _format_value(con.v)
                con_strs.append(f"= {val}")
            elif isinstance(con, ConRealRange):
                con_strs.append(f"[{con.r.low}, {con.r.high}]")
            elif isinstance(con, ConIntRange):
                con_strs.append(f"[{con.r.low}, {con.r.high}]")

        if con_strs:
            label += ": " + ", ".join(con_strs)

    return Edge(
        from_id=task_id,
        to_id=tlcon.id,
        label=label,
        style="dotted",
        color="blue"
    )


def _create_impact_edge(task_id: str, impact: Impact, detail: bool) -> Edge:
    """Create edge for an impact (task writes timeline)"""
    # Determine operation string
    if isinstance(impact.how, ImpactAssign):
        op = f"= {_format_value(impact.how.v)}"
    elif isinstance(impact.how, ImpactCumulative):
        op = f"+= {impact.how.v}"
    elif isinstance(impact.how, ImpactRate):
        op = f"+~ {impact.how.r}"
    else:
        op = "?"

    label = f"{impact.when}: {op}" if detail else impact.when

    # Color by timing
    if impact.when == "pre":
        color = "green"
    elif impact.when == "maint":
        color = "blue"
    elif impact.when == "post":
        color = "red"
    else:
        color = "black"

    return Edge(
        from_id=task_id,
        to_id=impact.id,
        label=label,
        style="solid",
        color=color
    )


def _format_value(val) -> str:
    """Format a value for display"""
    if isinstance(val, IntVal):
        return str(val.v)
    elif isinstance(val, RealVal):
        return str(val.v)
    elif isinstance(val, BoolVal):
        return str(val.v).lower()
    elif isinstance(val, StrVal):
        return val.v
    else:
        return str(val)


# ============================================================================
# DOT FILE GENERATION
# ============================================================================

def generate_dot(nodes: List[Node], edges: List[Edge], title: str) -> str:
    """Generate DOT format string from nodes and edges"""
    lines = []
    lines.append("digraph tasknet {")
    lines.append(f'  label="{title}";')
    lines.append('  labelloc="t";')
    lines.append('  fontsize=16;')
    lines.append('  rankdir=LR;')
    lines.append('  node [fontname="Arial"];')
    lines.append('  edge [fontname="Arial"];')
    lines.append('')

    # Add nodes
    for node in nodes:
        attrs = [
            f'label="{node.label}"',
            f'shape={node.shape}',
            f'color="{node.color}"',
            f'fillcolor="{node.fillcolor}"',
            f'style="{node.style}"'
        ]
        lines.append(f'  "{node.id}" [{", ".join(attrs)}];')

    lines.append('')

    # Add edges
    for edge in edges:
        attrs = []
        if edge.label:
            attrs.append(f'label="{edge.label}"')
        if edge.style != "solid":
            attrs.append(f'style={edge.style}')
        if edge.color != "black":
            attrs.append(f'color="{edge.color}"')
        if edge.arrowhead != "normal":
            attrs.append(f'arrowhead={edge.arrowhead}')

        attr_str = f' [{", ".join(attrs)}]' if attrs else ""
        lines.append(f'  "{edge.from_id}" -> "{edge.to_id}"{attr_str};')

    lines.append('}')
    return '\n'.join(lines)


# ============================================================================
# RENDERING HELPERS
# ============================================================================

def check_dot_available() -> bool:
    """Check if Graphviz dot command is available"""
    try:
        subprocess.run(['dot', '-V'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def render_dot_to_png(dot_path: Path) -> bool:
    """Render DOT file to PNG using Graphviz dot command"""
    png_path = dot_path.with_suffix('.png')
    try:
        subprocess.run(['dot', '-Tpng', str(dot_path), '-o', str(png_path)],
                      capture_output=True, check=True)
        print(f"  → {png_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Warning: Failed to render {dot_path}: {e}", file=sys.stderr)
        return False


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Generate Graphviz DOT visualizations of TaskNet files'
    )
    parser.add_argument('tasknet_file', help='Path to .tn tasknet file')
    parser.add_argument('--detail', action='store_true',
                       help='Include detailed information (ranges, constraints, etc.)')
    parser.add_argument('--show-definitions', action='store_true',
                       help='Include task definitions (templates) in visualization')
    parser.add_argument('--output-dir', default=None,
                       help='Output directory for .dot files (default: visualizations/ in tasknet file directory)')

    args = parser.parse_args()

    # Parse tasknet file
    try:
        tasknet = parse_tasknet_file(args.tasknet_file)
    except Exception as e:
        print(f"Error parsing {args.tasknet_file}: {e}", file=sys.stderr)
        sys.exit(1)

    # Get base filename and determine output directory
    tasknet_path = Path(args.tasknet_file)
    base_name = tasknet_path.stem

    if args.output_dir is None:
        # Default: create visualizations/ in the same directory as the tasknet file
        output_dir = tasknet_path.parent / 'visualizations'
    else:
        output_dir = Path(args.output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate task dependency graph
    print(f"Generating task dependency graph...")
    task_nodes, task_edges = build_task_dependency_graph(tasknet, args.detail, args.show_definitions)
    task_dot = generate_dot(task_nodes, task_edges, f"{base_name} - Task Dependencies")

    task_dot_path = output_dir / f"{base_name}_tasks.dot"
    with open(task_dot_path, 'w') as f:
        f.write(task_dot)
    print(f"  → {task_dot_path}")

    # Generate timeline interaction graph
    print(f"Generating timeline interaction graph...")
    timeline_nodes, timeline_edges = build_timeline_interaction_graph(tasknet, args.detail)
    timeline_dot = generate_dot(timeline_nodes, timeline_edges, f"{base_name} - Task-Timeline Interactions")

    timeline_dot_path = output_dir / f"{base_name}_timeline_interactions.dot"
    with open(timeline_dot_path, 'w') as f:
        f.write(timeline_dot)
    print(f"  → {timeline_dot_path}")

    # Automatically render to PNG if dot is available
    if check_dot_available():
        print(f"\nRendering to PNG...")
        render_dot_to_png(task_dot_path)
        render_dot_to_png(timeline_dot_path)
        print("\nDone!")
    else:
        print("\nDone! Graphviz not found. To render as images:")
        print(f"  dot -Tpng {task_dot_path} -o {output_dir / f'{base_name}_tasks.png'}")
        print(f"  dot -Tpng {timeline_dot_path} -o {output_dir / f'{base_name}_timeline_interactions.png'}")


if __name__ == '__main__':
    main()
