
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
        self.all_scheduled_tasks = self.required_tasks + self.optional_tasks

        # === Optional task inclusion variables ===
        self.optional_included: Dict[str, object] = {}
        for t in self.optional_tasks:
            self.optional_included[t.id] = Bool(f"included_{t.id}")

        # Use Optimize if we have optional tasks and optimization is enabled, otherwise use Solver
        if self.optional_tasks and use_optimization:
            self.solver = Optimize()
        else:
            self.solver = Solver()
            # Enable unsat core tracking for Solver (not available for Optimize)
            self.solver.set(unsat_core=True)

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

        self._mk_zone_state_vars()
        self._encode_initial_state_zones()
        self._encode_initial_bounds()
        self._encode_init_predicate()
        self._encode_zone_transitions()
        self._encode_timeline_ranges()
        self._encode_pre_inv_post_zones()

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

            if t.definition is not None:
                # Merge with definition
                if t.definition not in definitions:
                    raise ValueError(f"Task {t.id} references undefined definition {t.definition}")

                defn = definitions[t.definition]
                resolved_tasks.append(self._merge_task_with_definition(t, defn))
            else:
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
            definition=None,  # Already resolved
            priority=instance.priority if instance.priority is not None else definition.priority,
            startrng=instance.startrng if instance.startrng is not None else definition.startrng,
            endrng=instance.endrng if instance.endrng is not None else definition.endrng,
            durrng=instance.durrng if instance.durrng is not None else definition.durrng,
            dur=instance.dur if instance.dur is not None else definition.dur,
            start=instance.start if instance.start is not None else definition.start,
            after=instance.after if instance.after is not None else definition.after,
            containedin=instance.containedin if instance.containedin is not None else definition.containedin,
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
                if getattr(tl, "bounds", None) is None:
                    tl.bounds = RealRange(tl.range.low, tl.range.high)

            elif isinstance(tl, RateTimeline):
                if getattr(tl, "range", None) is None:
                    tl.range = RealRange(MIN_REAL, MAX_REAL)
                if getattr(tl, "bounds", None) is None:
                    tl.bounds = RealRange(tl.range.low, tl.range.high)

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

        # Basic constraints for each task
        for t in tasks:
            s = self.start_vars[t.id]
            e = self.end_vars[t.id]

            # Helper to conditionally add constraint for optional tasks
            def add_constraint(*args):
                if t.kind == TaskKind.OPTIONAL:
                    # Only apply constraint if task is included
                    self.solver.add(If(self.optional_included[t.id], And(*args), True))
                else:
                    # Required task - always apply constraint
                    self.solver.add(*args)

            # Start/end within global horizon and ordered
            add_constraint(s >= 0, s <= e, e <= n)

            # start,end within given ranges
            if t.startrng is not None:
                add_constraint(s >= t.startrng.low, s <= t.startrng.high)
            if t.endrng is not None:
                add_constraint(e >= t.endrng.low, e <= t.endrng.high)

            # duration range constraint
            if t.durrng is not None:
                add_constraint(e - s >= t.durrng.low, e - s <= t.durrng.high)

            # duration (now treated as preferred duration, not a hard constraint)
            # This will be handled in the optimization objective instead
            # if t.dur is not None:
            #     add_constraint(e - s == t.dur)

            # after dependencies
            if t.after is not None:
                for bid in t.after:
                    if bid not in self.end_vars:
                        # ill-formed TaskNet — forbid
                        self.solver.add(False)
                    else:
                        add_constraint(self.end_vars[bid] <= s)

            # containedin dependencies
            if t.containedin is not None:
                for pid in t.containedin:
                    if pid not in self.start_vars or pid not in self.end_vars:
                        # ill-formed TaskNet — forbid
                        self.solver.add(False)
                    else:
                        # parent task must be active during this task's execution
                        # parent_start <= this_start AND this_end <= parent_end
                        add_constraint(self.start_vars[pid] <= s, e <= self.end_vars[pid])

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
                if tj.kind == TaskKind.OPTIONAL:
                    both_included = And(both_included, self.optional_included[tj.id])

                # Only enforce distinctness if both are included
                if ti.kind == TaskKind.OPTIONAL or tj.kind == TaskKind.OPTIONAL:
                    self.solver.add(If(both_included,
                        And(si != sj, ei != ej, si != ej, ei != sj),
                        True))
                else:
                    # Both required - always distinct
                    self.solver.add(si != sj)
                    self.solver.add(ei != ej)
                    self.solver.add(si != ej)
                    self.solver.add(ei != sj)

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
        self.solver.add(z[0] == 0)
        self.solver.add(z[last] == n)

        # Strictly increasing
        for i in range(last):
            self.solver.add(z[i] < z[i + 1])

        # Each start/end must be equal to *some* internal zone
        for t in tasks:
            s = self.start_vars[t.id]
            e = self.end_vars[t.id]
            self.solver.add(Or(*[s == z[j] for j in range(1, last)]))
            self.solver.add(Or(*[e == z[j] for j in range(1, last)]))

        # Each internal zone must be equal to *some* start or end
        for j in range(1, last):
            self.solver.add(
                Or(*[
                    Or(self.start_vars[t.id] == z[j],
                       self.end_vars[t.id] == z[j])
                    for t in tasks
                ])
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
                vars_z = [Bool(f"{tl.id}_z{j}") for j in range(Z)]
                self.atomic_tl_zone[tl.id] = vars_z

            elif isinstance(tl, ClaimableTimeline):
                vars_z = [Real(f"{tl.id}_z{j}") for j in range(Z)]
                self.numeric_tl_zone[tl.id] = (tl.range, None, vars_z)

            elif isinstance(tl, CumulativeTimeline):
                vars_z = [Real(f"{tl.id}_z{j}") for j in range(Z)]
                self.numeric_tl_zone[tl.id] = (tl.range, tl.bounds, vars_z)

            elif isinstance(tl, RateTimeline):
                vars_z = [Real(f"{tl.id}_z{j}") for j in range(Z)]
                self.numeric_tl_zone[tl.id] = (tl.range, tl.bounds, vars_z)

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
                    self.solver.add(vars_z[z0_idx] == tl.initial)

            elif isinstance(tl, ClaimableTimeline):
                _, _, vars_z = self.numeric_tl_zone[tl.id]
                if tl.initial is not None:
                    self.solver.add(vars_z[0] == tl.initial)

            elif isinstance(tl, CumulativeTimeline):
                _, _, vars_z = self.numeric_tl_zone[tl.id]
                if tl.initial is not None:
                    self.solver.add(vars_z[0] == tl.initial)

            elif isinstance(tl, RateTimeline):
                _, _, vars_z = self.numeric_tl_zone[tl.id]
                if tl.initial is not None:
                    self.solver.add(vars_z[0] == tl.initial)

    def _encode_initial_bounds(self):
        for tl in self.tn.timelines:
            if isinstance(tl, (CumulativeTimeline, RateTimeline)) and tl.bounds is not None:
                _, bounds, vars_z = self.numeric_tl_zone[tl.id]
                self.solver.add(vars_z[0] >= bounds.low, vars_z[0] <= bounds.high)

    def _encode_init_predicate(self):
        # init constraints apply at zone 0
        self.solver.add(self._conds_holds_zone(self.tn.initial_constraints, 0))

    # ------------------------------
    # Impact semantics over zones
    # ------------------------------

    def _numeric_delta_zone(self, tl_id: str, zone_i: int):
        """
        Sum of all numeric deltas over zone i for numeric timelines
        (cumulative + rate).
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

                    # Guard with optional_included for optional tasks
                    if t.kind == TaskKind.OPTIONAL:
                        term = If(self.optional_included[t.id], term, 0.0)
                    terms.append(term)

                # RATE: r * dt while task active over the entire zone
                elif isinstance(how, ImpactRate):
                    r = how.r

                    # We assume zi, zi1, dt are already defined above in your function.
                    # Semantics:
                    #   pre   : rate active from start time onward
                    #   maint : rate active only while task is active (start <= t < end)
                    #   post  : rate active from end time onward

                    active_pre   = (zi >= s)                 # t ≥ start
                    active_maint = And(zi >= s, zi < e)      # start ≤ t < end
                    active_post  = (zi >= e)                 # t ≥ end

                    if when == "pre":
                        term = If(active_pre, r * dt, 0.0)
                    elif when == "maint":
                        term = If(active_maint, r * dt, 0.0)
                    elif when == "post":
                        term = If(active_post, r * dt, 0.0)
                    else:
                        continue

                    # Guard with optional_included for optional tasks
                    if t.kind == TaskKind.OPTIONAL:
                        term = If(self.optional_included[t.id], term, 0.0)
                    terms.append(term)
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
                                else:
                                    expr = If(zi == s, idx, expr)
                            elif imp.when == "post":
                                if t.kind == TaskKind.OPTIONAL:
                                    expr = If(And(self.optional_included[t.id], zi == e), idx, expr)
                                else:
                                    expr = If(zi == e, idx, expr)
                            else:
                                # maint+assign disallowed
                                self.solver.add(False)
                    self.solver.add(vars_z[i + 1] == expr)

            elif isinstance(tl, AtomicTimeline):
                vars_z = self.atomic_tl_zone[tl.id]
                for i in range(Z - 1):
                    cur = vars_z[i]
                    expr = cur
                    zi = self.zones[i]
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
                            if not isinstance(v, BoolVal):
                                self.solver.add(False)
                                continue
                            if imp.when == "pre":
                                expr = If(zi == s, v.v, expr)
                            elif imp.when == "post":
                                expr = If(zi == e, v.v, expr)
                            else:
                                self.solver.add(False)
                    self.solver.add(vars_z[i + 1] == expr)

        # Numeric timelines: deltas + clamping by bounds (not by range!)
        for tl in self.tn.timelines:
            if isinstance(tl, (ClaimableTimeline, CumulativeTimeline, RateTimeline)):
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
                                else:
                                    expr = If(zi == s, val, expr)
                            elif imp.when == "post":
                                if t.kind == TaskKind.OPTIONAL:
                                    expr = If(And(self.optional_included[t.id], zi == e), val, expr)
                                else:
                                    expr = If(zi == e, val, expr)
                            else:
                                # maint+assign disallowed for numeric timelines
                                self.solver.add(False)

                    self.solver.add(vars_z[i + 1] == expr)

    def _encode_timeline_ranges(self):
        """
        Enforce TimeLineRangeOk: for numeric timelines, the value at *all*
        zone boundaries lies within the declared RealRange.
        (State timelines are already domain-restricted, atomic are Bool.)
        """
        for tl_id, (range_r, _bounds, vars_z) in self.numeric_tl_zone.items():
            lo, hi = range_r.low, range_r.high
            for v in vars_z:
                self.solver.add(v >= lo, v <= hi)

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
                    self.solver.add(Or(Not(self.optional_included[t.id]), zj != s, pre_formula))

                    # POST at end: either not included, or zone != end, or post holds
                    self.solver.add(Or(Not(self.optional_included[t.id]), zj != e, post_formula))

                    # INV whenever active: either not included, or zone outside [start, end], or inv holds
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
                    self.solver.add(Or(zj != s, pre_formula))

                    # POST at end
                    self.solver.add(Or(zj != e, post_formula))

                    # INV whenever active (inclusive bounds)
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
            # 1. Primary objective: minimize the number of included optional tasks
            if self.optional_tasks:
                objective_optional = Sum([If(self.optional_included[t.id], 1, 0) for t in self.optional_tasks])
                self.solver.minimize(objective_optional)

            # 2. Secondary objective: minimize priority-weighted cost
            # Lower priority values = higher importance = lower cost
            # Cost = sum of (priority * inclusion_factor) for all tasks
            priority_terms = []
            for t in self.all_scheduled_tasks:
                if t.priority is not None:
                    if t.kind == TaskKind.OPTIONAL:
                        # For optional tasks, only count if included
                        priority_terms.append(If(self.optional_included[t.id], t.priority, 0))
                    else:
                        # For required tasks, always count
                        priority_terms.append(t.priority)

            if priority_terms:
                objective_priority = Sum(priority_terms)
                self.solver.minimize(objective_priority)

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
                print(f"\nUNSAT CORE ({len(core)} constraints):")
                for i, constraint in enumerate(core, 1):
                    print(f"  {i}. {constraint}")

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
            # Check if optional task is included
            if t.kind == TaskKind.OPTIONAL:
                included = model[self.optional_included[t.id]]
                if not included:
                    print(f"  {t.id:14s}: [OPTIONAL - NOT INCLUDED]")
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
                # Skip optional tasks that aren't included
                if t.kind == TaskKind.OPTIONAL:
                    included = model[self.optional_included[t.id]]
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
                    print(
                        f"    {tl.id:14s} = "
                        f"{v_start.as_decimal(6)} -> {v_end.as_decimal(6)}"
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
   