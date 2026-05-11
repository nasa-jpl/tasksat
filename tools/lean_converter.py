#!/usr/bin/env python3
"""
Convert Python TaskNet AST to Lean-compatible JSON format.
"""

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src' / 'smt'))

from tasknet_parser import parse_tasknet_file
from tasknet_ast import *

def convert_value(v):
    """Convert Python Value to Lean JSON format."""
    if isinstance(v, IntVal):
        return {"tag": "intVal", "v": v.v}
    elif isinstance(v, RealVal):
        return {"tag": "realVal", "v": v.v}
    elif isinstance(v, StrVal):
        return {"tag": "strVal", "v": v.v}
    elif isinstance(v, BoolVal):
        return {"tag": "boolVal", "v": v.v}
    raise ValueError(f"Unknown value type: {type(v)}")

def convert_timeline(tl):
    """Convert Python Timeline to Lean JSON format."""
    if isinstance(tl, StateTimeline):
        return {
            "tag": "stateTimeline",
            "id": tl.id,
            "states": tl.states,
            "initial": tl.initial
        }
    elif isinstance(tl, AtomicTimeline):
        return {
            "tag": "atomicTimeline",
            "id": tl.id,
            "initial": tl.initial or False
        }
    elif isinstance(tl, ClaimableTimeline):
        return {
            "tag": "claimableTimeline",
            "id": tl.id,
            "range": {"low": tl.range.low, "high": tl.range.high},
            "initial": tl.initial or 0.0
        }
    elif isinstance(tl, CumulativeTimeline):
        # If bounds is None, use range as bounds
        bounds = tl.bounds if tl.bounds else tl.range
        return {
            "tag": "cumulativeTimeline",
            "id": tl.id,
            "range": {"low": tl.range.low, "high": tl.range.high},
            "bounds": {"low": bounds.low, "high": bounds.high},
            "initial": tl.initial or 0.0
        }
    elif isinstance(tl, RateTimeline):
        # If bounds is None, use range as bounds
        bounds = tl.bounds if tl.bounds else tl.range
        return {
            "tag": "rateTimeline",
            "id": tl.id,
            "range": {"low": tl.range.low, "high": tl.range.high},
            "bounds": {"low": bounds.low, "high": bounds.high},
            "initial": tl.initial or 0.0,
            "initial_rate": tl.initial_rate or 0.0
        }
    raise ValueError(f"Unknown timeline type: {type(tl)}")

def convert_con(c):
    """Convert Python Con to Lean JSON."""
    if isinstance(c, ConVal):
        return {"tag": "val", "v": convert_value(c.v)}
    elif isinstance(c, ConIntRange):
        return {"tag": "i_rng", "r": {"low": c.r.low, "high": c.r.high}}
    elif isinstance(c, ConRealRange):
        return {"tag": "r_rng", "r": {"low": c.r.low, "high": c.r.high}}
    raise ValueError(f"Unknown Con type: {type(c)}")

def convert_tlcon(tc):
    """Convert Python TlCon to Lean JSON."""
    return {
        "id": tc.id,
        "cons": [convert_con(c) for c in tc.cons]
    }

def convert_impact(imp):
    """Convert Python Impact to Lean JSON."""
    if isinstance(imp.how, ImpactAssign):
        how_tag = "assign"
        how_val = convert_value(imp.how.v)
    elif isinstance(imp.how, ImpactCumulative):
        how_tag = "cumulative"
        how_val = imp.how.v
    elif isinstance(imp.how, ImpactRateCumulative):
        # Lean only has "rate" which behaves like rateCumulative
        how_tag = "rate"
        how_val = imp.how.delta
    elif isinstance(imp.how, ImpactRateAssignment):
        # Lean only has "rate" - rate assignment not directly supported
        # Map to rate cumulative for now (semantics differ slightly)
        how_tag = "rate"
        how_val = imp.how.r
    else:
        raise ValueError(f"Unknown ImpactHow type: {type(imp.how)}")

    return {
        "id": imp.id,
        "when": imp.when,
        "how": {"tag": how_tag, "v": how_val}
    }

