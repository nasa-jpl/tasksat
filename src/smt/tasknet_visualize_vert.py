#!/usr/bin/env python3
"""
TaskNet Visualization Tool - Timeline Layout

Generates Graphviz DOT visualizations of TaskNet files with:
- Vertical layout for task containment (container tasks above contained tasks)
- Horizontal layout for temporal ordering (earlier tasks to the left)
"""

import sys
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict, deque

from tasknet_parser import parse_tasknet_file
from tasknet_ast import TaskNet, Task, TaskKind, ImpactAssign, ConVal


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class TaskNode:
    """Represents a task node in the visualization"""
    id: str
    kind: TaskKind
    definition: Optional[str] = None
    temporal_rank: int = 0  # For left-to-right ordering
    container: Optional[str] = None  # Parent task if contained


@dataclass
class TaskEdge:
    """Represents an edge between tasks"""
    from_id: str
    to_id: str
    label: str
    edge_type: str  # 'after', 'containedin', 'assumes'
    style: str = "solid"
    color: str = "black"


# ============================================================================
# DEPENDENCY ANALYSIS
# ============================================================================

def find_implicit_dependencies(tasknet: TaskNet) -> List[Tuple[str, str, str]]:
    """
    Find implicit dependencies through timeline state changes.
    Returns list of (prerequisite_task, dependent_task, timeline) tuples.
    """
    from tasknet_ast import StrVal, BoolVal, IntVal, RealVal

    def extract_value(val_obj):
        """Extract actual value from Value wrapper objects"""
        if isinstance(val_obj, (StrVal, BoolVal, IntVal, RealVal)):
            return str(val_obj.v).lower() if isinstance(val_obj, BoolVal) else str(val_obj.v)
        return str(val_obj)

    # Build mapping from definition name to definition task
    definitions: Dict[str, Task] = {}
    for task in tasknet.tasks:
        if task.kind == TaskKind.DEFINITION:
            definitions[task.id] = task

    def get_impacts(task: Task):
        """Get impacts for a task, checking definition if needed"""
        if task.impacts:
            return task.impacts
        elif task.definition and task.definition in definitions:
            return definitions[task.definition].impacts
        return None

    def get_pre(task: Task):
        """Get pre constraints for a task, checking definition if needed"""
        if task.pre:
            return task.pre
        elif task.definition and task.definition in definitions:
            return definitions[task.definition].pre
        return None

    implicit_deps = []

    # Build mapping: timeline → {value → tasks that require it in pre}
    pre_requires: Dict[str, Dict[str, List[str]]] = {}

    for task in tasknet.tasks:
        if task.kind == TaskKind.DEFINITION:
            continue

        pre_constraints = get_pre(task)
        if pre_constraints:
            for tlcon in pre_constraints:
                timeline_id = tlcon.id
                for con in tlcon.cons:
                    if isinstance(con, ConVal):
                        val = extract_value(con.v)
                        if timeline_id not in pre_requires:
                            pre_requires[timeline_id] = {}
                        if val not in pre_requires[timeline_id]:
                            pre_requires[timeline_id][val] = []
                        pre_requires[timeline_id][val].append(task.id)

    # Find tasks that set timeline values in post
    for task in tasknet.tasks:
        if task.kind == TaskKind.DEFINITION:
            continue

        impacts = get_impacts(task)
        if impacts:
            for impact in impacts:
                if impact.when == "post" and isinstance(impact.how, ImpactAssign):
                    timeline_id = impact.id
                    val = extract_value(impact.how.v)

                    if timeline_id in pre_requires and val in pre_requires[timeline_id]:
                        for dependent_task in pre_requires[timeline_id][val]:
                            if dependent_task != task.id:
                                implicit_deps.append((task.id, dependent_task, timeline_id))

    return implicit_deps


