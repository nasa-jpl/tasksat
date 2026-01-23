"""
TaskNet AST Transformations

This module provides transformations that desugar derived/syntactic-sugar constructs
into core TaskNet primitives. Transformations are applied after parsing but before
well-formedness checking and SMT encoding.

Transformation pipeline:
    parse → transform → check_wellformedness → encode_to_smt
"""

from __future__ import annotations
from typing import Set, Optional
from tasknet_ast import *


def apply_transforms(tn: TaskNet) -> TaskNet:
    """
    Apply all AST transformations in order.

    This is the main entry point for the transformation pipeline.
    Add new transformation passes here as they are implemented.

    Args:
        tn: The parsed TaskNet AST

    Returns:
        Transformed TaskNet with all derived constructs desugared to core primitives
    """
    # Pass 1: Desugar active(T) syntax to __T_active = true
    tn = desugar_active_predicate(tn)

    # Pass 2: Inject task state timelines for __taskname_active references
    # (This must come after Pass 1 so it sees the desugared __T_active references)
    tn = inject_task_state_timelines(tn)

    # Future passes can be added here:
    # tn = expand_macros(tn)              # Hypothetical: expand task templates
    # tn = inline_definitions(tn)         # Hypothetical: inline task definitions

    return tn


# ==============================================================================
# Transformation Pass 1: Desugar active(T) Predicate
# ==============================================================================

def desugar_active_predicate(tn: TaskNet) -> TaskNet:
    """
    Transform active(taskname) predicates to __taskname_active = true.

    This is syntactic sugar that makes properties more readable:
        always (active(T1) -> A = true)
    becomes:
        always (__T1_active = true -> A = true)

    The transformation recursively walks all temporal formulas in constraints
    and properties, replacing TLTaskActive nodes with TLBoolIs nodes.

    Args:
        tn: The TaskNet AST

    Returns:
        TaskNet with active(T) syntax desugared to __T_active = true
    """
    # Transform constraints
    for prop in tn.constraints:
        prop.formula = _desugar_formula(prop.formula)

    # Transform properties
    for prop in tn.properties:
        prop.formula = _desugar_formula(prop.formula)

    return tn


def _desugar_formula(f: Formula) -> Formula:
    """
    Recursively desugar active(T) to __T_active = true in a formula.
    """
    # Base case: TLTaskActive desugars to TLBoolIs
    if isinstance(f, TLTaskActive):
        return TLBoolIs(tl=f"__{f.task}_active", value=True)

    # Recursive cases: process subformulas
    elif isinstance(f, (TLAnd, TLOr, TLUntil, TLSince)):
        return type(f)(
            left=_desugar_formula(f.left),
            right=_desugar_formula(f.right)
        )
    elif isinstance(f, (TLNot, TLAlways, TLEventually, TLSoFar, TLOnce)):
        return type(f)(sub=_desugar_formula(f.sub))
    elif isinstance(f, TLImplies):
        return TLImplies(
            left=_desugar_formula(f.left),
            right=_desugar_formula(f.right)
        )

    # Atomic formulas (TLNumCmp, TLStateIs, TLBoolIs): no transformation needed
    else:
        return f


# ==============================================================================
# Transformation Pass 2: Task State Timeline Injection
# ==============================================================================

def inject_task_state_timelines(tn: TaskNet) -> TaskNet:
    """
    Automatically generate __taskname_active timelines for tasks referenced
    in temporal formulas or conditions.

    This transformation allows users to write properties like:
        always (__T1_active = true -> A = true)
    without manually creating and maintaining task state timelines.

    For each referenced task T, this creates:
    - An atomic timeline __T_active with initial value false
    - A PRE impact on T that sets __T_active to true
    - A POST impact on T that sets __T_active to false

    Args:
        tn: The TaskNet AST

    Returns:
        TaskNet with synthetic task state timelines injected
    """
    # Collect all task names that are referenced via __taskname_active pattern
    referenced_tasks = _collect_referenced_task_states(tn)

    if not referenced_tasks:
        return tn

    # Generate timelines and inject impacts only for referenced tasks
    for task_id in referenced_tasks:
        # Find the task
        task = next((t for t in tn.tasks if t.id == task_id), None)

        if not task or task.kind == TaskKind.DEFINITION:
            # Skip if task doesn't exist or is a definition (not scheduled)
            continue

        timeline_id = f"__{task_id}_active"

        # Check if timeline already exists (avoid duplicates)
        if any(tl.id == timeline_id for tl in tn.timelines):
            continue

        # Create atomic timeline: false initially, true when task is active
        tl = AtomicTimeline(
            id=timeline_id,
            initial=False
        )
        tn.timelines.append(tl)

        # Inject impacts to set timeline true at start, false at end
        if task.impacts is None:
            task.impacts = []

        task.impacts.extend([
            Impact(
                id=timeline_id,
                when="pre",
                how=ImpactAssign(BoolVal(True))
            ),
            Impact(
                id=timeline_id,
                when="post",
                how=ImpactAssign(BoolVal(False))
            )
        ])

    return tn


