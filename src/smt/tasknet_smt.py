
from __future__ import annotations
from typing import List, Optional, Dict, Union, Literal, Tuple

from z3 import (
    Solver, Optimize, Int, Real, Bool,
    And, Or, Not, If,
    sat, Sum,
)

from tasknet_ast import *
from tasknet_ast import TaskKind


class TaskNetSMT:
    """
    Solver for TaskNet using Z3 SMT.
    """

    def __init__(self, tn: TaskNet, use_optimization: bool = True):
        self.tn = self.normalize_tasknet(tn)
        self.tn = self.resolve_task_definitions(self.tn)

        # === Task categorization ===
        self.required_tasks = [t for t in self.tn.tasks if t.kind == TaskKind.INSTANCE]
        self.optional_tasks = [t for t in self.tn.tasks if t.kind == TaskKind.OPTIONAL]
        self.request_tasks = [t for t in self.tn.tasks if t.kind == TaskKind.REQUEST]
        self.all_scheduled_tasks = self.required_tasks + self.optional_tasks + self.request_tasks

        # === Optional task inclusion variables ===
        self.optional_included: Dict[str, object] = {}
        for t in self.optional_tasks:
            self.optional_included[t.id] = Bool(f"included_{t.id}")

        # === Request task inclusion variables ===
        self.request_included: Dict[str, object] = {}
        for t in self.request_tasks:
            self.request_included[t.id] = Bool(f"included_{t.id}")

        # Use Optimize if we have optional or request tasks and optimization is enabled, otherwise use Solver
        if (self.optional_tasks or self.request_tasks) and use_optimization:
            self.solver = Optimize()
            print(f"DEBUG: Using Optimize mode")
        else:
            self.solver = Solver()
            # Enable unsat core tracking for Solver (not available for Optimize)
            self.solver.set(unsat_core=True)
            print(f"DEBUG: Using Solver mode with unsat_core=True")

        # === Schedule variables ===
        self.start_vars: Dict[str, object] = {}
        self.end_vars: Dict[str, object] = {}
        self._mk_schedule_vars()
        self._encode_start_end_times_ok()
        self._encode_no_simultaneous_assignments()

        # === Zone boundaries ===
        # At most 2*|tasks| + 2 unique boundaries: 0, endTime, all start/end's
        self.zone_count = 2 * len(self.all_scheduled_tasks) + 2
        self.zones = [Int(f"z_{i}") for i in range(self.zone_count)]
        self._encode_zones()

        # === State at each zone for each timeline ===
        # state timelines: id -> (states, str->idx, idx->str, [Int vars])
        self.state_tl_zone: Dict[str, Tuple[List[str], Dict[str, int], Dict[int, str], List]] = {}
        # atomic timelines: id -> [Bool vars]
        self.atomic_tl_zone: Dict[str, List] = {}
        # numeric timelines: id -> (range, bounds_opt, [Real vars])
        self.numeric_tl_zone: Dict[str, Tuple[RealRange, Optional[RealRange], List]] = {}
        # rate timeline rates: id -> [Real vars] for the RATE (not value)
        self.rate_tl_rate_zone: Dict[str, List] = {}

        self._mk_zone_state_vars()
        self._encode_initial_state_zones()
        self._encode_initial_bounds()
        self._encode_init_predicate()
        self._encode_zone_transitions()
        self._encode_timeline_ranges()
        self._encode_pre_inv_post_zones()

    def add_tracked(self, constraint, label: str):
        """Add a constraint with tracking for unsat core analysis."""
        if isinstance(self.solver, Solver):
            # Use assert_and_track for Solver (supports unsat cores)
            self.solver.assert_and_track(constraint, label)
            if not hasattr(self, '_tracked_count'):
                self._tracked_count = 0
            self._tracked_count += 1
        else:
            # Optimize doesn't support assert_and_track
            self.solver.add(constraint)

    def _format_conditions(self, conds: List[TlCon]) -> str:
        """Format timeline conditions for display in unsat core."""
        if not conds:
            return "no conditions"
        parts = []
        for tlcon in conds:
            tl_id = tlcon.id
            con_strs = []
            for con in tlcon.cons:
                if isinstance(con, ConVal):
                    con_strs.append(f"{con.v}")
                elif isinstance(con, ConIntRange):
                    con_strs.append(f"in [{con.r.low},{con.r.high}]")
                elif isinstance(con, ConRealRange):
                    con_strs.append(f"in [{con.r.low},{con.r.high}]")
            if con_strs:
                parts.append(f"{tl_id} {', '.join(con_strs)}")
        return "; ".join(parts) if parts else "conditions"

    def _analyze_unsat_core(self, by_category: dict):
        """Provide detailed analysis of unsat core constraints."""
        print("\nDetailed Analysis:")

        # Analyze atomic capacity violations
        if 'atomic_capacity' in by_category:
            # Extract timeline name from first constraint
            first_label = by_category['atomic_capacity'][0]
            # Parse: "atomic_capacity: timeline 'resource' must stay in [0,1] at zone 2"
            if "timeline '" in first_label:
                tl_name = first_label.split("timeline '")[1].split("'")[0]

                # Find all tasks that impact this timeline
                impacting_tasks = []
                for t in self.all_scheduled_tasks:
                    if t.impacts:
                        for imp in t.impacts:
                            if imp.id == tl_name:
                                impact_type = "maint" if imp.when == "maint" else imp.when
                                if isinstance(imp.how, ImpactCumulative):
                                    delta = imp.how.v
                                    impacting_tasks.append({
                                        'id': t.id,
                                        'type': impact_type,
                                        'delta': delta,
                                        'start_range': f"[{t.startrng.low},{t.startrng.high}]" if t.startrng else "any",
                                        'duration_range': f"[{t.durrng.low},{t.durrng.high}]" if t.durrng else "any"
                                    })
                                    break  # Only report first impact per task

                if impacting_tasks:
                    print(f"  Timeline '{tl_name}' (atomic, valid range [0,1]) is impacted by {len(impacting_tasks)} task(s):")
                    for task_info in impacting_tasks:
                        print(f"    • Task '{task_info['id']}': {task_info['type']} impact {task_info['delta']:+.0f}, "
                              f"start {task_info['start_range']}, duration {task_info['duration_range']}")

                    # Check for overlapping tasks
                    if len(impacting_tasks) >= 2:
                        print(f"\n  ⚠️  Conflict: {len(impacting_tasks)} tasks claim the same atomic resource.")
                        print(f"      Since their time ranges overlap, they would simultaneously claim the resource,")
                        print(f"      causing the value to exceed 1 (mutual exclusion violated).")

        # Analyze timeline range violations (numeric timelines)
        if 'timeline_range' in by_category:
            first_label = by_category['timeline_range'][0]
            # Parse: "timeline_range: timeline 'battery' must stay in [0.0,100.0] at zone 3"
            if "timeline '" in first_label:
                tl_name = first_label.split("timeline '")[1].split("'")[0]
                range_part = first_label.split("must stay in ")[1].split(" at zone")[0]

                # Find all tasks that impact this timeline
                impacting_tasks = []
                for t in self.all_scheduled_tasks:
                    if t.impacts:
                        for imp in t.impacts:
                            if imp.id == tl_name:
                                impact_type = imp.when
                                if isinstance(imp.how, ImpactCumulative):
                                    delta = imp.how.v
                                    impacting_tasks.append({
                                        'id': t.id,
                                        'type': impact_type,
                                        'delta': delta,
                                        'start_range': f"[{t.startrng.low},{t.startrng.high}]" if t.startrng else "any",
                                        'duration_range': f"[{t.durrng.low},{t.durrng.high}]" if t.durrng else "any"
                                    })
                                    break

                # Get timeline details
                tl_initial = None
                for tl in self.tn.timelines:
                    if tl.id == tl_name:
                        if hasattr(tl, 'initial'):
                            tl_initial = tl.initial
                        break

                if impacting_tasks:
                    print(f"  Timeline '{tl_name}' must stay in range {range_part}")
                    if tl_initial is not None:
                        print(f"  Initial value: {tl_initial}")
                    print(f"  Impacted by {len(impacting_tasks)} task(s):")
                    for task_info in impacting_tasks:
                        print(f"    • Task '{task_info['id']}': {task_info['type']} impact {task_info['delta']:+.0f}, "
                              f"start {task_info['start_range']}, duration {task_info['duration_range']}")

                    print(f"\n  ⚠️  Conflict: The combined impacts push the timeline outside its valid range.")
                    print(f"      Adjust task impacts, timing, or increase the timeline range.")

        # Analyze precondition violations
        if 'precondition' in by_category:
            first_label = by_category['precondition'][0]
            # Parse: "precondition: task 'charge' requires battery in [150.0,200.0] at start (zone 1)"
            if "task '" in first_label and "requires " in first_label:
                task_name = first_label.split("task '")[1].split("'")[0]
                condition_part = first_label.split("requires ")[1].split(" at start")[0]

                # Find the timeline being constrained
                tl_name = condition_part.split()[0]

                # Find the timeline definition to get its valid range
                tl_range = None
                for tl in self.tn.timelines:
                    if tl.id == tl_name:
                        if isinstance(tl, CumulativeTimeline):
                            if hasattr(tl, 'range'):
                                tl_range = f"[{tl.range.low},{tl.range.high}]"
                            if hasattr(tl, 'initial'):
                                initial = tl.initial
                        break

                print(f"  Task '{task_name}' requires {condition_part}")
                if tl_range:
                    print(f"  However, timeline '{tl_name}' has valid range {tl_range}")
                    if hasattr(tl, 'initial'):
                        print(f"  and initial value {initial}")
                print(f"\n  ⚠️  Conflict: The required range is outside the timeline's valid range.")
                print(f"      This precondition can never be satisfied.")

        # Analyze postcondition violations
        if 'postcondition' in by_category:
            first_label = by_category['postcondition'][0]
            # Parse: "postcondition: task 'drain' requires battery in [10.0,20.0] at end (zone 3)"
            if "task '" in first_label and "requires " in first_label:
                task_name = first_label.split("task '")[1].split("'")[0]
                condition_part = first_label.split("requires ")[1].split(" at end")[0]

                # Find the timeline being constrained
                tl_name = condition_part.split()[0]

                # Find the timeline definition
                tl_range = None
                for tl in self.tn.timelines:
                    if tl.id == tl_name:
                        if isinstance(tl, CumulativeTimeline):
                            if hasattr(tl, 'range'):
                                tl_range = f"[{tl.range.low},{tl.range.high}]"
                            if hasattr(tl, 'initial'):
                                initial = tl.initial
                        break

                print(f"  Task '{task_name}' requires {condition_part} at end")
                if tl_range:
                    print(f"  However, timeline '{tl_name}' has valid range {tl_range}")
                    if hasattr(tl, 'initial'):
                        print(f"  and initial value {initial}")
                print(f"\n  ⚠️  Conflict: The postcondition cannot be satisfied given timeline dynamics.")
                print(f"      Check task impacts and whether the timeline can reach the required value.")

        # Analyze invariant violations
        if 'invariant' in by_category:
            first_label = by_category['invariant'][0]
            # Parse: "invariant: task 'maintain' requires power in [50.0,100.0] during execution (zone 3)"
            if "task '" in first_label and "requires " in first_label:
                task_name = first_label.split("task '")[1].split("'")[0]
                condition_part = first_label.split("requires ")[1].split(" during execution")[0]

                # Find the timeline being constrained
                tl_name = condition_part.split()[0]

                # Find the timeline definition
                tl_range = None
                for tl in self.tn.timelines:
                    if tl.id == tl_name:
                        if isinstance(tl, CumulativeTimeline):
                            if hasattr(tl, 'range'):
                                tl_range = f"[{tl.range.low},{tl.range.high}]"
                        break

                print(f"  Task '{task_name}' requires {condition_part} throughout its execution")
                if tl_range:
                    print(f"  Timeline '{tl_name}' has valid range {tl_range}")
                print(f"\n  ⚠️  Conflict: The invariant cannot be maintained during task execution.")
                print(f"      Check timeline state and task impacts that might violate the invariant.")

        # Analyze containment dependency violations
        if 'dependency_containedin' in by_category:
            labels = by_category['dependency_containedin']
            # Parse: "dependency_containedin: task 'child' must be contained within task 'parent'"
            print(f"  ⚠️  Containment constraint violation:")
            for label in labels:
                if "task '" in label:
                    parts = label.split("task '")
                    if len(parts) >= 3:
                        child_task = parts[1].split("'")[0]
                        parent_task = parts[2].split("'")[0]
                        print(f"      • Task '{child_task}' must be contained within '{parent_task}'")

                        # Find task time ranges
                        child_info = parent_info = None
                        for t in self.all_scheduled_tasks:
                            if t.id == child_task:
                                child_info = {
                                    'start': f"[{t.startrng.low},{t.startrng.high}]" if t.startrng else "any",
                                    'duration': f"[{t.durrng.low},{t.durrng.high}]" if t.durrng else "any"
                                }
                            if t.id == parent_task:
                                parent_info = {
                                    'start': f"[{t.startrng.low},{t.startrng.high}]" if t.startrng else "any",
                                    'duration': f"[{t.durrng.low},{t.durrng.high}]" if t.durrng else "any"
                                }

                        if child_info and parent_info:
                            print(f"        Child:  start {child_info['start']}, duration {child_info['duration']}")
                            print(f"        Parent: start {parent_info['start']}, duration {parent_info['duration']}")

            print(f"\n      The time ranges don't allow the child task(s) to fit within the parent(s).")
            print(f"      Adjust start/end ranges or durations to make containment possible.")

        # Analyze dependency cycles
        if 'dependency_after' in by_category:
            # Check if it's a circular dependency
            labels = by_category['dependency_after']
            if len(labels) >= 2:
                # Parse task IDs from labels
                tasks_involved = set()
                for label in labels:
                    if "task '" in label:
                        parts = label.split("task '")
                        if len(parts) >= 3:
                            task1 = parts[1].split("'")[0]
                            task2 = parts[2].split("'")[0]
                            tasks_involved.add(task1)
                            tasks_involved.add(task2)

                if len(tasks_involved) == len(labels):
                    print(f"  ⚠️  Circular dependency detected among {len(tasks_involved)} task(s):")
                    for label in labels:
                        if "task '" in label:
                            parts = label.split("task '")
                            if len(parts) >= 3:
                                task1 = parts[1].split("'")[0]
                                task2 = parts[2].split("'")[0]
                                print(f"      • '{task1}' must come after '{task2}'")
                    print(f"\n      This creates an impossible ordering - no valid schedule exists.")

        # Analyze task timing conflicts (start/end/duration ranges)
        if any(cat in by_category for cat in ['task_start_range', 'task_end_range', 'task_duration_range', 'task_timing']):
            print(f"\n  TASK TIMING CONSTRAINT CONFLICT:")
            print(f"  The following tasks have timing constraints that cannot be satisfied:\n")

            # Collect all tasks mentioned in timing constraints
            timing_tasks = {}
            for cat in ['task_start_range', 'task_end_range', 'task_duration_range', 'task_timing']:
                if cat in by_category:
                    for label in by_category[cat]:
                        if "task '" in label:
                            task_id = label.split("task '")[1].split("'")[0]
                            if task_id not in timing_tasks:
                                timing_tasks[task_id] = {'start': None, 'end': None, 'duration': None}

                            if 'start must be in [' in label:
                                range_str = label.split('[')[1].split(']')[0]
                                timing_tasks[task_id]['start'] = range_str
                            elif 'end must be in [' in label:
                                range_str = label.split('[')[1].split(']')[0]
                                timing_tasks[task_id]['end'] = range_str
                            elif 'duration must be in [' in label:
                                range_str = label.split('[')[1].split(']')[0]
                                timing_tasks[task_id]['duration'] = range_str

            for task_id, ranges in timing_tasks.items():
                print(f"    Task '{task_id}':")
                if ranges['start']:
                    print(f"      • Start range: [{ranges['start']}]")
                if ranges['end']:
                    print(f"      • End range: [{ranges['end']}]")
                if ranges['duration']:
                    print(f"      • Duration range: [{ranges['duration']}]")

            print(f"\n      ⚠️  Conflict: These timing constraints cannot be satisfied simultaneously.")
            print(f"      Common causes:")
            print(f"        • Multiple tasks with overlapping fixed start times need the same resource")
            print(f"        • Task dependencies create impossible ordering with fixed start times")
            print(f"        • Duration too long to fit within allowed time window")
            print(f"\n      Suggestions:")
            print(f"        • Widen start_range to allow more scheduling flexibility")
            print(f"        • Adjust duration_range if tasks are overconstrained")
            print(f"        • Review task dependencies and resource requirements")

        # Analyze zone ordering conflicts
        if 'zone_ordering' in by_category:
            print(f"\n  ZONE ORDERING CONFLICT:")
            zone_conflicts = []
            for label in by_category['zone_ordering']:
                if 'zone ' in label and ' must be < zone ' in label:
                    parts = label.split('zone ')
                    if len(parts) >= 3:
                        zone1 = parts[1].split(' ')[0]
                        zone2 = parts[2].split(' ')[0]
                        zone_conflicts.append((zone1, zone2))

            print(f"  The zone-based encoding requires zones to be strictly increasing in time:")
            for z1, z2 in zone_conflicts[:5]:  # Show first 5
                print(f"    • Zone {z1} must be < Zone {z2}")
            if len(zone_conflicts) > 5:
                print(f"    ... and {len(zone_conflicts) - 5} more zone ordering constraints")

            print(f"\n      ⚠️  Conflict: Task timing constraints make it impossible to maintain zone ordering.")
            print(f"      This typically indicates overconstrained task start/end/duration ranges.")
            print(f"\n      Suggestions:")
            print(f"        • Review task start_range and duration_range constraints")
            print(f"        • Look for tasks with fixed times that conflict with dependencies")
            print(f"        • Consider increasing the global time horizon (end value)")

        # Analyze task-zone alignment conflicts
        if 'task_zone_alignment' in by_category:
            print(f"\n  TASK-ZONE ALIGNMENT CONFLICT:")
            alignment_tasks = set()
            for label in by_category['task_zone_alignment']:
                if "task '" in label:
                    task_id = label.split("task '")[1].split("'")[0]
                    alignment_tasks.add(task_id)

            print(f"  The following tasks cannot align with zone boundaries:")
            for task_id in alignment_tasks:
                print(f"    • Task '{task_id}'")

            print(f"\n      ⚠️  Conflict: Task start/end times must align with zone boundaries,")
            print(f"      but the timing constraints make this impossible.")
            print(f"      This typically indicates overconstrained or conflicting timing requirements.")
            print(f"\n      Suggestions:")
            print(f"        • Relax fixed start/end time constraints")
            print(f"        • Review duration ranges for flexibility")
            print(f"        • Check for circular dependencies or impossible ordering")

    # -------------------
    # Resolving task definitions
    # -------------------

    def resolve_task_definitions(self, tn: TaskNet) -> TaskNet:
        """
        Resolve task instances that reference definitions by merging properties.
        Instance properties override definition properties.
        Remove definition tasks from the task list (they're not scheduled).
        """
        # Build a map of definitions
        definitions: Dict[str, Task] = {}
        for t in tn.tasks:
            if t.kind == TaskKind.DEFINITION:
                definitions[t.id] = t

        # Resolve instances and optional tasks that reference definitions
        resolved_tasks = []
        for t in tn.tasks:
            if t.kind == TaskKind.DEFINITION:
                # Skip definitions - they're not scheduled
                continue

            if t.definition is not None and t.definition in definitions:
                # Merge with definition (only if definition exists in map)
                defn = definitions[t.definition]
                resolved_tasks.append(self._merge_task_with_definition(t, defn))
            else:
                # Either no definition reference, or already resolved
                # (definition field preserved for type-level constraint lookups)
                resolved_tasks.append(t)

        tn.tasks = resolved_tasks
        return tn

    def _merge_task_with_definition(self, instance: Task, definition: Task) -> Task:
        """
        Merge instance with definition. Instance properties take precedence.
        Impacts are merged (not overwritten) to preserve both definition impacts
        and any impacts injected by transformation passes.
        """
        # Merge impacts: combine definition impacts with instance impacts
        merged_impacts = None
        if definition.impacts is not None and instance.impacts is not None:
            # Both have impacts - merge them
            merged_impacts = list(definition.impacts) + list(instance.impacts)
        elif definition.impacts is not None:
            # Only definition has impacts
            merged_impacts = definition.impacts
        elif instance.impacts is not None:
            # Only instance has impacts
            merged_impacts = instance.impacts

        return Task(
            id=instance.id,
            ident=instance.ident if instance.ident is not None else definition.ident,
            kind=instance.kind,
            definition=instance.definition,  # Preserve for type-level constraint lookups
            priority=instance.priority if instance.priority is not None else definition.priority,
            startrng=instance.startrng if instance.startrng is not None else definition.startrng,
            endrng=instance.endrng if instance.endrng is not None else definition.endrng,
            durrng=instance.durrng if instance.durrng is not None else definition.durrng,
            dur=instance.dur if instance.dur is not None else definition.dur,
            start=instance.start if instance.start is not None else definition.start,
            # Type-level constraints from definition, instance-level from instance
            after_instances=instance.after_instances,
            after_definitions=definition.after_definitions,
            containedin_instances=instance.containedin_instances,
            containedin_definitions=definition.containedin_definitions,
            pre=instance.pre if instance.pre is not None else definition.pre,
            inv=instance.inv if instance.inv is not None else definition.inv,
            post=instance.post if instance.post is not None else definition.post,
            impacts=merged_impacts,  # Use merged impacts
        )

    # -------------------
    # Normalizing tasknet
    # -------------------


    def normalize_tasknet(self, tn: TaskNet) -> TaskNet:
        MAX_INT  = 10**9
        MIN_REAL = -1e9
        MAX_REAL =  1e9

        for tl in tn.timelines:
            if isinstance(tl, StateTimeline):
                if getattr(tl, "initial", None) in ("",):
                    tl.initial = None

            elif isinstance(tl, AtomicTimeline):
                pass

            elif isinstance(tl, ClaimableTimeline):
                if getattr(tl, "range", None) is None:
                    tl.range = RealRange(MIN_REAL, MAX_REAL)

            elif isinstance(tl, CumulativeTimeline):
                if getattr(tl, "range", None) is None:
                    tl.range = RealRange(MIN_REAL, MAX_REAL)
                # Don't set default bounds - bounds should be None unless explicitly specified

            elif isinstance(tl, RateTimeline):
                if getattr(tl, "range", None) is None:
                    tl.range = RealRange(MIN_REAL, MAX_REAL)
                # Don't set default bounds - bounds should be None unless explicitly specified

        for t in tn.tasks:
            if getattr(t, "startrng", None) is None:
                t.startrng = IntRange(0, MAX_INT)
            if getattr(t, "endrng", None) is None:
                t.endrng = IntRange(0, MAX_INT)

        return tn

    # ------------------------------
    # 2.1 Schedule vars + constraints
    # ------------------------------

    def _mk_schedule_vars(self):
        for t in self.all_scheduled_tasks:
            s = Int(f"start_{t.id}")
            e = Int(f"end_{t.id}")
            self.start_vars[t.id] = s
            self.end_vars[t.id] = e

    def _encode_start_end_times_ok(self):
        n = self.tn.endTime
        tasks = self.all_scheduled_tasks

        # Check solver type once at the beginning
        use_tracking = isinstance(self.solver, Solver)

        # Basic constraints for each task
        for t in tasks:
            s = self.start_vars[t.id]
            e = self.end_vars[t.id]

            # Helper to conditionally add constraint for optional/request tasks
            def add_constraint(*args, label=None):
                constraint = And(*args) if len(args) > 1 else args[0]
                if t.kind == TaskKind.OPTIONAL:
                    # Only apply constraint if task is included
                    wrapped = If(self.optional_included[t.id], constraint, True)
                    if label:
                        self.add_tracked(wrapped, label)
                    else:
                        self.solver.add(wrapped)
                elif t.kind == TaskKind.REQUEST:
                    # Only apply constraint if task is included
                    wrapped = If(self.request_included[t.id], constraint, True)
                    if label:
                        self.add_tracked(wrapped, label)
                    else:
                        self.solver.add(wrapped)
                else:
                    # Required task - always apply constraint
                    if label:
                        self.add_tracked(constraint, label)
                    else:
                        self.solver.add(constraint)

            # Start/end within global horizon and ordered
            if use_tracking:
                add_constraint(s >= 0, s <= e, e <= n, label=f"task_timing: task '{t.id}' must have 0 <= start <= end <= {n}")
            else:
                add_constraint(s >= 0, s <= e, e <= n)

            # start,end within given ranges
            if t.startrng is not None:
                # Only track non-default ranges to avoid affecting optimization heuristics
                MAX_INT = 10**9
                is_default = (t.startrng.low == 0 and t.startrng.high == MAX_INT)
                if use_tracking and not is_default:
                    add_constraint(s >= t.startrng.low, s <= t.startrng.high, label=f"task_start_range: task '{t.id}' start must be in [{t.startrng.low},{t.startrng.high}]")
                else:
                    add_constraint(s >= t.startrng.low, s <= t.startrng.high)
            if t.endrng is not None:
                if use_tracking:
                    add_constraint(e >= t.endrng.low, e <= t.endrng.high, label=f"task_end_range: task '{t.id}' end must be in [{t.endrng.low},{t.endrng.high}]")
                else:
                    add_constraint(e >= t.endrng.low, e <= t.endrng.high)

            # duration range constraint
            if t.durrng is not None:
                if use_tracking:
                    add_constraint(e - s >= t.durrng.low, e - s <= t.durrng.high, label=f"task_duration_range: task '{t.id}' duration must be in [{t.durrng.low},{t.durrng.high}]")
                else:
                    add_constraint(e - s >= t.durrng.low, e - s <= t.durrng.high)

            # duration (now treated as preferred duration, not a hard constraint)
            # This will be handled in the optimization objective instead
            # if t.dur is not None:
            #     add_constraint(e - s == t.dur)

            # Instance-level after dependencies (specific task IDs)
            if t.after_instances is not None:
                for bid in t.after_instances:
                    if bid not in self.end_vars:
                        # ill-formed TaskNet — forbid
                        self.solver.add(False)
                    else:
                        add_constraint(self.end_vars[bid] <= s, label=f"dependency_after: task '{t.id}' must start after task '{bid}' ends")

            # Type-level after dependencies (definition IDs with OR semantics)
            if t.after_definitions is not None:
                for def_id in t.after_definitions:
                    # Find all instances of def_id (exclude definitions themselves)
                    def_instances = [inst for inst in tasks
                                    if inst.definition == def_id and inst.kind != TaskKind.DEFINITION]

                    if not def_instances:
                        # No instances of required definition - constraint cannot be satisfied
                        self.solver.add(False)
                    else:
                        # At least one instance must complete before this task starts
                        # Encoding: OR over all instances: (end(inst1) <= s) OR (end(inst2) <= s) OR ...
                        constraints = [self.end_vars[inst.id] <= s for inst in def_instances]
                        add_constraint(Or(*constraints), label=f"dependency_after: task '{t.id}' must start after some instance of '{def_id}'")

            # Instance-level containedin dependencies (specific task IDs)
            if t.containedin_instances is not None:
                for pid in t.containedin_instances:
                    if pid not in self.start_vars or pid not in self.end_vars:
                        # ill-formed TaskNet — forbid
                        self.solver.add(False)
                    else:
                        # parent task must be active during this task's execution
                        # parent_start <= this_start AND this_end <= parent_end
                        add_constraint(self.start_vars[pid] <= s, e <= self.end_vars[pid],
                                     label=f"dependency_containedin: task '{t.id}' must be contained within task '{pid}'")

            # Type-level containedin dependencies (definition IDs with OR semantics)
            if t.containedin_definitions is not None:
                for def_id in t.containedin_definitions:
                    # Find all instances of def_id (exclude definitions themselves)
                    def_instances = [inst for inst in tasks
                                    if inst.definition == def_id and inst.kind != TaskKind.DEFINITION]

                    if not def_instances:
                        # No instances of required definition - constraint cannot be satisfied
                        self.solver.add(False)
                    else:
                        # Must be contained within at least one instance
                        # Encoding: OR over all instances:
                        #   (parent1.start <= s AND e <= parent1.end) OR
                        #   (parent2.start <= s AND e <= parent2.end) OR ...
                        constraints = [And(self.start_vars[inst.id] <= s, e <= self.end_vars[inst.id])
                                      for inst in def_instances]
                        add_constraint(Or(*constraints), label=f"dependency_containedin: task '{t.id}' must be contained within some instance of '{def_id}'")

        # --- All task boundaries are pairwise distinct ---
        # Only for included tasks
        for i in range(len(tasks)):
            ti = tasks[i]
            si = self.start_vars[ti.id]
            ei = self.end_vars[ti.id]
            for j in range(i + 1, len(tasks)):
                tj = tasks[j]
                sj = self.start_vars[tj.id]
                ej = self.end_vars[tj.id]

                # Determine if both tasks are included
                both_included = True
                if ti.kind == TaskKind.OPTIONAL:
                    both_included = And(both_included, self.optional_included[ti.id])
                elif ti.kind == TaskKind.REQUEST:
                    both_included = And(both_included, self.request_included[ti.id])
                if tj.kind == TaskKind.OPTIONAL:
                    both_included = And(both_included, self.optional_included[tj.id])
                elif tj.kind == TaskKind.REQUEST:
                    both_included = And(both_included, self.request_included[tj.id])

                # Only enforce distinctness if both are included
                if ti.kind in (TaskKind.OPTIONAL, TaskKind.REQUEST) or tj.kind in (TaskKind.OPTIONAL, TaskKind.REQUEST):
                    self.add_tracked(If(both_included,
                        And(si != sj, ei != ej, si != ej, ei != sj),
                        True), f"task_distinctness: tasks '{ti.id}' and '{tj.id}' must have distinct boundaries")
                else:
                    # Both required - always distinct
                    self.add_tracked(And(si != sj, ei != ej, si != ej, ei != sj),
                                   f"task_distinctness: tasks '{ti.id}' and '{tj.id}' must have distinct boundaries")

    def _encode_no_simultaneous_assignments(self):
        """
        No two tasks may assign the same timeline at the same time.
        (Only for ImpactAssign; numeric impacts can overlap.)
        """
        tasks = self.all_scheduled_tasks
        assign_points: List[Tuple[TaskName, TimeLineName, object]] = []

        for t in tasks:
            s = self.start_vars[t.id]
            e = self.end_vars[t.id]
            if t.impacts is None:
                continue
            for imp in t.impacts:
                if isinstance(imp.how, ImpactAssign):
                    if imp.when == "pre":
                        assign_points.append((t.id, imp.id, s))
                    elif imp.when == "post":
                        assign_points.append((t.id, imp.id, e))
                    else:  # maint + assign is disallowed per spec
                        self.solver.add(False)

        m = len(assign_points)
        for i in range(m):
            _, id_i, time_i = assign_points[i]
            for j in range(i + 1, m):
                _, id_j, time_j = assign_points[j]
                if id_i == id_j:
                    self.solver.add(time_i != time_j)

    # ------------------------------
    # 2.2 Zones
    # ------------------------------

    def _encode_zones(self):
        """
        zones[i] = time of zone boundary i, with
          z_0   = 0
          z_last = endTime
          z_i < z_{i+1}  (strictly increasing)

        and we enforce a *bijection* between internal zones z_1..z_{last-1}
        and all task start/end times:

          - every task start/end equals some internal z_j
          - every internal z_j equals some task start or end
        """
        n = self.tn.endTime
        z = self.zones
        last = self.zone_count - 1
        tasks = self.all_scheduled_tasks

        # First / last
        self.add_tracked(z[0] == 0, "zone_boundary: first zone must be 0")
        self.add_tracked(z[last] == n, f"zone_boundary: last zone must be {n}")

        # Strictly increasing
        for i in range(last):
            self.add_tracked(z[i] < z[i + 1], f"zone_ordering: zone {i} must be < zone {i+1}")

        # Each start/end must be equal to *some* internal zone
        for t in tasks:
            s = self.start_vars[t.id]
            e = self.end_vars[t.id]
            self.add_tracked(Or(*[s == z[j] for j in range(1, last)]), f"task_zone_alignment: task '{t.id}' start must align with a zone")
            self.add_tracked(Or(*[e == z[j] for j in range(1, last)]), f"task_zone_alignment: task '{t.id}' end must align with a zone")

        # Each internal zone must be equal to *some* start or end
        for j in range(1, last):
            self.add_tracked(
                Or(*[
                    Or(self.start_vars[t.id] == z[j],
                       self.end_vars[t.id] == z[j])
                    for t in tasks
                ]), f"zone_bijection: zone {j} must equal some task start or end"
            )

    # ------------------------------
    # 2.3 State-at-zone variables
    # ------------------------------

    def _mk_zone_state_vars(self):
        Z = self.zone_count
        for tl in self.tn.timelines:
            if isinstance(tl, StateTimeline):
                states = tl.states
                s2i = {s: i for (i, s) in enumerate(states)}
                i2s = {i: s for (i, s) in enumerate(states)}
                vars_z = [Int(f"{tl.id}_z{j}") for j in range(Z)]
                self.state_tl_zone[tl.id] = (states, s2i, i2s, vars_z)
                # Constrain domain of state
                for v in vars_z:
                    self.solver.add(v >= 0, v < len(states))

            elif isinstance(tl, AtomicTimeline):
                # Use Int instead of Bool to support cumulative MAINT (claim/release)
                # Range [0,1] enforces mutual exclusion via overflow detection
                vars_z = [Int(f"{tl.id}_z{j}") for j in range(Z)]
                self.atomic_tl_zone[tl.id] = vars_z
                # Add range constraints [0,1] for all zones
                for i, v in enumerate(vars_z):
                    self.add_tracked(And(v >= 0, v <= 1), f"atomic_capacity: timeline '{tl.id}' must stay in [0,1] at zone {i}")

            elif isinstance(tl, ClaimableTimeline):
                vars_z = [Real(f"{tl.id}_z{j}") for j in range(Z)]
                self.numeric_tl_zone[tl.id] = (tl.range, None, vars_z)

            elif isinstance(tl, CumulativeTimeline):
                vars_z = [Real(f"{tl.id}_z{j}") for j in range(Z)]
                self.numeric_tl_zone[tl.id] = (tl.range, tl.bounds, vars_z)

            elif isinstance(tl, RateTimeline):
                # VALUE variables (as before)
                vars_z = [Real(f"{tl.id}_z{j}") for j in range(Z)]
                self.numeric_tl_zone[tl.id] = (tl.range, tl.bounds, vars_z)
                # RATE variables (new for dual tracking)
                rate_vars = [Real(f"{tl.id}_rate_z{j}") for j in range(Z)]
                self.rate_tl_rate_zone[tl.id] = rate_vars

    def _encode_initial_state_zones(self):
        # Zone 0 corresponds to time 0
        z0_idx = 0
        for tl in self.tn.timelines:
            if isinstance(tl, StateTimeline):
                _, s2i, _, vars_z = self.state_tl_zone[tl.id]
                if tl.initial is not None:
                   self.solver.add(vars_z[0] == s2i[tl.initial])

            elif isinstance(tl, AtomicTimeline):
                vars_z = self.atomic_tl_zone[tl.id]
                if getattr(tl, "initial", None) is not None:
                    # Initial value specified (0 or 1)
                    self.solver.add(vars_z[z0_idx] == tl.initial)
                else:
                    # Default to 0 (unclaimed) for atomic timelines
                    self.solver.add(vars_z[z0_idx] == 0)

            elif isinstance(tl, ClaimableTimeline):
                _, _, vars_z = self.numeric_tl_zone[tl.id]
                if tl.initial is not None:
                    self.solver.add(vars_z[0] == tl.initial)

            elif isinstance(tl, CumulativeTimeline):
                _, _, vars_z = self.numeric_tl_zone[tl.id]
                if tl.initial is not None:
                    self.solver.add(vars_z[0] == tl.initial)

            elif isinstance(tl, RateTimeline):
                # Initialize VALUE at zone 0
                _, _, vars_z = self.numeric_tl_zone[tl.id]
                if tl.initial is not None:
                    self.solver.add(vars_z[0] == tl.initial)
                # Initialize RATE at zone 0
                rate_vars = self.rate_tl_rate_zone[tl.id]
                if getattr(tl, "initial_rate", None) is not None:
                    self.solver.add(rate_vars[0] == tl.initial_rate)
                else:
                    # Default to 0 rate if not specified
                    self.solver.add(rate_vars[0] == 0.0)

    def _encode_initial_bounds(self):
        for tl in self.tn.timelines:
            if isinstance(tl, (CumulativeTimeline, RateTimeline)) and tl.bounds is not None:
                _, bounds, vars_z = self.numeric_tl_zone[tl.id]
                if isinstance(self.solver, Solver):
                    self.add_tracked(vars_z[0] >= bounds.low, f"initial_timeline_bounds: timeline '{tl.id}' initial value >= {bounds.low}")
                    self.add_tracked(vars_z[0] <= bounds.high, f"initial_timeline_bounds: timeline '{tl.id}' initial value <= {bounds.high}")
                else:
                    self.solver.add(vars_z[0] >= bounds.low, vars_z[0] <= bounds.high)

    def _encode_init_predicate(self):
        # init constraints apply at zone 0
        init_constraint = self._conds_holds_zone(self.tn.initial_constraints, 0)
        if isinstance(self.solver, Solver) and self.tn.initial_constraints:
            self.add_tracked(init_constraint, "initial_constraints: initial conditions must hold at start")
        else:
            self.solver.add(init_constraint)

    # ------------------------------
    # Impact semantics over zones
    # ------------------------------

    def _numeric_delta_zone(self, tl_id: str, zone_i: int):
        """
        Sum of all numeric deltas over zone i for ClaimableTimeline and CumulativeTimeline.
        RateTimeline now uses dual tracking and is handled separately.
        Zone i spans [z_i, z_{i+1}].
        """
        z = self.zones
        zi = z[zone_i]
        zi1 = z[zone_i + 1]
        dt = zi1 - zi

        terms = []
        for t in self.all_scheduled_tasks:
            s = self.start_vars[t.id]
            e = self.end_vars[t.id]
            if t.impacts is None:
                continue
            for imp in t.impacts:
                if imp.id != tl_id:
                    continue
                how = imp.how
                when = imp.when

                # CUMULATIVE: no dependence on dt, just boundary events
                if isinstance(how, ImpactCumulative):
                    v = how.v
                    if when == "pre":
                        # instant change at start time: applied at boundary zi
                        term = If(zi == s, v, 0.0)
                    elif when == "maint":
                        # +v at start, -v at end (as in previous discrete encoding)
                        term = If(zi == s, v, If(zi == e, -v, 0.0))
                    elif when == "post":
                        term = If(zi == e, v, 0.0)
                    else:
                        continue

                    # Guard with inclusion for optional/request tasks
                    if t.kind == TaskKind.OPTIONAL:
                        term = If(self.optional_included[t.id], term, 0.0)
                    elif t.kind == TaskKind.REQUEST:
                        term = If(self.request_included[t.id], term, 0.0)
                    terms.append(term)

                # RATE: Skip - RateTimeline uses dual tracking in _encode_zone_transitions
                elif isinstance(how, (ImpactRateCumulative, ImpactRateAssignment)):
                    # Skip - rate impacts are handled in dual tracking for RateTimeline
                    continue
                # Assign to numeric timelines: skip here, handled in _encode_zone_transitions
                elif isinstance(how, ImpactAssign):
                    # Skip - assignments are applied separately in zone transitions
                    continue

        if not terms:
            return 0.0
        total = terms[0]
        for term in terms[1:]:
            total = total + term
        return total

    def _encode_zone_transitions(self):
        """
        For each zone i, encode state_z[i+1] as a function of state_z[i],
        schedule, and impacts over that zone.
        """
        Z = self.zone_count

        # State / atomic timelines: assign-only, no numeric deltas
        for tl in self.tn.timelines:
            if isinstance(tl, StateTimeline):
                _, s2i, _, vars_z = self.state_tl_zone[tl.id]
                for i in range(Z - 1):
                    cur = vars_z[i]
                    expr = cur
                    zi = self.zones[i]
                    # Apply assigns at boundaries (pre/post)
                    for t in self.all_scheduled_tasks:
                        s = self.start_vars[t.id]
                        e = self.end_vars[t.id]
                        if t.impacts is None:
                            continue
                        for imp in t.impacts:
                            if imp.id != tl.id:
                                continue
                            if not isinstance(imp.how, ImpactAssign):
                                continue
                            v = imp.how.v
                            # Convert value to string for state lookup
                            if isinstance(v, StrVal):
                                value_str = v.v
                            elif isinstance(v, IntVal):
                                value_str = str(v.v)
                            elif isinstance(v, RealVal):
                                value_str = str(int(v.v)) if v.v.is_integer() else str(v.v)
                            else:
                                self.solver.add(False)
                                continue
                            idx = s2i[value_str]
                            # We apply assignments at the boundary *after* checking pre,
                            # i.e. they affect the transition to zone i+1.
                            if imp.when == "pre":
                                if t.kind == TaskKind.OPTIONAL:
                                    # For optional tasks: only apply if task is included
                                    expr = If(And(self.optional_included[t.id], zi == s), idx, expr)
                                elif t.kind == TaskKind.REQUEST:
                                    # For request tasks: only apply if task is included
                                    expr = If(And(self.request_included[t.id], zi == s), idx, expr)
                                else:
                                    expr = If(zi == s, idx, expr)
                            elif imp.when == "post":
                                if t.kind == TaskKind.OPTIONAL:
                                    expr = If(And(self.optional_included[t.id], zi == e), idx, expr)
                                elif t.kind == TaskKind.REQUEST:
                                    expr = If(And(self.request_included[t.id], zi == e), idx, expr)
                                else:
                                    expr = If(zi == e, idx, expr)
                            else:
                                # maint+assign disallowed
                                self.solver.add(False)
                    # Track state timeline evolution
                    if isinstance(self.solver, Solver):
                        self.add_tracked(vars_z[i + 1] == expr, f"state_timeline_evolution: timeline '{tl.id}' zone {i}->{i+1}")
                    else:
                        self.solver.add(vars_z[i + 1] == expr)

            elif isinstance(tl, AtomicTimeline):
                vars_z = self.atomic_tl_zone[tl.id]
                for i in range(Z - 1):
                    cur = vars_z[i]
                    # Start with delta-based value (for cumulative impacts)
                    delta = 0  # Will accumulate +1/-1 from tasks

                    zi = self.zones[i]

                    # Collect cumulative impacts (for claim/release MAINT pattern)
                    for t in self.all_scheduled_tasks:
                        s = self.start_vars[t.id]
                        e = self.end_vars[t.id]
                        if t.impacts is None:
                            continue
                        for imp in t.impacts:
                            if imp.id != tl.id:
                                continue

                            if isinstance(imp.how, ImpactCumulative):
                                v = imp.how.v  # Typically +1 (claim) or -1 (release)
                                if imp.when == "maint":
                                    # +v at start, -v at end (claim/release)
                                    delta = If(zi == s, delta + v,
                                              If(zi == e, delta - v, delta))
                                elif imp.when == "pre":
                                    delta = If(zi == s, delta + v, delta)
                                elif imp.when == "post":
                                    delta = If(zi == e, delta + v, delta)

                    # Apply delta to get next value
                    expr = cur + delta

                    # Apply assignments (override delta-based value)
                    for t in self.all_scheduled_tasks:
                        s = self.start_vars[t.id]
                        e = self.end_vars[t.id]
                        if t.impacts is None:
                            continue
                        for imp in t.impacts:
                            if imp.id != tl.id:
                                continue

                            # Assignment impacts (pre/post only, NOT maint)
                            if isinstance(imp.how, ImpactAssign):
                                v = imp.how.v
                                # Accept both IntVal (0/1) and BoolVal (true/false)
                                if isinstance(v, IntVal):
                                    int_val = v.v
                                elif isinstance(v, BoolVal):
                                    # Convert BoolVal to Int (true -> 1, false -> 0)
                                    int_val = 1 if v.v else 0
                                else:
                                    self.solver.add(False)
                                    continue

                                if imp.when == "pre":
                                    expr = If(zi == s, int_val, expr)
                                elif imp.when == "post":
                                    expr = If(zi == e, int_val, expr)
                                else:  # maint
                                    self.solver.add(False)  # Still reject maint+assign for atomic

                    # Track atomic timeline evolution
                    if isinstance(self.solver, Solver):
                        self.add_tracked(vars_z[i + 1] == expr, f"atomic_timeline_evolution: timeline '{tl.id}' zone {i}->{i+1}")
                    else:
                        self.solver.add(vars_z[i + 1] == expr)

        # Numeric timelines (Claimable and Cumulative): deltas + clamping by bounds
        # RateTimeline handled separately below due to dual tracking
        for tl in self.tn.timelines:
            if isinstance(tl, (ClaimableTimeline, CumulativeTimeline)):
                range_r, bounds_opt, vars_z = self.numeric_tl_zone[tl.id]

                if bounds_opt is not None:
                    low_bnd, high_bnd = bounds_opt.low, bounds_opt.high
                else:
                    low_bnd, high_bnd = None, None

                for i in range(Z - 1):
                    cur = vars_z[i]
                    delta = self._numeric_delta_zone(tl.id, i)
                    raw = cur + delta

                    if bounds_opt is not None:
                        clamped = If(raw < low_bnd, low_bnd,
                                     If(raw > high_bnd, high_bnd, raw))
                    else:
                        clamped = raw

                    # Start with delta-based value
                    expr = clamped
                    zi = self.zones[i]

                    # Apply assignments (they override the delta-based value)
                    for t in self.all_scheduled_tasks:
                        s = self.start_vars[t.id]
                        e = self.end_vars[t.id]
                        if t.impacts is None:
                            continue
                        for imp in t.impacts:
                            if imp.id != tl.id:
                                continue
                            if not isinstance(imp.how, ImpactAssign):
                                continue
                            v = imp.how.v
                            # Type check: must be numeric (IntVal or RealVal)
                            if isinstance(v, IntVal):
                                val = v.v
                            elif isinstance(v, RealVal):
                                val = v.v
                            else:
                                # Wrong type for numeric timeline
                                self.solver.add(False)
                                continue

                            if imp.when == "pre":
                                if t.kind == TaskKind.OPTIONAL:
                                    expr = If(And(self.optional_included[t.id], zi == s), val, expr)
                                elif t.kind == TaskKind.REQUEST:
                                    expr = If(And(self.request_included[t.id], zi == s), val, expr)
                                else:
                                    expr = If(zi == s, val, expr)
                            elif imp.when == "post":
                                if t.kind == TaskKind.OPTIONAL:
                                    expr = If(And(self.optional_included[t.id], zi == e), val, expr)
                                elif t.kind == TaskKind.REQUEST:
                                    expr = If(And(self.request_included[t.id], zi == e), val, expr)
                                else:
                                    expr = If(zi == e, val, expr)
                            else:
                                # maint+assign disallowed for numeric timelines
                                self.solver.add(False)

                    # Track numeric timeline evolution
                    if isinstance(self.solver, Solver):
                        timeline_type = "claimable" if isinstance(tl, ClaimableTimeline) else "cumulative"
                        self.add_tracked(vars_z[i + 1] == expr, f"{timeline_type}_timeline_evolution: timeline '{tl.id}' zone {i}->{i+1}")
                    else:
                        self.solver.add(vars_z[i + 1] == expr)

        # Rate timelines: dual tracking of VALUE and RATE
        for tl in self.tn.timelines:
            if isinstance(tl, RateTimeline):
                range_r, bounds_opt, value_vars = self.numeric_tl_zone[tl.id]
                rate_vars = self.rate_tl_rate_zone[tl.id]

                if bounds_opt is not None:
                    low_bnd, high_bnd = bounds_opt.low, bounds_opt.high
                else:
                    low_bnd, high_bnd = None, None

                for i in range(Z - 1):
                    zi = self.zones[i]
                    zi1 = self.zones[i + 1]
                    dt = zi1 - zi

                    cur_value = value_vars[i]
                    cur_rate = rate_vars[i]

                    # ===== Update RATE variable =====
                    # Compute rate[i+1] from rate[i]

                    # Step 1: Apply cumulative rate deltas at boundary zi+1
                    rate_delta = 0.0
                    for t in self.all_scheduled_tasks:
                        s = self.start_vars[t.id]
                        e = self.end_vars[t.id]
                        if t.impacts is None:
                            continue
                        for imp in t.impacts:
                            if imp.id != tl.id:
                                continue

                            if isinstance(imp.how, ImpactRateCumulative):
                                delta = imp.how.delta
                                # Apply deltas that occur at the END of this zone (zi+1)
                                if imp.when == "pre":
                                    # Pre happens when zi+1 == task start
                                    term = If(zi1 == s, delta, 0.0)
                                elif imp.when == "maint":
                                    # +delta at start, -delta at end
                                    term = If(zi1 == s, delta, If(zi1 == e, -delta, 0.0))
                                elif imp.when == "post":
                                    # Post happens when zi+1 == task end
                                    term = If(zi1 == e, delta, 0.0)
                                else:
                                    continue

                                if t.kind == TaskKind.OPTIONAL:
                                    term = If(self.optional_included[t.id], term, 0.0)
                                elif t.kind == TaskKind.REQUEST:
                                    term = If(self.request_included[t.id], term, 0.0)
                                rate_delta = rate_delta + term

                    # Base rate: cur_rate + cumulative deltas (before assignments)
                    base_rate = cur_rate + rate_delta

                    # Step 2: Apply rate assignments at boundary zi+1
                    rate_expr = base_rate
                    for t in self.all_scheduled_tasks:
                        s = self.start_vars[t.id]
                        e = self.end_vars[t.id]
                        if t.impacts is None:
                            continue
                        for imp in t.impacts:
                            if imp.id != tl.id:
                                continue

                            if isinstance(imp.how, ImpactRateAssignment):
                                r = imp.how.r
                                if imp.when == "pre":
                                    # Assign when zi+1 == task start
                                    if t.kind == TaskKind.OPTIONAL:
                                        rate_expr = If(And(self.optional_included[t.id], zi1 == s), r, rate_expr)
                                    elif t.kind == TaskKind.REQUEST:
                                        rate_expr = If(And(self.request_included[t.id], zi1 == s), r, rate_expr)
                                    else:
                                        rate_expr = If(zi1 == s, r, rate_expr)
                                elif imp.when == "post":
                                    # Assign when zi+1 == task end
                                    if t.kind == TaskKind.OPTIONAL:
                                        rate_expr = If(And(self.optional_included[t.id], zi1 == e), r, rate_expr)
                                    elif t.kind == TaskKind.REQUEST:
                                        rate_expr = If(And(self.request_included[t.id], zi1 == e), r, rate_expr)
                                    else:
                                        rate_expr = If(zi1 == e, r, rate_expr)
                                elif imp.when == "maint":
                                    # MAINT not supported for assignment (cannot restore correctly)
                                    # Already checked in wellformedness
                                    self.solver.add(False)

                    # Track rate timeline rate evolution
                    if isinstance(self.solver, Solver):
                        self.add_tracked(rate_vars[i + 1] == rate_expr, f"rate_timeline_rate_evolution: timeline '{tl.id}' zone {i}->{i+1}")
                    else:
                        self.solver.add(rate_vars[i + 1] == rate_expr)

                    # ===== Update VALUE variable =====
                    # Compute value[i+1] from value[i]
                    # Value evolves as: value[i+1] = value[i] + rate[i] * dt

                    # Step 1: Integrate rate over the zone
                    # Use cur_rate (rate at start of zone, which is rate[i])
                    integrated_value = cur_value + cur_rate * dt

                    # Step 2: Add cumulative VALUE impacts at boundary zi+1
                    value_delta = 0.0
                    for t in self.all_scheduled_tasks:
                        s = self.start_vars[t.id]
                        e = self.end_vars[t.id]
                        if t.impacts is None:
                            continue
                        for imp in t.impacts:
                            if imp.id != tl.id:
                                continue

                            if isinstance(imp.how, ImpactCumulative):
                                v = imp.how.v
                                if imp.when == "pre":
                                    term = If(zi1 == s, v, 0.0)
                                elif imp.when == "maint":
                                    term = If(zi1 == s, v, If(zi1 == e, -v, 0.0))
                                elif imp.when == "post":
                                    term = If(zi1 == e, v, 0.0)
                                else:
                                    continue

                                if t.kind == TaskKind.OPTIONAL:
                                    term = If(self.optional_included[t.id], term, 0.0)
                                elif t.kind == TaskKind.REQUEST:
                                    term = If(self.request_included[t.id], term, 0.0)
                                value_delta = value_delta + term

                    raw_value = integrated_value + value_delta

                    # Step 3: Apply bounds clamping
                    if bounds_opt is not None:
                        clamped_value = If(raw_value < low_bnd, low_bnd,
                                          If(raw_value > high_bnd, high_bnd, raw_value))
                    else:
                        clamped_value = raw_value

                    # Step 4: Apply value assignments at boundary zi+1
                    value_expr = clamped_value
                    for t in self.all_scheduled_tasks:
                        s = self.start_vars[t.id]
                        e = self.end_vars[t.id]
                        if t.impacts is None:
                            continue
                        for imp in t.impacts:
                            if imp.id != tl.id:
                                continue

                            if isinstance(imp.how, ImpactAssign):
                                v = imp.how.v
                                if isinstance(v, IntVal):
                                    val = v.v
                                elif isinstance(v, RealVal):
                                    val = v.v
                                else:
                                    self.solver.add(False)
                                    continue

                                if imp.when == "pre":
                                    if t.kind == TaskKind.OPTIONAL:
                                        value_expr = If(And(self.optional_included[t.id], zi1 == s), val, value_expr)
                                    elif t.kind == TaskKind.REQUEST:
                                        value_expr = If(And(self.request_included[t.id], zi1 == s), val, value_expr)
                                    else:
                                        value_expr = If(zi1 == s, val, value_expr)
                                elif imp.when == "post":
                                    if t.kind == TaskKind.OPTIONAL:
                                        value_expr = If(And(self.optional_included[t.id], zi1 == e), val, value_expr)
                                    elif t.kind == TaskKind.REQUEST:
                                        value_expr = If(And(self.request_included[t.id], zi1 == e), val, value_expr)
                                    else:
                                        value_expr = If(zi1 == e, val, value_expr)
                                # MAINT not allowed for value assignments on rate timelines

                    # Track rate timeline value evolution
                    if isinstance(self.solver, Solver):
                        self.add_tracked(value_vars[i + 1] == value_expr, f"rate_timeline_value_evolution: timeline '{tl.id}' zone {i}->{i+1}")
                    else:
                        self.solver.add(value_vars[i + 1] == value_expr)

    def _encode_timeline_ranges(self):
        """
        Enforce TimeLineRangeOk: for numeric timelines, the value at *all*
        zone boundaries lies within the declared RealRange.
        (State timelines are already domain-restricted, atomic are Bool.)
        """
        for tl_id, (range_r, _bounds, vars_z) in self.numeric_tl_zone.items():
            lo, hi = range_r.low, range_r.high
            for i, v in enumerate(vars_z):
                self.add_tracked(And(v >= lo, v <= hi), f"timeline_range: timeline '{tl_id}' must stay in [{lo},{hi}] at zone {i}")

    # ------------------------------
    # pre / inv / post (zone-based)
    # ------------------------------

    def _tl_value_at_zone(self, tl_id: str, zi: int):
        """
        Return a pair (kind, expr) describing the value of timeline tl_id at zone index zi.
        kind in {"state", "atomic", "real"} with the appropriate Z3 expression.
        """
        if tl_id in self.state_tl_zone:
            _, _, _, vars_z = self.state_tl_zone[tl_id]
            return "state", vars_z[zi]
        if tl_id in self.atomic_tl_zone:
            vars_z = self.atomic_tl_zone[tl_id]
            return "atomic", vars_z[zi]
        if tl_id in self.numeric_tl_zone:
            _, _, vars_z = self.numeric_tl_zone[tl_id]
            return "real", vars_z[zi]
        # Unknown timeline id: impossible in well-formed spec
        self.solver.add(False)
        dummy = Real("dummy_unknown_timeline")
        return "real", dummy

    def _con_holds_zone(self, tl_id: str, con: Con, zi: int):
        """
        SMT formula for a single Con on timeline tl_id at zone index zi.
        A TlCon is OR over such formulas.
        """
        kind, expr = self._tl_value_at_zone(tl_id, zi)

        if isinstance(con, ConVal):
            v = con.v
            if isinstance(v, StrVal):
                if kind != "state":
                    self.solver.add(False)
                    return False
                _, s2i, _, _ = self.state_tl_zone[tl_id]
                idx = s2i[v.v]
                return expr == idx

            if isinstance(v, BoolVal):
                if kind != "atomic":
                    self.solver.add(False)
                    return False
                return expr == v.v

            if isinstance(v, IntVal):
                # Check if it's a state timeline with numeric states
                if kind == "state":
                    _, s2i, _, _ = self.state_tl_zone[tl_id]
                    idx = s2i[str(v.v)]
                    return expr == idx
                # Otherwise treat as equality on real-valued numeric TL
                elif kind == "real":
                    return expr == v.v
                else:
                    self.solver.add(False)
                    return False

            if isinstance(v, RealVal):
                # Check if it's a state timeline with numeric states
                if kind == "state":
                    _, s2i, _, _ = self.state_tl_zone[tl_id]
                    value_str = str(int(v.v)) if v.v.is_integer() else str(v.v)
                    idx = s2i[value_str]
                    return expr == idx
                # Otherwise treat as equality on real-valued numeric TL
                elif kind == "real":
                    return expr == v.v
                else:
                    self.solver.add(False)
                    return False

        elif isinstance(con, ConRealRange):
            if kind != "real":
                self.solver.add(False)
                return False
            lo, hi = con.r.low, con.r.high
            return And(expr >= lo, expr <= hi)

        elif isinstance(con, ConIntRange):
            if kind != "real":
                self.solver.add(False)
                return False
            lo, hi = con.r.low, con.r.high
            return And(expr >= lo, expr <= hi)

        # Unsupported combination; forbid
        self.solver.add(False)
        return False

    def _tlcon_holds_zone(self, tlc: TlCon, zi: int):
        """
        SMT formula for one TlCon at zone index zi:
          OR over its cons.
        """
        if not tlc.cons:
            # Empty list => False
            return False
        clauses = [self._con_holds_zone(tlc.id, c, zi) for c in tlc.cons]
        return Or(*clauses)

    def _conds_holds_zone(self, conds: List[TlCon], zi: int):
        """
        SMT formula for a list of TlCon at zone index zi:
          AND over TlCon (each TlCon is an OR of Cons).
        Empty list => True.
        """
        if not conds:
            return True
        return And(*[self._tlcon_holds_zone(c, zi) for c in conds])

    def _encode_pre_inv_post_zones(self):
        """
        Zone-based obligations:

        For each task t:

          - PRE:
              For each zone index j:
                (start_t == z_j) -> pre holds at zone j.

          - POST:
              For each zone index j:
                (end_t == z_j) -> post holds at zone j.

          - INV:
              For each zone index j:
                (z_j in [start_t, end_t]) -> inv holds at zone j.
        """
        Z = self.zone_count
        z = self.zones

        for t in self.all_scheduled_tasks:
            s = self.start_vars[t.id]
            e = self.end_vars[t.id]

            for j in range(Z):
                pre_formula  = self._conds_holds_zone(t.pre, j) if t.pre else True
                inv_formula  = self._conds_holds_zone(t.inv, j) if t.inv else True
                post_formula = self._conds_holds_zone(t.post, j) if t.post else True

                zj = z[j]

                # Guard constraints for optional tasks
                if t.kind == TaskKind.OPTIONAL:
                    # Only enforce constraints if task is included
                    # PRE at start: either not included, or zone != start, or pre holds
                    if t.pre:  # Only track if pre condition exists
                        pre_desc = self._format_conditions(t.pre)
                        self.add_tracked(Or(Not(self.optional_included[t.id]), zj != s, pre_formula),
                                       f"precondition: task '{t.id}' requires {pre_desc} at start (zone {j})")
                    else:
                        self.solver.add(Or(Not(self.optional_included[t.id]), zj != s, pre_formula))

                    # POST at end: either not included, or zone != end, or post holds
                    if t.post:  # Only track if post condition exists
                        post_desc = self._format_conditions(t.post)
                        self.add_tracked(Or(Not(self.optional_included[t.id]), zj != e, post_formula),
                                       f"postcondition: task '{t.id}' requires {post_desc} at end (zone {j})")
                    else:
                        self.solver.add(Or(Not(self.optional_included[t.id]), zj != e, post_formula))

                    # INV whenever active: either not included, or zone outside [start, end], or inv holds
                    if t.inv:  # Only track if inv condition exists
                        inv_desc = self._format_conditions(t.inv)
                        self.add_tracked(
                            Or(
                                Not(self.optional_included[t.id]),
                                zj < s,
                                zj > e,
                                inv_formula
                            ),
                            f"invariant: task '{t.id}' requires {inv_desc} during execution (zone {j})"
                        )
                    else:
                        self.solver.add(
                            Or(
                                Not(self.optional_included[t.id]),
                                zj < s,
                                zj > e,
                                inv_formula
                            )
                        )
                else:
                    # Required task - always enforce constraints
                    # PRE at start
                    if t.pre:  # Only track if pre condition exists
                        pre_desc = self._format_conditions(t.pre)
                        self.add_tracked(Or(zj != s, pre_formula), f"precondition: task '{t.id}' requires {pre_desc} at start (zone {j})")
                    else:
                        self.solver.add(Or(zj != s, pre_formula))

                    # POST at end
                    if t.post:  # Only track if post condition exists
                        post_desc = self._format_conditions(t.post)
                        self.add_tracked(Or(zj != e, post_formula), f"postcondition: task '{t.id}' requires {post_desc} at end (zone {j})")
                    else:
                        self.solver.add(Or(zj != e, post_formula))

                    # INV whenever active (inclusive bounds)
                    if t.inv:  # Only track if inv condition exists
                        inv_desc = self._format_conditions(t.inv)
                        self.add_tracked(
                            Or(
                                zj < s,
                                zj > e,
                                inv_formula
                            ),
                            f"invariant: task '{t.id}' requires {inv_desc} during execution (zone {j})"
                        )
                    else:
                        self.solver.add(
                            Or(
                                zj < s,
                                zj > e,
                                inv_formula
                            )
                        )

    # ------------------------------
    # Solving + pretty-printing
    # ------------------------------

    def solve(self):
        # Add optimization objectives if using Optimize
        if isinstance(self.solver, Optimize):
            # 1a. Primary objective: minimize the number of included optional tasks
            if self.optional_tasks:
                objective_optional = Sum([If(self.optional_included[t.id], 1, 0) for t in self.optional_tasks])
                self.solver.minimize(objective_optional)

            # 1b. Primary objective: maximize the number of included request tasks
            if self.request_tasks:
                objective_request = Sum([If(self.request_included[t.id], 1, 0) for t in self.request_tasks])
                self.solver.maximize(objective_request)

            # 2. Secondary objective: maximize priority-weighted benefit
            # Higher priority values = higher importance = higher benefit
            # Benefit = sum of (priority * inclusion_factor) for all tasks
            priority_terms = []
            for t in self.all_scheduled_tasks:
                if t.priority is not None:
                    if t.kind == TaskKind.OPTIONAL:
                        # For optional tasks, only count if included
                        priority_terms.append(If(self.optional_included[t.id], t.priority, 0))
                    elif t.kind == TaskKind.REQUEST:
                        # For request tasks, only count if included
                        priority_terms.append(If(self.request_included[t.id], t.priority, 0))
                    else:
                        # For required tasks, always count
                        priority_terms.append(t.priority)

            if priority_terms:
                objective_priority = Sum(priority_terms)
                self.solver.maximize(objective_priority)

            # 3. Tertiary objective: minimize deviation from preferred start times
            # Cost = sum of |actual_start - preferred_start| for tasks with preferred starts
            start_deviation_terms = []
            for t in self.all_scheduled_tasks:
                if t.start is not None:
                    s = self.start_vars[t.id]
                    # Absolute difference: max(s - start, start - s)
                    diff = If(s >= t.start, s - t.start, t.start - s)

                    if t.kind == TaskKind.OPTIONAL:
                        # For optional tasks, only count deviation if included
                        start_deviation_terms.append(If(self.optional_included[t.id], diff, 0))
                    elif t.kind == TaskKind.REQUEST:
                        # For request tasks, only count deviation if included
                        start_deviation_terms.append(If(self.request_included[t.id], diff, 0))
                    else:
                        # For required tasks, always count deviation
                        start_deviation_terms.append(diff)

            if start_deviation_terms:
                objective_start_deviation = Sum(start_deviation_terms)
                self.solver.minimize(objective_start_deviation)

            # 4. Quaternary objective: minimize deviation from preferred durations
            # Cost = sum of |actual_duration - preferred_duration| for tasks with preferred durations
            duration_deviation_terms = []
            for t in self.all_scheduled_tasks:
                if t.dur is not None:
                    s = self.start_vars[t.id]
                    e = self.end_vars[t.id]
                    actual_dur = e - s
                    # Absolute difference: max(actual_dur - dur, dur - actual_dur)
                    diff = If(actual_dur >= t.dur, actual_dur - t.dur, t.dur - actual_dur)

                    if t.kind == TaskKind.OPTIONAL:
                        # For optional tasks, only count deviation if included
                        duration_deviation_terms.append(If(self.optional_included[t.id], diff, 0))
                    elif t.kind == TaskKind.REQUEST:
                        # For request tasks, only count deviation if included
                        duration_deviation_terms.append(If(self.request_included[t.id], diff, 0))
                    else:
                        # For required tasks, always count deviation
                        duration_deviation_terms.append(diff)

            if duration_deviation_terms:
                objective_duration_deviation = Sum(duration_deviation_terms)
                self.solver.minimize(objective_duration_deviation)

        res = self.solver.check()
        if res != sat:
            print("TaskNet constraints (schedule + zone trace):", res)

            # If using Solver (not Optimize), retrieve and display unsat core
            if isinstance(self.solver, Solver):
                core = self.solver.unsat_core()
                tracked_count = getattr(self, '_tracked_count', 0)
                total_assertions = len(self.solver.assertions())
                print(f"\nDEBUG: Solver type: {type(self.solver).__name__}, Core size: {len(core)}, Tracked constraints: {tracked_count}, Total assertions: {total_assertions}")
                if len(core) > 0:
                    print(f"DEBUG: First 5 core items: {[str(c) for c in list(core)[:5]]}")
                if len(core) == 0:
                    print("\nUNSAT CORE: Empty (constraints not tracked)")
                    print("Hint: The conflict involves untracked constraints.")
                else:
                    print(f"\nUNSAT CORE ({len(core)} conflicting constraints)")

                    # Group by category
                    by_category = {}
                    for constraint in core:
                        label = str(constraint)
                        # Extract category from label (e.g., "dependency_after: ..." -> "dependency_after")
                        if ':' in label:
                            category = label.split(':', 1)[0].strip()
                        elif '_' in label:
                            parts = label.split('_')
                            if len(parts) >= 2:
                                category = f"{parts[0]}_{parts[1]}"
                            else:
                                category = parts[0]
                        else:
                            category = 'other'
                        by_category.setdefault(category, []).append(label)

                    # Provide detailed analysis
                    self._analyze_unsat_core(by_category)

                    # Suggest actions
                    print("\nSuggestions:")
                    if any('dependency' in cat for cat in by_category):
                        print("  • Check task start/end ranges for conflicts")
                        print("  • Review task ordering constraints (after, containedin)")
                    if any(cat in by_category for cat in ['atomic_capacity', 'timeline_range']):
                        print("  • Check timeline capacity and resource bounds")
                        print("  • Verify tasks don't exceed timeline limits")
                    if any('precondition' in cat or 'postcondition' in cat or 'invariant' in cat for cat in by_category):
                        print("  • Review task pre/post/inv conditions")
                        print("  • Check if timeline values can satisfy required conditions")
                    if any(cat in by_category for cat in ['task_start_range', 'task_end_range', 'task_duration_range', 'task_timing']):
                        print("  • Widen start_range constraints to allow more flexibility")
                        print("  • Adjust duration_range if tasks are overconstrained")
                        print("  • Look for fixed start times that conflict with dependencies")
                    if 'zone_ordering' in by_category or 'task_zone_alignment' in by_category:
                        print("  • Review task timing constraints (start/duration ranges)")
                        print("  • Check for impossible combinations of fixed times and dependencies")
                        print("  • Consider increasing the time horizon (end value)")

                    # Show raw Z3 unsat core for advanced debugging
                    print(f"\n--- Raw Z3 Unsat Core ({len(core)} formulas) ---")
                    for i, constraint in enumerate(core, 1):
                        print(f"{i}. {constraint}")

            return None
        return self.solver.model()

    def extract_schedule(self, model):
        sched: Dict[str, Tuple[int, int]] = {}
        for t in self.all_scheduled_tasks:
            s_val = model[self.start_vars[t.id]]
            e_val = model[self.end_vars[t.id]]
            sched[t.id] = (int(s_val.as_long()), int(e_val.as_long()))
        return sched

    def pretty_print(self, model):
        # 1) Schedule
        print(f"Schedule for TaskNet `{self.tn.id}`:")
        sched = self.extract_schedule(model)
        for t in self.all_scheduled_tasks:
            # Check if optional/request task is included
            if t.kind == TaskKind.OPTIONAL:
                included = model[self.optional_included[t.id]]
                if not included:
                    print(f"  {t.id:14s}: [OPTIONAL - NOT INCLUDED]")
                    continue
            elif t.kind == TaskKind.REQUEST:
                included = model[self.request_included[t.id]]
                if not included:
                    print(f"  {t.id:14s}: [REQUEST - NOT INCLUDED]")
                    continue
            s, e = sched[t.id]
            print(f"  {t.id:14s}: start = {s:4d}, end = {e:4d}")

        # 2) Zone boundaries
        print("\nZone boundaries (z_i):")
        for i, zi in enumerate(self.zones):
            val = model[zi].as_long()
            print(f"  z_{i:2d} = {val}")

        # 3) Values in each zone ( (z_j, z_{j+1}] )
        print("\nValues in each zone:")
        Z = self.zone_count
        for j in range(Z - 1):
            t0 = model[self.zones[j]].as_long()
            t1 = model[self.zones[j + 1]].as_long()
            print(f"\n  -- zone {j}: ({t0}, {t1}] --")

            # Use LEFT boundary t0 to decide activity:
            # task active in zone j iff start_t ≤ t0 < end_t
            active: List[str] = []
            for t in self.all_scheduled_tasks:
                # Skip optional/request tasks that aren't included
                if t.kind == TaskKind.OPTIONAL:
                    included = model[self.optional_included[t.id]]
                    if not included:
                        continue
                elif t.kind == TaskKind.REQUEST:
                    included = model[self.request_included[t.id]]
                    if not included:
                        continue
                s, e = sched[t.id]
                if s <= t0 < e:
                    active.append(t.id)

            if active:
                print(f"    active tasks : {', '.join(active)}")
            else:
                print(f"    active tasks : (none)")

            # For non-rate timelines, interior value is piecewise constant
            # and represented by state at boundary j+1.
            idx_interior = j + 1

            for tl in self.tn.timelines:
                # --- State timelines ---
                if isinstance(tl, StateTimeline):
                    _, _, i2s, vars_z = self.state_tl_zone[tl.id]
                    idx = model[vars_z[idx_interior]].as_long()
                    print(f"    {tl.id:14s} = {i2s[idx]}")

                # --- Atomic timelines ---
                elif isinstance(tl, AtomicTimeline):
                    vars_z = self.atomic_tl_zone[tl.id]
                    val = model[vars_z[idx_interior]]
                    print(f"    {tl.id:14s} = {val}")

                # --- Numeric timelines: piecewise-constant types ---
                elif isinstance(tl, (ClaimableTimeline, CumulativeTimeline)):
                    _, _, vars_z = self.numeric_tl_zone[tl.id]
                    val = model[vars_z[idx_interior]]
                    print(f"    {tl.id:14s} = {val.as_decimal(6)}")

                # --- Numeric timelines: rate types ---
                elif isinstance(tl, RateTimeline):
                    _, _, vars_z = self.numeric_tl_zone[tl.id]
                    v_start = model[vars_z[j]]
                    v_end   = model[vars_z[j + 1]]

                    # Get rate during this zone (use left boundary j)
                    # The rate at z_j is what integrates over interval (z_j, z_{j+1}]
                    rate_vars = self.rate_tl_rate_zone[tl.id]
                    rate = model[rate_vars[j]]

                    print(
                        f"    {tl.id:14s} = "
                        f"{v_start.as_decimal(6)} -> {v_end.as_decimal(6)} "
                        f"(rate: {rate.as_decimal(6)})"
                    )