def build_dependency_graph(tasknet: TaskNet, show_definitions: bool = False) -> Tuple[Dict[str, TaskNode], List[TaskEdge]]:
    """
    Build task dependency graph with temporal and containment relationships.
    Returns (nodes_dict, edges_list)
    """
    nodes: Dict[str, TaskNode] = {}
    edges: List[TaskEdge] = []

    # Create nodes for all tasks (excluding definitions unless requested)
    for task in tasknet.tasks:
        if task.kind == TaskKind.DEFINITION and not show_definitions:
            continue

        nodes[task.id] = TaskNode(
            id=task.id,
            kind=task.kind,
            definition=task.definition
        )

    # Find implicit dependencies
    implicit_deps = find_implicit_dependencies(tasknet)

    # Build edges
    for task in tasknet.tasks:
        if task.kind == TaskKind.DEFINITION and not show_definitions:
            continue

        # After dependencies (temporal)
        # Arrow shows: dependent_task -> prerequisite (dependency direction)
        # This means if B is after A, arrow goes B -> A
        if task.after:
            for prerequisite in task.after:
                if prerequisite in nodes:
                    edges.append(TaskEdge(
                        from_id=task.id,
                        to_id=prerequisite,
                        label="after",
                        edge_type="after",
                        style="solid",
                        color="blue"
                    ))

        # Containment relationships
        if task.containedin:
            for container in task.containedin:
                if container in nodes:
                    nodes[task.id].container = container
                    edges.append(TaskEdge(
                        from_id=task.id,
                        to_id=container,
                        label="containedin",
                        edge_type="containedin",
                        style="dashed",
                        color="purple"
                    ))

    # Add implicit dependencies (temporal)
    # Arrow shows: dependent_task -> prerequisite (dependency direction)
    for (prerequisite_task, dependent_task, timeline) in implicit_deps:
        if prerequisite_task in nodes and dependent_task in nodes:
            edges.append(TaskEdge(
                from_id=dependent_task,
                to_id=prerequisite_task,
                label=f"assumes {timeline}",
                edge_type="assumes",
                style="dashed",
                color="darkgreen"
            ))

    return nodes, edges


