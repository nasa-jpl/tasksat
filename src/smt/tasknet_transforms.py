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


def apply_transforms(tn: TaskNet) -> tuple[TaskNet, bool]:
    """
    Apply all AST transformations in order.

    This is the main entry point for the transformation pipeline.
    Add new transformation passes here as they are implemented.

    Args:
        tn: The parsed TaskNet AST

    Returns:
        Tuple of (transformed TaskNet, auto_instantiation_occurred)
        - Transformed TaskNet with all derived constructs desugared to core primitives
        - Boolean indicating whether auto-instantiation created new task instances
    """
    # Pass 0: Expand task ranges FIRST (before other transforms that operate on tasks)
    # Example: task T[2..4] → T_0, T_1, T_2, T_3
    tn = expand_task_ranges(tn)

    # Pass 1: Desugar sequence [task1, task2, ...] to pairwise ordering constraints
    tn = desugar_sequence(tn)

    # Pass 1.5: Desugar mutex [task1, task2, ...] to non-overlap constraints
    # (Must come BEFORE active() desugaring to avoid creating active timelines)
    tn = desugar_mutex(tn)

    # Pass 2: Desugar active(T) syntax to __T_active = 1
    tn = desugar_active_predicate(tn)

    # Pass 3: Inject task state timelines for __taskname_active references
    # (This must come after Pass 2 so it sees the desugared __T_active references)
    tn = inject_task_state_timelines(tn)

    # Pass 4: Reclassify constraints based on what they reference
    # (Parser puts all constraints in *_instances based on container type, but
    #  we need to categorize based on whether referenced ID is taskdef or instance)
    tn = reclassify_constraints(tn)

    # Pass 5: Instantiate taskdefs for type-level dependencies
    # (Must come after reclassification so we know which taskdefs are referenced)
    original_task_count = len(tn.tasks)
    tn = instantiate_from_definitions(tn)
    auto_instantiation_occurred = len(tn.tasks) > original_task_count

    # Pass 6: Reclassify again after auto-instantiation
    # (Newly created instances need to be linked to tasks that depend on them)
    tn = reclassify_constraints(tn)

    # NOTE: We do NOT convert type-level to instance-level dependencies here.
    # The SMT encoder will resolve inherited type-level dependencies to specific
    # auto-instances at encoding time, avoiding conflicts with inheritance.

    # Future passes can be added here:
    # tn = expand_macros(tn)              # Hypothetical: expand task templates
    # tn = inline_definitions(tn)         # Hypothetical: inline task definitions

    return tn, auto_instantiation_occurred


# ==============================================================================
# Transformation Pass 1: Desugar sequence Construct
# ==============================================================================

def desugar_sequence(tn: TaskNet) -> TaskNet:
    """
    Transform sequence [task1, task2, ...] constructs into pairwise ordering constraints.

    This is syntactic sugar for sequential task ordering:
        sequence [T1, T2, T3]
    becomes:
        T1.end <= T2.start and T2.end <= T3.start

    The transformation recursively walks all temporal formulas in constraints
    and properties, replacing TLSequence nodes with conjunctions of TLTimeCmp nodes.

    Args:
        tn: The TaskNet AST

    Returns:
        TaskNet with sequence constructs desugared to pairwise constraints
    """
    # Transform constraints
    for prop in tn.constraints:
        prop.formula = _desugar_sequence_formula(prop.formula)

    # Transform properties
    for prop in tn.properties:
        prop.formula = _desugar_sequence_formula(prop.formula)

    return tn


def _desugar_sequence_formula(f: Formula) -> Formula:
    """
    Recursively desugar sequence [T1, T2, ...] to T1.end <= T2.start and ... in a formula.
    """
    # Base case: TLSequence desugars to conjunction of pairwise constraints
    if isinstance(f, TLSequence):
        tasks = f.tasks
        if len(tasks) < 2:
            # Empty or single-task sequence: trivially true
            return TLTrue()

        # Build conjunction: task[0].end <= task[1].start and task[1].end <= task[2].start ...
        constraints = []
        for i in range(len(tasks) - 1):
            left = TLTaskBoundary(task=tasks[i], boundary="end")
            right = TLTaskBoundary(task=tasks[i + 1], boundary="start")
            constraint = TLTimeCmp(left=left, op="<=", right=right)
            constraints.append(constraint)

        # Chain with AND
        result = constraints[0]
        for c in constraints[1:]:
            result = TLAnd(left=result, right=c)

        return result

    # Recursive cases: process subformulas
    elif isinstance(f, (TLAnd, TLOr, TLUntil, TLSince)):
        return type(f)(
            left=_desugar_sequence_formula(f.left),
            right=_desugar_sequence_formula(f.right)
        )
    elif isinstance(f, (TLNot, TLAlways, TLEventually, TLSoFar, TLOnce)):
        return type(f)(sub=_desugar_sequence_formula(f.sub))
    elif isinstance(f, TLImplies):
        return TLImplies(
            left=_desugar_sequence_formula(f.left),
            right=_desugar_sequence_formula(f.right)
        )

    # Atomic formulas: no transformation needed
    else:
        return f