def _collect_referenced_task_states(tn: TaskNet) -> Set[str]:
    """
    Scan the TaskNet for references to __taskname_active timelines.
    Returns set of task names that need state tracking.
    """
    referenced = set()

    # Scan temporal formulas (constraints and properties)
    for prop in tn.constraints + tn.properties:
        referenced.update(_find_task_refs_in_formula(prop.formula))

    # Scan task conditions (pre/inv/post)
    for task in tn.tasks:
        for cond_list in [task.pre, task.inv, task.post]:
            if cond_list:
                for tlcon in cond_list:
                    task_name = _extract_task_name_from_timeline_id(tlcon.id)
                    if task_name:
                        referenced.add(task_name)

    # Scan initial constraints
    for tlcon in tn.initial_constraints:
        task_name = _extract_task_name_from_timeline_id(tlcon.id)
        if task_name:
            referenced.add(task_name)

    return referenced


def _find_task_refs_in_formula(f: Formula) -> Set[str]:
    """
    Recursively find task state timeline references in a formula.
    Returns set of task names.
    """
    refs = set()

    # Check atomic formulas that reference timelines
    if isinstance(f, (TLBoolIs, TLStateIs)):
        task_name = _extract_task_name_from_timeline_id(f.tl)
        if task_name:
            refs.add(task_name)
    elif isinstance(f, TLNumCmp):
        task_name = _extract_task_name_from_timeline_id(f.tl)
        if task_name:
            refs.add(task_name)

    # Recurse into compound formulas
    elif isinstance(f, (TLAnd, TLOr, TLUntil, TLSince)):
        refs.update(_find_task_refs_in_formula(f.left))
        refs.update(_find_task_refs_in_formula(f.right))
    elif isinstance(f, (TLNot, TLAlways, TLEventually, TLSoFar, TLOnce)):
        refs.update(_find_task_refs_in_formula(f.sub))
    elif isinstance(f, TLImplies):
        refs.update(_find_task_refs_in_formula(f.left))
        refs.update(_find_task_refs_in_formula(f.right))

    return refs


def _extract_task_name_from_timeline_id(timeline_id: str) -> Optional[str]:
    """
    Extract task name from timeline ID if it matches __taskname_active pattern.
    Returns None if it doesn't match the pattern.
    """
    if timeline_id.startswith("__") and timeline_id.endswith("_active"):
        # Strip __ prefix and _active suffix
        return timeline_id[2:-7]
    return None


# ==============================================================================
# Future Transformation Passes
# ==============================================================================


# ==============================================================================
# Guide: Adding New Transformation Passes
# ==============================================================================
#
# To add a new transformation pass:
#
# 1. Define your transformation function:
#    def my_transformation(tn: TaskNet) -> TaskNet:
#        """
#        Clear docstring explaining what derived syntax is being desugared
#        and what core constructs it transforms to.
#        """
#        # Your transformation logic here
#        return tn
#
# 2. Add it to apply_transforms() in the appropriate order:
#    - Earlier passes can create constructs that later passes transform
#    - Dependencies: if pass B needs output from pass A, put A before B
#
# 3. Update tests to verify the transformation works correctly
#
# Example transformation ideas:
#   - Macro expansion: expand task templates into concrete tasks
#   - Constraint normalization: rewrite complex constraints to simpler forms
#   - Default value injection: add missing default values
#   - Syntactic sugar: desugar high-level syntax to core primitives
#