def compute_temporal_ranks(nodes: Dict[str, TaskNode], edges: List[TaskEdge]) -> None:
    """
    Compute temporal ranks for left-to-right ordering using topological sort.
    Modifies nodes in-place to set temporal_rank.

    Note: Since 'after' edges now point backward (dependent -> prerequisite),
    we reverse them for ranking purposes to get correct temporal order.
    """
    # Build adjacency list for temporal edges only (after, assumes)
    adj: Dict[str, List[str]] = defaultdict(list)
    in_degree: Dict[str, int] = defaultdict(int)

    # Initialize all nodes
    for node_id in nodes:
        in_degree[node_id] = 0

    # Build graph from temporal edges
    # Both 'after' and 'assumes' edges now point backward (dependent -> prerequisite)
    # We reverse them for ranking to get correct temporal order (earlier tasks to the left)
    for edge in edges:
        if edge.edge_type in ['after', 'assumes']:
            # Edge goes B -> A (dependency), but for ranking we want A before B
            adj[edge.to_id].append(edge.from_id)
            in_degree[edge.from_id] += 1

    # Topological sort using Kahn's algorithm
    queue = deque([node_id for node_id in nodes if in_degree[node_id] == 0])
    rank = 0

    while queue:
        # Process all nodes at current rank level
        level_size = len(queue)
        for _ in range(level_size):
            node_id = queue.popleft()
            nodes[node_id].temporal_rank = rank

            # Add successors
            for neighbor in adj[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        rank += 1


# ============================================================================
# DOT GENERATION
# ============================================================================

def _add_node(lines: List[str], node_id: str, node: TaskNode, is_container: bool):
    """Helper to add a node with appropriate styling"""
    color = "black"
    fillcolor = "lightgreen"

    if node.kind == TaskKind.OPTIONAL:
        fillcolor = "lightyellow"

    if is_container:
        fillcolor = "lightblue"
        style = "filled,bold"
        width = "2.5"
        height = "0.7"
    else:
        style = "filled"
        width = "2.0"
        height = "0.6"

    attrs = [
        f'label="{node_id}"',
        f'shape=box',
        f'color="{color}"',
        f'fillcolor="{fillcolor}"',
        f'style="{style}"',
        f'width={width}',
        f'height={height}'
    ]
    lines.append(f'    "{node_id}" [{", ".join(attrs)}];')


def generate_task_dependency_dot(tasknet: TaskNet, show_definitions: bool = False) -> str:
    """Generate DOT format for task dependency graph with cluster-based containment"""
    nodes, edges = build_dependency_graph(tasknet, show_definitions)
    compute_temporal_ranks(nodes, edges)

    lines = []
    lines.append("digraph tasknet {")
    lines.append(f'  label="{tasknet.id} - Task Dependencies (Cluster Layout)";')
    lines.append('  labelloc="t";')
    lines.append('  fontsize=16;')
    lines.append('  rankdir=TB;')  # Top to bottom
    lines.append('  compound=true;')  # Allow edges to/from clusters
    lines.append('  node [fontname="Arial"];')
    lines.append('  edge [fontname="Arial"];')
    lines.append('  ranksep=1.5;')
    lines.append('  nodesep=0.8;')
    lines.append('')

    # Identify container tasks and their contained tasks
    container_to_contained: Dict[str, List[str]] = defaultdict(list)
    for node_id, node in nodes.items():
        if node.container:
            container_to_contained[node.container].append(node_id)

    # Tasks that are not contained in anything (roots)
    all_contained = set(sum(container_to_contained.values(), []))
    root_tasks = [n for n in nodes if n not in all_contained]

    # For tasks with multiple containers, track secondary containment
    multi_contained: Dict[str, List[str]] = defaultdict(list)
    for node_id, node in nodes.items():
        if node.container:
            # Count how many containers this task has
            container_count = sum(1 for e in edges if e.edge_type == "containedin" and e.from_id == node_id)
            if container_count > 1:
                # Find all containers
                containers_list = [e.to_id for e in edges if e.edge_type == "containedin" and e.from_id == node_id]
                # Primary container is node.container, others are secondary
                secondary = [c for c in containers_list if c != node.container]
                multi_contained[node_id] = secondary

    # Generate clusters for each container task
    for container_id in sorted(container_to_contained.keys()):
        contained = container_to_contained[container_id]
        lines.append(f'  subgraph cluster_{container_id.replace("-", "_")} {{')
        lines.append(f'    label="{container_id} (container)";')
        lines.append(f'    style=dashed;')
        lines.append(f'    color=purple;')
        lines.append(f'    fontcolor=purple;')
        lines.append('')

        # Add container node
        _add_node(lines, container_id, nodes[container_id], is_container=True)

        # Add contained nodes
        for contained_id in sorted(contained):
            _add_node(lines, contained_id, nodes[contained_id], is_container=False)

        lines.append(f'  }}')
        lines.append('')

    # Add root tasks (not contained)
    if root_tasks:
        lines.append('  // Root tasks (not contained)')
        for node_id in sorted(root_tasks):
            lines.append(f'  "{node_id}" [label="{node_id}", shape=box, color="black", fillcolor="lightgreen", style="filled", width=2.0, height=0.6];')
        lines.append('')

    # Generate edges
    for edge in edges:
        # Skip containedin edges for tasks in their primary cluster (redundant)
        if edge.edge_type == "containedin":
            # Only show if this is a secondary containment (multi-contained case)
            if edge.from_id not in multi_contained or edge.to_id not in multi_contained[edge.from_id]:
                continue

        attrs = []
        attrs.append(f'label="{edge.label}"')
        if edge.style != "solid":
            attrs.append(f'style={edge.style}')
        attrs.append(f'color="{edge.color}"')

        # All edges don't affect layout - clusters handle containment
        attrs.append('constraint=false')

        attr_str = f' [{", ".join(attrs)}]' if attrs else ""
        lines.append(f'  "{edge.from_id}" -> "{edge.to_id}"{attr_str};')

    lines.append('}')
    return '\n'.join(lines)


# ============================================================================
# RENDERING
# ============================================================================

def check_dot_available() -> bool:
    """Check if Graphviz dot command is available"""
    try:
        subprocess.run(['dot', '-V'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def render_dot_to_png(dot_path: Path) -> bool:
    """Render DOT file to PNG using Graphviz"""
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
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Generate timeline-layout visualization of TaskNet files'
    )
    parser.add_argument('tasknet_file', help='Path to .tn tasknet file')
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
        output_dir = tasknet_path.parent / 'visualizations'
    else:
        output_dir = Path(args.output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate task dependency graph with timeline layout
    print(f"Generating task dependency graph (timeline layout)...")
    task_dot = generate_task_dependency_dot(tasknet, args.show_definitions)

    task_dot_path = output_dir / f"{base_name}_tasks_timeline.dot"
    with open(task_dot_path, 'w') as f:
        f.write(task_dot)
    print(f"  → {task_dot_path}")

    # Automatically render to PNG if dot is available
    if check_dot_available():
        print(f"\nRendering to PNG...")
        render_dot_to_png(task_dot_path)
    else:
        print(f"\nGraphviz not found. Install it to automatically render PNG files.", file=sys.stderr)
        print(f"You can manually render with: dot -Tpng {task_dot_path} -o {task_dot_path.with_suffix('.png')}")

    print(f"\nDone!")


if __name__ == '__main__':
    main()
