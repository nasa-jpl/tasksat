"""Tests for the static tasknet structure visualization.

These test the graph BUILDERS (node/edge extraction) against the raw parsed AST
(no apply_transforms, so mutex/sequence remain visible), plus the DOT generation
and end-to-end PNG rendering when Graphviz is available.
"""

import sys
import os
import shutil

# Add src/smt to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "smt"))

import pytest

from tasknet_parser import parse_tasknet
from tasknet_structure_viz import (
    build_task_relation_graph,
    build_timeline_interaction_graph,
    generate_relations_dot,
    generate_timeline_dot,
    create_structure_visualization,
    check_dot_available,
)


def _edge_pairs(edges, label_contains=None, color=None):
    """Return the set of (from_id, to_id) pairs, optionally filtered."""
    out = set()
    for e in edges:
        if label_contains is not None and label_contains not in e.label:
            continue
        if color is not None and e.color != color:
            continue
        out.add((e.from_id, e.to_id))
    return out


# ---------------------------------------------------------------------------
# Panel 1: task / taskdef relations
# ---------------------------------------------------------------------------

def test_after_edge():
    tn = parse_tasknet("""
    tasknet T {
        end = 200;
        task a { duration 10; }
        task b { after a; duration 10; }
    }
    """)
    nodes, edges = build_task_relation_graph(tn)
    # dependent -> prerequisite
    assert ("b", "a") in _edge_pairs(edges, label_contains="after")


def test_containedin_edge():
    tn = parse_tasknet("""
    tasknet T {
        end = 200;
        task parent { duration 100; }
        task child { containedin parent; duration 10; }
    }
    """)
    nodes, edges = build_task_relation_graph(tn)
    assert ("child", "parent") in _edge_pairs(edges, label_contains="containedin")


def test_instance_of_taskdef_edge():
    tn = parse_tasknet("""
    tasknet T {
        end = 200;
        taskdef Work { duration 10; }
        task w1 : Work {}
    }
    """)
    nodes, edges = build_task_relation_graph(tn)
    assert ("w1", "Work") in _edge_pairs(edges, label_contains="of")
    # taskdef node present and labeled
    labels = {n.id: n.label for n in nodes}
    assert "Work" in labels and "taskdef" in labels["Work"]


def test_mutex_within_group_pairs():
    tn = parse_tasknet("""
    tasknet T {
        end = 200;
        task a { duration 10; }
        task b { duration 10; }
        task c { duration 10; }
        constraints { prop m: mutex [a, b, c]; }
    }
    """)
    nodes, edges = build_task_relation_graph(tn)
    pairs = {frozenset(p) for p in _edge_pairs(edges, label_contains="mutex")}
    assert pairs == {frozenset(("a", "b")), frozenset(("a", "c")), frozenset(("b", "c"))}
    # mutex edges are symmetric (undirected)
    mutex_edges = [e for e in edges if "mutex" in e.label]
    assert all(e.dir == "none" for e in mutex_edges)


def test_mutex_between_group_pairs():
    tn = parse_tasknet("""
    tasknet T {
        end = 200;
        task a { duration 10; }
        task b { duration 10; }
        task c { duration 10; }
        constraints { prop m: mutex [a] with [b, c]; }
    }
    """)
    nodes, edges = build_task_relation_graph(tn)
    pairs = {frozenset(p) for p in _edge_pairs(edges, label_contains="mutex")}
    assert pairs == {frozenset(("a", "b")), frozenset(("a", "c"))}


def test_mutex_cross_label():
    tn = parse_tasknet("""
    tasknet T {
        end = 200;
        taskdef A { duration 10; }
        taskdef B { duration 10; }
        task a0 : A {}
        task b0 : B {}
        constraints { prop m: mutex cross [A, B]; }
    }
    """)
    nodes, edges = build_task_relation_graph(tn)
    # Operand-level edge between taskdefs, labeled as cross
    cross = _edge_pairs(edges, label_contains="cross")
    assert frozenset(list(cross)[0]) == frozenset(("A", "B"))


