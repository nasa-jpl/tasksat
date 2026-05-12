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

    # Pass 3: Reclassify constraints based on what they reference
    # (Parser puts all constraints in *_instances based on container type, but
    #  we need to categorize based on whether referenced ID is taskdef or instance)
    tn = reclassify_constraints(tn)

    # Pass 4: Instantiate taskdefs for type-level dependencies
    # (Must come after reclassification so we know which taskdefs are referenced)
    tn = instantiate_from_definitions(tn)

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
# Transformation Pass 3: Reclassify Constraints
# ==============================================================================

def reclassify_constraints(tn: TaskNet) -> TaskNet:
    """
    Reclassify after/containedin constraints based on what they reference.

    The parser categorizes constraints based on the container task's kind:
    - If parsing a taskdef, constraints go to after_definitions/containedin_definitions
    - If parsing an instance, constraints go to after_instances/containedin_instances

    But this is wrong! The categorization should be based on whether the
    referenced ID is a taskdef or an instance:
    - If reference points to a taskdef → should be in *_definitions
    - If reference points to an instance → should be in *_instances

    This pass fixes the categorization by:
    1. Building a set of all taskdef IDs
    2. For each task, checking its constraints
    3. Moving taskdef references from *_instances to *_definitions
    4. Moving instance references from *_definitions to *_instances

    Args:
        tn: The TaskNet AST

    Returns:
        TaskNet with constraints properly categorized
    """
    # Build set of taskdef IDs
    taskdef_ids = {t.id for t in tn.tasks if t.kind == TaskKind.DEFINITION}

    # Reclassify constraints for each task
    for task in tn.tasks:
        # Process after constraints
        if task.after_instances or task.after_definitions:
            # Start with empty lists
            instances = []
            definitions = []

            # Collect from both sources
            if task.after_instances:
                for ref_id in task.after_instances:
                    if ref_id in taskdef_ids:
                        definitions.append(ref_id)
                    else:
                        instances.append(ref_id)

            if task.after_definitions:
                for ref_id in task.after_definitions:
                    if ref_id in taskdef_ids:
                        definitions.append(ref_id)
                    else:
                        instances.append(ref_id)

            # Update task
            task.after_instances = instances if instances else None
            task.after_definitions = definitions if definitions else None

        # Process containedin constraints
        if task.containedin_instances or task.containedin_definitions:
            # Start with empty lists
            instances = []
            definitions = []

            # Collect from both sources
            if task.containedin_instances:
                for ref_id in task.containedin_instances:
                    if ref_id in taskdef_ids:
                        definitions.append(ref_id)
                    else:
                        instances.append(ref_id)

            if task.containedin_definitions:
                for ref_id in task.containedin_definitions:
                    if ref_id in taskdef_ids:
                        definitions.append(ref_id)
                    else:
                        instances.append(ref_id)

            # Update task
            task.containedin_instances = instances if instances else None
            task.containedin_definitions = definitions if definitions else None

    return tn


# ==============================================================================
# Transformation Pass 4: Taskdef Instantiation for Type-Level Dependencies
# ==============================================================================