def convert_task(task):
    """Convert Python Task to Lean TaskDef JSON format."""
    return {
        "id": task.id,
        "ident": task.ident,
        "priority": task.priority or 0,
        "startrng": {"low": task.startrng.low, "high": task.startrng.high} if task.startrng else {"low": 0, "high": 1000000},
        "endrng": {"low": task.endrng.low, "high": task.endrng.high} if task.endrng else {"low": 0, "high": 1000000},
        "durrng": {"low": task.durrng.low, "high": task.durrng.high} if task.durrng else {"low": 0, "high": 1000000},
        "dur": task.dur or 0,
        "start": task.start or 0,
        "after": task.after_instances or [],
        "containedin": task.containedin_instances or [],
        "after_definitions": task.after_definitions or [],
        "containedin_definitions": task.containedin_definitions or [],
        "kind": task.kind.value if hasattr(task.kind, 'value') else task.kind.name.lower(),
        "pre": [convert_tlcon(c) for c in (task.pre or [])],
        "inv": [convert_tlcon(c) for c in (task.inv or [])],
        "post": [convert_tlcon(c) for c in (task.post or [])],
        "impacts": [convert_impact(i) for i in (task.impacts or [])]
    }

def convert_tasknet(tn):
    """Convert Python TaskNet to Lean JSON format."""
    # Separate taskdefs from task instances
    taskdef_list = [t for t in tn.tasks if t.kind == TaskKind.DEFINITION]
    actual_tasks = [t for t in tn.tasks if t.kind != TaskKind.DEFINITION]

    # Build map of taskdef name → taskdef for constraint inheritance
    taskdefs = {t.id: t for t in taskdef_list}

    # Inherit constraints and properties from taskdefs to instances
    for task in actual_tasks:
        if task.definition and task.definition in taskdefs:
            taskdef = taskdefs[task.definition]
            # Inherit range constraints if not set on instance
            if not task.startrng and taskdef.startrng:
                task.startrng = taskdef.startrng
            if not task.endrng and taskdef.endrng:
                task.endrng = taskdef.endrng
            if not task.durrng and taskdef.durrng:
                task.durrng = taskdef.durrng
            # Inherit priority if not set
            if task.priority is None and taskdef.priority is not None:
                task.priority = taskdef.priority
            # Inherit temporal constraints
            if not task.after_definitions and taskdef.after_definitions:
                task.after_definitions = taskdef.after_definitions
            if not task.containedin_definitions and taskdef.containedin_definitions:
                task.containedin_definitions = taskdef.containedin_definitions
            # Inherit conditions if not set on instance
            if not task.pre and taskdef.pre:
                task.pre = taskdef.pre
            if not task.inv and taskdef.inv:
                task.inv = taskdef.inv
            if not task.post and taskdef.post:
                task.post = taskdef.post
            # Inherit impacts if not set on instance
            if not task.impacts and taskdef.impacts:
                task.impacts = taskdef.impacts

    return {
        "id": tn.id,
        "timelines": [convert_timeline(tl) for tl in tn.timelines],
        "tasks": [convert_task(t) for t in actual_tasks],
        "taskdefs": [convert_task(t) for t in taskdef_list],
        "endTime": tn.endTime
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: lean_converter.py tasknet.tn [output.json]")
        sys.exit(1)

    tasknet_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "tasknet.lean.json"

    # Parse with existing Python parser
    tasknet = parse_tasknet_file(tasknet_path)

    # Convert to Lean format
    lean_json = convert_tasknet(tasknet)

    # Write output
    with open(output_path, 'w') as f:
        json.dump(lean_json, f, indent=2)

    print(f"✓ Converted {tasknet_path} → {output_path}")

if __name__ == '__main__':
    main()