# ==============================================================================
# Transformation Pass 1.5: Desugar Mutex Constraints
# ==============================================================================

def desugar_mutex(tn: TaskNet) -> TaskNet:
    """
    Transform mutex [task1, task2, ...] constructs into non-overlap constraints.

    This is syntactic sugar for mutual exclusion:
        mutex [T1, T2]
    becomes:
        (T1.end <= T2.start) or (T2.end <= T1.start)

    And between-group exclusion:
        mutex [T1, T2] with [T3, T4]
    becomes the cross-product of all pairs from both groups.

    The transformation recursively walks all temporal formulas in constraints
    and properties, replacing TLMutex nodes with disjunctions of non-overlap conditions.

    Args:
        tn: The TaskNet AST

    Returns:
        TaskNet with mutex constructs desugared to non-overlap constraints
    """
    # Transform constraints
    for prop in tn.constraints:
        prop.formula = _desugar_mutex_formula(prop.formula)

    # Transform properties
    for prop in tn.properties:
        prop.formula = _desugar_mutex_formula(prop.formula)

    return tn


def _desugar_mutex_formula(f: Formula) -> Formula:
    """
    Recursively desugar mutex [T1, T2, ...] to non-overlap disjunctions.
    """
    # Base case: TLMutex desugars to conjunction of non-overlap disjunctions
    if isinstance(f, TLMutex):
        constraints = []

        if f.group_b is None:
            # Within-group: all pairs
            tasks = f.group_a
            for i in range(len(tasks)):
                for j in range(i+1, len(tasks)):
                    constraints.append(_make_non_overlap_formula(tasks[i], tasks[j]))
        else:
            # Between-group: cross-product
            for task_a in f.group_a:
                for task_b in f.group_b:
                    constraints.append(_make_non_overlap_formula(task_a, task_b))

        # Empty list: trivially true
        if not constraints:
            return TLTrue()

        # Single constraint: return it
        if len(constraints) == 1:
            return constraints[0]

        # Multiple constraints: AND them together
        result = constraints[0]
        for c in constraints[1:]:
            result = TLAnd(left=result, right=c)
        return result

    # Recursive cases: process subformulas
    elif isinstance(f, (TLAnd, TLOr, TLUntil, TLSince)):
        return type(f)(
            left=_desugar_mutex_formula(f.left),
            right=_desugar_mutex_formula(f.right)
        )
    elif isinstance(f, (TLNot, TLAlways, TLEventually, TLSoFar, TLOnce)):
        return type(f)(sub=_desugar_mutex_formula(f.sub))
    elif isinstance(f, TLImplies):
        return TLImplies(
            left=_desugar_mutex_formula(f.left),
            right=_desugar_mutex_formula(f.right)
        )

    # Atomic formulas: no transformation needed
    else:
        return f


def _make_non_overlap_formula(task_a: str, task_b: str) -> Formula:
    """
    Create non-overlap formula: (A.end <= B.start) or (B.end <= A.start)
    """
    # A.end <= B.start
    a_before_b = TLTimeCmp(
        left=TLTaskBoundary(task=task_a, boundary="end"),
        op="<=",
        right=TLTaskBoundary(task=task_b, boundary="start")
    )

    # B.end <= A.start
    b_before_a = TLTimeCmp(
        left=TLTaskBoundary(task=task_b, boundary="end"),
        op="<=",
        right=TLTaskBoundary(task=task_a, boundary="start")
    )

    # (A.end <= B.start) or (B.end <= A.start)
    return TLOr(left=a_before_b, right=b_before_a)


# ==============================================================================
# Transformation Pass 2: Desugar active(T) Predicate
# ==============================================================================