def test_sequence_chain_edges():
    tn = parse_tasknet("""
    tasknet T {
        end = 200;
        task a { duration 10; }
        task b { duration 10; }
        task c { duration 10; }
        constraints { prop s: sequence [a, b, c]; }
    }
    """)
    nodes, edges = build_task_relation_graph(tn)
    seq = _edge_pairs(edges, label_contains="sequence")
    assert ("a", "b") in seq and ("b", "c") in seq


# ---------------------------------------------------------------------------
# Panel 2: task <-> timeline interactions
# ---------------------------------------------------------------------------

def test_impact_edges_tagged_by_when():
    tn = parse_tasknet("""
    tasknet T {
        end = 200;
        timelines { battery : rate [0.0, 100.0] = 50.0; }
        task drain {
            duration 10;
            impacts { maint { battery +~ 2.0; } }
        }
    }
    """)
    nodes, edges = build_timeline_interaction_graph(tn)
    # task -> timeline impact edge, labeled with 'maint'
    assert ("drain", "battery") in _edge_pairs(edges, label_contains="maint")
    # timeline node present
    assert any(n.id == "battery" for n in nodes)


def test_read_edges_from_pre():
    tn = parse_tasknet("""
    tasknet T {
        end = 200;
        timelines { mode : state(idle, busy) = idle; }
        task go {
            duration 10;
            pre { mode = idle; }
        }
    }
    """)
    nodes, edges = build_timeline_interaction_graph(tn)
    assert ("go", "mode") in _edge_pairs(edges, label_contains="pre")


# ---------------------------------------------------------------------------
# DOT generation + rendering
# ---------------------------------------------------------------------------

def test_generate_relations_dot():
    tn = parse_tasknet("""
    tasknet T {
        end = 200;
        timelines { battery : rate [0.0, 100.0] = 50.0; }
        task a { duration 10; impacts { maint { battery +~ 1.0; } } }
        task b { after a; duration 10; }
    }
    """)
    dot = generate_relations_dot(tn)
    assert "digraph tasknet_relations" in dot
    assert '"a"' in dot and '"b"' in dot
    # after edge
    assert '"b" -> "a"' in dot


def test_generate_timeline_dot_is_bipartite():
    tn = parse_tasknet("""
    tasknet T {
        end = 200;
        timelines { battery : rate [0.0, 100.0] = 50.0; }
        task a { duration 10; impacts { maint { battery +~ 1.0; } } }
    }
    """)
    dot = generate_timeline_dot(tn)
    assert "digraph tasknet_timelines" in dot
    # tasks pinned to source rank, timelines to sink rank
    assert "rank=source" in dot
    assert "rank=sink" in dot
    assert '"a" -> "battery"' in dot


@pytest.mark.skipif(not check_dot_available(), reason="Graphviz 'dot' not installed")
def test_render_composited_png(tmp_path):
    tn = parse_tasknet("""
    tasknet T {
        end = 200;
        timelines { battery : rate [0.0, 100.0] = 50.0; }
        task a { duration 10; impacts { maint { battery +~ 1.0; } } }
        task b { after a; duration 10; }
        constraints { prop m: mutex [a, b]; }
    }
    """)
    base = tmp_path / "structure.png"
    created = create_structure_visualization(tn, str(base))
    # With PIL available the two panels are composited into the single base image;
    # the intermediate per-panel files are cleaned up.
    try:
        from PIL import Image  # noqa: F401
        have_pil = True
    except ImportError:
        have_pil = False

    if have_pil:
        assert created == [str(base)]
        assert base.exists() and base.stat().st_size > 0
        # composite must be wider than tall-ish: at least as wide as both panels
        from PIL import Image
        assert Image.open(base).width > Image.open(base).height * 0.8
        assert not (tmp_path / "structure_relations.png").exists()
        assert not (tmp_path / "structure_timelines.png").exists()
    else:
        # Fallback: two separate panels are kept.
        assert len(created) == 2