class TaskNetTL(TaskNetSMT):
    """Temporal logic interpretation"""

    def __init__(self, tn: TaskNet, error_trace: bool = True, use_optimization: bool = True):
        super().__init__(tn, use_optimization=use_optimization)
        self._encode_temporal_constraints()
        self.error_trace = error_trace

    def _encode_temporal_constraints(self):
        # each constraint prop must hold at position 0
        for prop in getattr(self.tn, "constraints", []):
            self.solver.add(self._encode_formula_at_pos(prop.formula, 0))

    def _encode_formula_at_pos(self, f: Formula, j: int):
        Z = self.zone_count

        # Atomic
        if isinstance(f, TLNumCmp):
            kind, expr = self._tl_value_at_zone(f.tl, j)
            if kind != "real":
                self.solver.add(False)
                return False
            if f.op == "<":
                return expr < f.bound
            elif f.op == "<=":
                return expr <= f.bound
            elif f.op == "=":
                return expr == f.bound
            elif f.op == ">":
                return expr > f.bound
            elif f.op == ">=":
                return expr >= f.bound
            self.solver.add(False)
            return False

        if isinstance(f, TLStateIs):
            kind, expr = self._tl_value_at_zone(f.tl, j)
            if kind != "state":
                self.solver.add(False)
                return False
            _, s2i, _, _ = self.state_tl_zone[f.tl]
            idx = s2i[f.value]
            return expr == idx

        if isinstance(f, TLBoolIs):
            kind, expr = self._tl_value_at_zone(f.tl, j)
            if kind != "atomic":
                self.solver.add(False)
                return False
            return expr == f.value

        if isinstance(f, TLAnd):
            return And(self._encode_formula_at_pos(f.left, j),
                       self._encode_formula_at_pos(f.right, j))

        if isinstance(f, TLOr):
            return Or(self._encode_formula_at_pos(f.left, j),
                      self._encode_formula_at_pos(f.right, j))

        if isinstance(f, TLNot):
            return Not(self._encode_formula_at_pos(f.sub, j))

        if isinstance(f, TLImplies):
            return Or(Not(self._encode_formula_at_pos(f.left, j)),
                      self._encode_formula_at_pos(f.right, j))

        if isinstance(f, TLAlways):
            if j >= Z:
                return True
            return And(*[self._encode_formula_at_pos(f.sub, k)
                         for k in range(j, Z)])

        if isinstance(f, TLEventually):
            if j >= Z:
                return False
            return Or(*[self._encode_formula_at_pos(f.sub, k)
                        for k in range(j, Z)])

        if isinstance(f, TLUntil):
            if j >= Z:
                return False
            disjuncts = []
            for k in range(j, Z):
                right_k = self._encode_formula_at_pos(f.right, k)
                if j == k:
                    # No positions in [j, k), so left-part is True
                    left_part = True
                else:
                    left_conjuncts = [
                        self._encode_formula_at_pos(f.left, m)
                        for m in range(j, k)
                    ]
                    left_part = And(*left_conjuncts) if left_conjuncts else True
                disjuncts.append(And(right_k, left_part))
            return Or(*disjuncts) if disjuncts else False
            
        if isinstance(f, TLSoFar):
            if j < 0:
                return True
            conjuncts = [
                self._encode_formula_at_pos(f.sub, k)
                for k in range(0, j + 1)
            ]
            return And(*conjuncts) if conjuncts else True

        if isinstance(f, TLOnce):
            if j < 0:
                return False
            disjuncts = [
                self._encode_formula_at_pos(f.sub, k)
                for k in range(0, j + 1)
            ]
            return Or(*disjuncts) if disjuncts else False

        if isinstance(f, TLSince):
            if j < 0:
                return False
            disjuncts = []
            for k in range(0, j + 1):
                right_k = self._encode_formula_at_pos(f.right, k)
                if k == j:
                    # No positions in (k, j], so left-part is True
                    left_part = True
                else:
                    left_conjuncts = [
                        self._encode_formula_at_pos(f.left, m)
                        for m in range(k + 1, j + 1)
                    ]
                    left_part = And(*left_conjuncts) if left_conjuncts else True
                disjuncts.append(And(right_k, left_part))
            return Or(*disjuncts) if disjuncts else False
            
        self.solver.add(False)
        return False
      
    def check_temporal_properties(self):
        """
        For each TemporalProperty in self.tn.properties, check whether it holds
        for all schedules/zone-traces that satisfy:
          - schedule/zone semantics
          - initial_constraints (zone 0)
          - temporal constraints (self.tn.constraints) at position 0

        Additionally, report vacuity:
          - If there is NO model satisfying the base constraints, then every
            property "holds" vacuously, but the spec is UNREALIZABLE.
        """
        print()

        # 0) If no properties, done.
        if not getattr(self.tn, "properties", None):
            print("\nNo temporal properties attached to this TaskNet.")
            return
        else:
            print(f"Checking {len(self.tn.properties)} temporal properties:")

        # Realizability already verified by initial validity check in tasknet_verifier.py
        # Skip redundant check to eliminate one solver call (optimization)

        # PROPERTY CHECKS: look for counterexamples
        import sys
        total_props = len(self.tn.properties)
        holds_count = 0
        violated_count = 0
        unknown_count = 0

        for idx, prop in enumerate(self.tn.properties, start=1):
            # Show progress indicator before checking - with newline to force flush
            print(f"[{idx}/{total_props}] Checking property '{prop.name}'...")
            sys.stdout.flush()

            # Always use Solver() for property checks (faster counterexample finding)
            # use_optimization=False ensures we use Solver() even if main schedule used Optimize()
            enc = TaskNetTL(self.tn, error_trace=self.error_trace, use_optimization=False)
            phi = prop.formula
            enc.solver.add(Not(enc._encode_formula_at_pos(phi, 0)))

            # Set timeout to prevent hanging on difficult properties (10 seconds)
            enc.solver.set("timeout", 10000)

            res = enc.solver.check()
            if res == sat:
                print("  → VIOLATED!")
                violated_count += 1
                if self.error_trace:
                    print("Counterexample:\n")
                    model = enc.solver.model()
                    enc.pretty_print(model)
            elif str(res) == "unsat":
                print("  → HOLDS")
                holds_count += 1
            else:
                print("  → UNKNOWN")
                unknown_count += 1

        # Print summary
        print()
        print(f"Summary: {holds_count} hold, {violated_count} violated, {unknown_count} unknown")
        print()
   