def desugar_active_predicate(tn: TaskNet) -> TaskNet:
    """
    Transform active(taskname) predicates to __taskname_active = 1.

    This is syntactic sugar that makes properties more readable:
        always (active(T1) -> A = 1)
    becomes:
        always (__T1_active = 1 -> A = 1)

    The transformation recursively walks all temporal formulas in constraints
    and properties, replacing TLTaskActive nodes with TLNumCmp nodes.

    Args:
        tn: The TaskNet AST

    Returns:
        TaskNet with active(T) syntax desugared to __T_active = 1
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
    Recursively desugar active(T) to __T_active = 1 in a formula.
    """
    # Base case: TLTaskActive desugars to TLNumCmp
    if isinstance(f, TLTaskActive):
        return TLNumCmp(tl=f"__{f.task}_active", op="=", bound=1)

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

    # Atomic formulas (TLNumCmp, TLStateIs, TLBoolIs, TLTrue, TLFalse): no transformation needed
    else:
        return f


# ==============================================================================
# Transformation Pass 3: Task State Timeline Injection
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
    - A MAINT impact on T that claims __T_active (+=1) during execution

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

        # Create atomic timeline: 0 initially, 1 when task is active
        tl = AtomicTimeline(
            id=timeline_id,
            initial=0
        )
        tn.timelines.append(tl)

        # Inject cumulative impact to claim timeline during task execution
        if task.impacts is None:
            task.impacts = []

        task.impacts.append(
            Impact(
                id=timeline_id,
                when="maint",
                how=ImpactCumulative(1)
            )
        )

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

    MEXEC-like behavior: For each task with a type-level dependency, create
    one instance of the referenced taskdef. This allows multiple tasks to each
    get their own instance.

    Only auto-instantiate if the user provided ZERO instances of that taskdef.
    If user provided any instances (≥1), assume user is managing instances manually.

    This only instantiates DIRECT dependencies. If the auto-created instance
    has its own type-level dependencies, those are NOT instantiated (no cascade).
    The SMT encoder will error on unsatisfied dependencies of auto-created instances.

    Example:
        taskdef preheat { ... }
        task downlink1 { after preheat; }
        task downlink2 { after preheat; }

        → Creates: preheat_auto_0 (for downlink1), preheat_auto_1 (for downlink2)

    Args:
        tn: The TaskNet AST

    Returns:
        TaskNet with taskdef instances created for type-level dependencies
    """
    # Separate definitions from instances
    taskdefs = {t.id: t for t in tn.tasks if t.kind == TaskKind.DEFINITION}
    instances = [t for t in tn.tasks if t.kind != TaskKind.DEFINITION]

    # Check which taskdefs already have user-provided instances
    taskdefs_with_instances = {t.definition for t in instances if t.definition}

    # Collect dependencies: list of (dependent_task_id, required_taskdef_id) pairs
    dependencies = []

    for task in instances:
        # Collect all taskdef IDs this task depends on
        needed_taskdefs = []

        # Check instance's direct constraints
        if task.after_definitions:
            needed_taskdefs.extend(task.after_definitions)

        if task.containedin_definitions:
            needed_taskdefs.extend(task.containedin_definitions)

        # Check inherited constraints from taskdef
        if task.definition and task.definition in taskdefs:
            taskdef = taskdefs[task.definition]

            if taskdef.after_definitions:
                needed_taskdefs.extend(taskdef.after_definitions)

            if taskdef.containedin_definitions:
                needed_taskdefs.extend(taskdef.containedin_definitions)

        # For each needed taskdef, record the dependency
        for def_id in needed_taskdefs:
            if def_id in taskdefs:
                dependencies.append((task.id, def_id))

    # Group dependencies by taskdef
    from collections import defaultdict
    taskdef_dependencies = defaultdict(list)
    for task_id, def_id in dependencies:
        taskdef_dependencies[def_id].append(task_id)

    # Instantiate one instance per dependency
    new_instances = []
    next_ident = max((t.ident for t in tn.tasks), default=0) + 1
    existing_ids = {t.id for t in tn.tasks}

    for def_id, dependent_tasks in taskdef_dependencies.items():
        # Skip if user provided ANY instances of this taskdef
        if def_id in taskdefs_with_instances:
            continue

        taskdef = taskdefs[def_id]

        # Create one instance per dependent task
        for idx, dependent_task_id in enumerate(dependent_tasks):
            # Find the dependent task to inherit its kind
            dependent_task = next((t for t in instances if t.id == dependent_task_id), None)
            if not dependent_task:
                continue  # Skip if dependent task not found

            # Use naming pattern: {taskdef_id}_auto_N
            instance_id = f"{def_id}_auto_{idx}"

            # Ensure unique ID
            counter = idx
            while instance_id in existing_ids:
                counter += 1
                instance_id = f"{def_id}_auto_{counter}"

            existing_ids.add(instance_id)

            # Deep copy lists to avoid shared references
            def deep_copy_tlcons(tlcons):
                if not tlcons:
                    return None
                return [TlCon(tc.id, tc.cons.copy()) for tc in tlcons]

            def deep_copy_impacts(impacts):
                if not impacts:
                    return None
                return [Impact(imp.id, imp.when, imp.how) for imp in impacts]

            # Inherit kind from dependent task:
            # - If dependent is INSTANCE (required) → auto-instance is INSTANCE (required)
            # - If dependent is REQUEST (desirable) → auto-instance is OPTIONAL (only if REQUEST included)
            # - If dependent is OPTIONAL (minimize) → auto-instance is OPTIONAL
            if dependent_task.kind == TaskKind.INSTANCE:
                instance_kind = TaskKind.INSTANCE
            else:
                instance_kind = TaskKind.OPTIONAL

            new_instance = Task(
                id=instance_id,
                ident=next_ident,
                kind=instance_kind,  # Inherit from dependent task
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
# Transformation Pass 6: Link Auto-Instances
# ==============================================================================

def link_auto_instances(tn: TaskNet) -> TaskNet:
    """
    Link tasks to their auto-created instances by converting type-level dependencies
    to instance-level dependencies.

    After auto-instantiation creates instances like preheat_auto_0 and preheat_auto_1,
    we need to match each dependent task to its corresponding instance.

    The matching uses the same order as instance creation: instances are created
    in the order dependent tasks appear, so downlink_1 (first) gets preheat_auto_0,
    downlink_2 (second) gets preheat_auto_1, etc.

    Args:
        tn: The TaskNet AST

    Returns:
        TaskNet with type-level dependencies linked to auto-created instances
    """
    # Replicate the dependency collection logic from instantiate_from_definitions
    taskdefs = {t.id: t for t in tn.tasks if t.kind == TaskKind.DEFINITION}
    instances = [t for t in tn.tasks if t.kind != TaskKind.DEFINITION]

    # Filter out auto-created instances (only process original instances for mapping)
    original_instances = [t for t in instances if '_auto_' not in t.id]

    # Collect dependencies: list of (dependent_task_id, required_taskdef_id) pairs
    dependencies = []

    for task in original_instances:
        needed_taskdefs = []

        # Check instance's direct constraints
        if task.after_definitions:
            needed_taskdefs.extend(task.after_definitions)
        if task.containedin_definitions:
            needed_taskdefs.extend(task.containedin_definitions)

        # Check inherited constraints from taskdef
        if task.definition and task.definition in taskdefs:
            taskdef = taskdefs[task.definition]
            if taskdef.after_definitions:
                needed_taskdefs.extend(taskdef.after_definitions)
            if taskdef.containedin_definitions:
                needed_taskdefs.extend(taskdef.containedin_definitions)

        # For each needed taskdef, record the dependency
        for def_id in needed_taskdefs:
            if def_id in taskdefs:
                dependencies.append((task.id, def_id))

    # Group dependencies by taskdef (in same order as instantiation)
    from collections import defaultdict
    taskdef_dependencies = defaultdict(list)
    for task_id, def_id in dependencies:
        taskdef_dependencies[def_id].append(task_id)

    # Build two mappings:
    # 1. (task_id, taskdef_id) -> auto_instance_id (for linking dependencies)
    # 2. auto_instance_id -> task_id (for tracking which "group" an auto-instance belongs to)
    existing_instance_ids = {t.id for t in tn.tasks}
    task_to_instance = {}
    auto_instance_to_group = {}  # Maps auto-instance to its "parent" dependent task

    for def_id, dependent_task_ids in taskdef_dependencies.items():
        for idx, dependent_task_id in enumerate(dependent_task_ids):
            auto_instance_id = f"{def_id}_auto_{idx}"
            # Only add mapping if the auto-instance exists
            if auto_instance_id in existing_instance_ids:
                task_to_instance[(dependent_task_id, def_id)] = auto_instance_id
                auto_instance_to_group[auto_instance_id] = dependent_task_id


    # For each task, link type-level dependencies to their auto-instances
    for task in instances:
        # Collect all type-level dependencies (direct + inherited from taskdef)
        after_defs = []
        containedin_defs = []

        # Direct constraints
        if task.after_definitions:
            after_defs.extend(task.after_definitions)
        if task.containedin_definitions:
            containedin_defs.extend(task.containedin_definitions)

        # Inherited constraints from taskdef
        if task.definition and task.definition in taskdefs:
            taskdef = taskdefs[task.definition]
            if taskdef.after_definitions:
                after_defs.extend(taskdef.after_definitions)
            if taskdef.containedin_definitions:
                containedin_defs.extend(taskdef.containedin_definitions)

        # Determine which "group" to use for lookups:
        # - Original tasks use their own ID
        # - Auto-instances use their parent dependent task's ID
        lookup_task_id = auto_instance_to_group.get(task.id, task.id)

        # Process after constraints
        if after_defs:
            new_after_instances = list(task.after_instances) if task.after_instances else []
            new_after_definitions = []

            for taskdef_id in after_defs:
                key = (lookup_task_id, taskdef_id)
                if key in task_to_instance:
                    new_after_instances.append(task_to_instance[key])
                else:
                    # Keep as type-level (no auto-instance for this task+taskdef pair)
                    new_after_definitions.append(taskdef_id)

            task.after_instances = new_after_instances if new_after_instances else None
            task.after_definitions = new_after_definitions if new_after_definitions else None

        # Process containedin constraints
        if containedin_defs:
            new_containedin_instances = list(task.containedin_instances) if task.containedin_instances else []
            new_containedin_definitions = []

            for taskdef_id in containedin_defs:
                key = (lookup_task_id, taskdef_id)
                if key in task_to_instance:
                    new_containedin_instances.append(task_to_instance[key])
                else:
                    # Keep as type-level (no auto-instance for this task+taskdef pair)
                    new_containedin_definitions.append(taskdef_id)

            task.containedin_instances = new_containedin_instances if new_containedin_instances else None
            task.containedin_definitions = new_containedin_definitions if new_containedin_definitions else None

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


def expand_task_ranges(tn: TaskNet) -> TaskNet:
    """
    Expand TaskRange nodes into individual Task nodes.

    For task T[2..4]:
        - Creates T_0, T_1 (required, kind=INSTANCE)
        - Creates T_2, T_3 (optional, kind=OPTIONAL)

    For request task R[2..4]:
        - Creates R_0, R_1 (required, kind=INSTANCE)
        - Creates R_2, R_3 (request, kind=REQUEST)

    Args:
        tn: TaskNet AST (may contain TaskRange nodes)

    Returns:
        TaskNet with all TaskRange nodes expanded to Task nodes
    """
    expanded_tasks = []

    for task in tn.tasks:
        if isinstance(task, TaskRange):
            # Expand range to individual tasks
            base_name = task.id
            min_inst = task.min_instances
            max_inst = task.max_instances

            # Validate range
            if min_inst > max_inst:
                raise ValueError(f"Invalid range for task '{base_name}': min ({min_inst}) > max ({max_inst})")
            if min_inst < 0 or max_inst < 0:
                raise ValueError(f"Invalid range for task '{base_name}': indices must be non-negative")

            # Create required instances (0 to min_instances-1)
            for i in range(min_inst):
                expanded_tasks.append(Task(
                    id=f"{base_name}_{i}",
                    ident=task.ident + i if task.ident else i,
                    kind=TaskKind.INSTANCE,
                    definition=task.definition,
                    priority=task.priority,
                    startrng=task.startrng,
                    endrng=task.endrng,
                    durrng=task.durrng,
                    dur=task.dur,
                    start=task.start,
                    after_instances=task.after_instances,
                    after_definitions=task.after_definitions,
                    containedin_instances=task.containedin_instances,
                    containedin_definitions=task.containedin_definitions,
                    pre=task.pre,
                    inv=task.inv,
                    post=task.post,
                    impacts=task.impacts
                ))

            # Create optional/request instances (min_instances to max_instances-1)
            for i in range(min_inst, max_inst):
                expanded_tasks.append(Task(
                    id=f"{base_name}_{i}",
                    ident=task.ident + i if task.ident else i,
                    kind=TaskKind.REQUEST if task.is_request else TaskKind.OPTIONAL,
                    definition=task.definition,
                    priority=task.priority,
                    startrng=task.startrng,
                    endrng=task.endrng,
                    durrng=task.durrng,
                    dur=task.dur,
                    start=task.start,
                    after_instances=task.after_instances,
                    after_definitions=task.after_definitions,
                    containedin_instances=task.containedin_instances,
                    containedin_definitions=task.containedin_definitions,
                    pre=task.pre,
                    inv=task.inv,
                    post=task.post,
                    impacts=task.impacts
                ))
        else:
            # Regular task, keep as-is
            expanded_tasks.append(task)

    tn.tasks = expanded_tasks
    return tn