def instantiate_from_definitions(tn: TaskNet) -> TaskNet:
    """
    Automatically create task instances from taskdefs when needed by type-level
    dependencies (after/containedin).

    For each task instance with type-level dependencies:
    - If after_definitions references taskdef T and no instance of T exists
    - Create a new instance from T with kind=INSTANCE (required)
    - The instance is required because the constraint must be satisfied

    This only instantiates DIRECT dependencies. If the auto-created instance
    has its own type-level dependencies, those are NOT instantiated (no cascade).
    The SMT encoder will error on unsatisfied dependencies of auto-created instances.

    Example:
        taskdef preheat { ... }
        task downlink { after preheat; }

        → Creates instance preheat_auto_0 from taskdef preheat

    Args:
        tn: The TaskNet AST

    Returns:
        TaskNet with taskdef instances created for type-level dependencies
    """
    # Separate definitions from instances
    taskdefs = {t.id: t for t in tn.tasks if t.kind == TaskKind.DEFINITION}
    instances = [t for t in tn.tasks if t.kind != TaskKind.DEFINITION]

    # Collect taskdef IDs that need instances
    needed_taskdefs = set()

    for task in instances:
        # Check instance's direct constraints
        if task.after_definitions:
            for def_id in task.after_definitions:
                if def_id in taskdefs:
                    needed_taskdefs.add(def_id)

        if task.containedin_definitions:
            for def_id in task.containedin_definitions:
                if def_id in taskdefs:
                    needed_taskdefs.add(def_id)

        # Check inherited constraints from taskdef
        if task.definition and task.definition in taskdefs:
            taskdef = taskdefs[task.definition]

            # Inherit after_definitions from taskdef
            if taskdef.after_definitions:
                for def_id in taskdef.after_definitions:
                    if def_id in taskdefs:
                        needed_taskdefs.add(def_id)

            # Inherit containedin_definitions from taskdef
            if taskdef.containedin_definitions:
                for def_id in taskdef.containedin_definitions:
                    if def_id in taskdefs:
                        needed_taskdefs.add(def_id)

    # Check which taskdefs already have instances
    existing_instances = {t.definition for t in instances if t.definition}

    # Instantiate missing taskdefs
    new_instances = []
    next_ident = max((t.ident for t in tn.tasks), default=0) + 1

    for def_id in needed_taskdefs:
        # Skip if instance already exists
        if def_id in existing_instances:
            continue

        taskdef = taskdefs[def_id]

        # Create instance from taskdef
        # Use naming pattern: {taskdef_id}_auto_0
        instance_id = f"{def_id}_auto_0"

        # Check for name collision
        while any(t.id == instance_id for t in tn.tasks):
            # Extract number and increment
            parts = instance_id.rsplit('_', 1)
            if len(parts) == 2 and parts[1].isdigit():
                num = int(parts[1]) + 1
                base = instance_id[:-(len(parts[1]) + 1)]  # Remove _N
                instance_id = f"{base}_{num}"
            else:
                instance_id = f"{instance_id}_1"

        # Deep copy lists to avoid shared references
        def deep_copy_tlcons(tlcons):
            if not tlcons:
                return None
            return [TlCon(tc.id, tc.cons.copy()) for tc in tlcons]

        def deep_copy_impacts(impacts):
            if not impacts:
                return None
            return [Impact(imp.id, imp.when, imp.how) for imp in impacts]

        new_instance = Task(
            id=instance_id,
            ident=next_ident,
            kind=TaskKind.INSTANCE,  # Required (dependency must be satisfied)
            definition=def_id,       # Reference to taskdef
            priority=taskdef.priority,
            startrng=taskdef.startrng,
            endrng=taskdef.endrng,
            durrng=taskdef.durrng,
            dur=taskdef.dur,
            start=taskdef.start,
            # Copy instance-level constraints from taskdef
            after_instances=taskdef.after_instances.copy() if taskdef.after_instances else None,
            containedin_instances=taskdef.containedin_instances.copy() if taskdef.containedin_instances else None,
            # DO NOT copy type-level constraints (no cascade)
            after_definitions=None,
            containedin_definitions=None,
            # Copy conditions and impacts
            pre=deep_copy_tlcons(taskdef.pre),
            inv=deep_copy_tlcons(taskdef.inv),
            post=deep_copy_tlcons(taskdef.post),
            impacts=deep_copy_impacts(taskdef.impacts),
        )

        new_instances.append(new_instance)
        next_ident += 1

    # Add new instances to tasknet
    if new_instances:
        tn.tasks.extend(new_instances)
        print(f"\n*** Auto-instantiated {len(new_instances)} task(s) from taskdefs:")
        for inst in new_instances:
            print(f"    {inst.id} (from taskdef {inst.definition})")
        print()

    return tn


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
