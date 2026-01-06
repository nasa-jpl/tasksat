"""
Well-formedness checker for TaskNet AST.

Validates static properties of a TaskNet before solving.
"""

from __future__ import annotations
from typing import List, Dict, Set, Optional
from dataclasses import dataclass

from tasknet_ast import *


@dataclass
class WellFormednessError:
    """Represents a single well-formedness violation."""
    category: str
    message: str

    def __str__(self) -> str:
        return f"[{self.category}] {self.message}"


class WellFormednessChecker:
    """Validates well-formedness of a TaskNet AST."""

    def __init__(self, tn: TaskNet):
        self.tn = tn
        self.errors: List[WellFormednessError] = []

        # Build lookup maps for efficient checking
        self.timeline_map: Dict[str, Timeline] = {tl.id: tl for tl in tn.timelines}
        self.task_map: Dict[str, Task] = {t.id: t for t in tn.tasks}
        self.definition_map: Dict[str, Task] = {
            t.id: t for t in tn.tasks if t.kind == TaskKind.DEFINITION
        }

    def check(self) -> List[WellFormednessError]:
        """
        Run all well-formedness checks.

        Returns:
            List of WellFormednessError objects. Empty list means well-formed.
        """
        self.errors = []

        # Run all checks
        self._check_timeline_ids_unique()
        self._check_task_ids_unique()
        self._check_task_definitions_exist()
        self._check_task_dependencies_exist()
        self._check_impact_types()
        self._check_condition_types()
        self._check_timeline_references()

        return self.errors

    def _error(self, category: str, message: str):
        """Record a well-formedness error."""
        self.errors.append(WellFormednessError(category, message))

    # ========== Timeline Checks ==========

    def _check_timeline_ids_unique(self):
        """Check that all timeline IDs are unique."""
        seen: Set[str] = set()
        for tl in self.tn.timelines:
            if tl.id in seen:
                self._error("Timeline ID", f"Duplicate timeline ID: '{tl.id}'")
            seen.add(tl.id)

    # ========== Task Checks ==========

    def _check_task_ids_unique(self):
        """Check that all task IDs are unique."""
        seen: Set[str] = set()
        for t in self.tn.tasks:
            if t.id in seen:
                self._error("Task ID", f"Duplicate task ID: '{t.id}'")
            seen.add(t.id)

    def _check_task_definitions_exist(self):
        """Check that referenced task definitions exist."""
        for t in self.tn.tasks:
            if t.definition is not None:
                if t.definition not in self.definition_map:
                    self._error(
                        "Task Definition",
                        f"Task '{t.id}' references undefined definition '{t.definition}'"
                    )

    def _check_task_dependencies_exist(self):
        """Check that task dependencies (after, containedin) reference existing tasks."""
        for t in self.tn.tasks:
            # Skip definitions - they're not scheduled
            if t.kind == TaskKind.DEFINITION:
                continue

            # Check 'after' dependencies
            if t.after is not None:
                for dep_id in t.after:
                    if dep_id not in self.task_map:
                        self._error(
                            "Task Dependency",
                            f"Task '{t.id}' has 'after' dependency on non-existent task '{dep_id}'"
                        )
                    elif self.task_map[dep_id].kind == TaskKind.DEFINITION:
                        self._error(
                            "Task Dependency",
                            f"Task '{t.id}' has 'after' dependency on definition '{dep_id}' "
                            "(definitions are not scheduled)"
                        )

            # Check 'containedin' dependencies
            if t.containedin is not None:
                for parent_id in t.containedin:
                    if parent_id not in self.task_map:
                        self._error(
                            "Task Dependency",
                            f"Task '{t.id}' has 'containedin' dependency on non-existent task '{parent_id}'"
                        )
                    elif self.task_map[parent_id].kind == TaskKind.DEFINITION:
                        self._error(
                            "Task Dependency",
                            f"Task '{t.id}' has 'containedin' dependency on definition '{parent_id}' "
                            "(definitions are not scheduled)"
                        )

    # ========== Impact Type Checks ==========

    def _check_impact_types(self):
        """Check that impacts match their timeline types and timing constraints."""
        for t in self.tn.tasks:
            if t.impacts is None:
                continue

            for imp in t.impacts:
                # Check timeline exists
                if imp.id not in self.timeline_map:
                    self._error(
                        "Impact Reference",
                        f"Task '{t.id}' has impact on non-existent timeline '{imp.id}'"
                    )
                    continue

                tl = self.timeline_map[imp.id]

                # Check impact type matches timeline type
                self._check_impact_timeline_compatibility(t.id, imp, tl)

    def _check_impact_timeline_compatibility(self, task_id: str, imp: Impact, tl: Timeline):
        """Check that an impact is compatible with its timeline type."""

        # StateTimeline: only ImpactAssign with StrVal
        if isinstance(tl, StateTimeline):
            if isinstance(imp.how, ImpactAssign):
                if not isinstance(imp.how.v, StrVal):
                    self._error(
                        "Impact Type",
                        f"Task '{task_id}' assigns non-string value to state timeline '{imp.id}'"
                    )
                elif imp.how.v.v not in tl.states:
                    self._error(
                        "Impact Type",
                        f"Task '{task_id}' assigns invalid state '{imp.how.v.v}' to timeline '{imp.id}'. "
                        f"Valid states: {tl.states}"
                    )
                # Check timing: only pre/post allowed
                if imp.when == "maint":
                    self._error(
                        "Impact Timing",
                        f"Task '{task_id}' has 'maint' assignment on state timeline '{imp.id}'. "
                        "Only 'pre' and 'post' are allowed."
                    )
            elif isinstance(imp.how, (ImpactCumulative, ImpactRate)):
                self._error(
                    "Impact Type",
                    f"Task '{task_id}' has cumulative/rate impact on state timeline '{imp.id}'. "
                    "Only assignments are allowed."
                )

        # AtomicTimeline: only ImpactAssign with BoolVal
        elif isinstance(tl, AtomicTimeline):
            if isinstance(imp.how, ImpactAssign):
                if not isinstance(imp.how.v, BoolVal):
                    self._error(
                        "Impact Type",
                        f"Task '{task_id}' assigns non-boolean value to atomic timeline '{imp.id}'"
                    )
                # Check timing: only pre/post allowed
                if imp.when == "maint":
                    self._error(
                        "Impact Timing",
                        f"Task '{task_id}' has 'maint' assignment on atomic timeline '{imp.id}'. "
                        "Only 'pre' and 'post' are allowed."
                    )
            elif isinstance(imp.how, (ImpactCumulative, ImpactRate)):
                self._error(
                    "Impact Type",
                    f"Task '{task_id}' has cumulative/rate impact on atomic timeline '{imp.id}'. "
                    "Only assignments are allowed."
                )

        # ClaimableTimeline: only ImpactCumulative with 'maint' timing
        elif isinstance(tl, ClaimableTimeline):
            if isinstance(imp.how, ImpactCumulative):
                if imp.when != "maint":
                    self._error(
                        "Impact Timing",
                        f"Task '{task_id}' has '{imp.when}' cumulative impact on claimable timeline '{imp.id}'. "
                        "Only 'maint' is allowed for claimable timelines."
                    )
            elif isinstance(imp.how, ImpactRate):
                self._error(
                    "Impact Type",
                    f"Task '{task_id}' has rate impact on claimable timeline '{imp.id}'. "
                    "Only cumulative 'maint' impacts are allowed."
                )
            elif isinstance(imp.how, ImpactAssign):
                self._error(
                    "Impact Type",
                    f"Task '{task_id}' has assignment on claimable timeline '{imp.id}'. "
                    "Only cumulative 'maint' impacts are allowed."
                )

        # CumulativeTimeline: no rate impacts; assignments allowed (pre/post only)
        elif isinstance(tl, CumulativeTimeline):
            if isinstance(imp.how, ImpactRate):
                self._error(
                    "Impact Type",
                    f"Task '{task_id}' has rate impact on cumulative timeline '{imp.id}'. "
                    "Only cumulative impacts and assignments are allowed."
                )
            elif isinstance(imp.how, ImpactAssign):
                # Verify numeric value
                if not isinstance(imp.how.v, (IntVal, RealVal)):
                    self._error(
                        "Impact Type",
                        f"Task '{task_id}' assigns non-numeric value to cumulative timeline '{imp.id}'"
                    )
                # Check timing: only pre/post allowed for assignments
                if imp.when == "maint":
                    self._error(
                        "Impact Timing",
                        f"Task '{task_id}' has 'maint' assignment on cumulative timeline '{imp.id}'. "
                        "Only 'pre' and 'post' assignments are allowed."
                    )

        # RateTimeline: cumulative and rate impacts allowed; assignments allowed (pre/post only)
        elif isinstance(tl, RateTimeline):
            if isinstance(imp.how, ImpactAssign):
                # Verify numeric value
                if not isinstance(imp.how.v, (IntVal, RealVal)):
                    self._error(
                        "Impact Type",
                        f"Task '{task_id}' assigns non-numeric value to rate timeline '{imp.id}'"
                    )
                # Check timing: only pre/post allowed for assignments
                if imp.when == "maint":
                    self._error(
                        "Impact Timing",
                        f"Task '{task_id}' has 'maint' assignment on rate timeline '{imp.id}'. "
                        "Only 'pre' and 'post' assignments are allowed."
                    )

    # ========== Condition Type Checks ==========

    def _check_condition_types(self):
        """Check that conditions (pre/inv/post) match their timeline types."""
        for t in self.tn.tasks:
            if t.pre:
                for tlcon in t.pre:
                    self._check_tlcon_type(t.id, "pre", tlcon)
            if t.inv:
                for tlcon in t.inv:
                    self._check_tlcon_type(t.id, "inv", tlcon)
            if t.post:
                for tlcon in t.post:
                    self._check_tlcon_type(t.id, "post", tlcon)

        # Check initial constraints
        for tlcon in self.tn.initial_constraints:
            self._check_tlcon_type("initial_constraints", "init", tlcon)

    def _check_tlcon_type(self, context: str, cond_type: str, tlcon: TlCon):
        """Check that a timeline condition matches its timeline type."""
        if tlcon.id not in self.timeline_map:
            self._error(
                "Condition Reference",
                f"{context} {cond_type} condition references non-existent timeline '{tlcon.id}'"
            )
            return

        tl = self.timeline_map[tlcon.id]

        for con in tlcon.cons:
            if isinstance(con, ConVal):
                v = con.v
                # StateTimeline: expect StrVal
                if isinstance(tl, StateTimeline):
                    if not isinstance(v, StrVal):
                        self._error(
                            "Condition Type",
                            f"{context} {cond_type} condition on state timeline '{tlcon.id}' "
                            f"uses non-string value"
                        )
                    elif v.v not in tl.states:
                        self._error(
                            "Condition Type",
                            f"{context} {cond_type} condition references invalid state '{v.v}' "
                            f"on timeline '{tlcon.id}'. Valid states: {tl.states}"
                        )

                # AtomicTimeline: expect BoolVal
                elif isinstance(tl, AtomicTimeline):
                    if not isinstance(v, BoolVal):
                        self._error(
                            "Condition Type",
                            f"{context} {cond_type} condition on atomic timeline '{tlcon.id}' "
                            f"uses non-boolean value"
                        )

                # Numeric timelines: expect IntVal or RealVal
                elif isinstance(tl, (ClaimableTimeline, CumulativeTimeline, RateTimeline)):
                    if not isinstance(v, (IntVal, RealVal)):
                        self._error(
                            "Condition Type",
                            f"{context} {cond_type} condition on numeric timeline '{tlcon.id}' "
                            f"uses non-numeric value"
                        )

            elif isinstance(con, (ConIntRange, ConRealRange)):
                # Range conditions only valid for numeric timelines
                if not isinstance(tl, (ClaimableTimeline, CumulativeTimeline, RateTimeline)):
                    self._error(
                        "Condition Type",
                        f"{context} {cond_type} condition uses range on non-numeric timeline '{tlcon.id}'"
                    )

    # ========== Timeline Reference Checks ==========

    def _check_timeline_references(self):
        """Check that all timeline references in formulas are valid."""
        # Check constraints
        for prop in self.tn.constraints:
            self._check_formula_timeline_refs(prop.name, prop.formula, "constraint")

        # Check properties
        for prop in self.tn.properties:
            self._check_formula_timeline_refs(prop.name, prop.formula, "property")

    def _check_formula_timeline_refs(self, prop_name: str, formula: Formula, kind: str):
        """Recursively check timeline references in a formula."""
        if isinstance(formula, TLNumCmp):
            if formula.tl not in self.timeline_map:
                self._error(
                    "Formula Reference",
                    f"{kind} '{prop_name}' references non-existent timeline '{formula.tl}'"
                )
            else:
                tl = self.timeline_map[formula.tl]
                if not isinstance(tl, (ClaimableTimeline, CumulativeTimeline, RateTimeline)):
                    self._error(
                        "Formula Type",
                        f"{kind} '{prop_name}' uses numeric comparison on non-numeric timeline '{formula.tl}'"
                    )

        elif isinstance(formula, TLStateIs):
            if formula.tl not in self.timeline_map:
                self._error(
                    "Formula Reference",
                    f"{kind} '{prop_name}' references non-existent timeline '{formula.tl}'"
                )
            else:
                tl = self.timeline_map[formula.tl]
                if not isinstance(tl, StateTimeline):
                    self._error(
                        "Formula Type",
                        f"{kind} '{prop_name}' uses state comparison on non-state timeline '{formula.tl}'"
                    )
                elif formula.value not in tl.states:
                    self._error(
                        "Formula Type",
                        f"{kind} '{prop_name}' references invalid state '{formula.value}' "
                        f"on timeline '{formula.tl}'. Valid states: {tl.states}"
                    )

        elif isinstance(formula, TLBoolIs):
            if formula.tl not in self.timeline_map:
                self._error(
                    "Formula Reference",
                    f"{kind} '{prop_name}' references non-existent timeline '{formula.tl}'"
                )
            else:
                tl = self.timeline_map[formula.tl]
                if not isinstance(tl, AtomicTimeline):
                    self._error(
                        "Formula Type",
                        f"{kind} '{prop_name}' uses boolean comparison on non-atomic timeline '{formula.tl}'"
                    )

        # Recursively check compound formulas
        elif isinstance(formula, (TLAnd, TLOr, TLUntil, TLSince)):
            self._check_formula_timeline_refs(prop_name, formula.left, kind)
            self._check_formula_timeline_refs(prop_name, formula.right, kind)

        elif isinstance(formula, (TLNot, TLAlways, TLEventually, TLSoFar, TLOnce)):
            self._check_formula_timeline_refs(prop_name, formula.sub, kind)

        elif isinstance(formula, TLImplies):
            self._check_formula_timeline_refs(prop_name, formula.left, kind)
            self._check_formula_timeline_refs(prop_name, formula.right, kind)


def check_wellformedness(tn: TaskNet) -> bool:
    """
    Check well-formedness of a TaskNet.

    Args:
        tn: The TaskNet to check

    Returns:
        True if well-formed, False if violations found (errors printed to stdout)
    """
    checker = WellFormednessChecker(tn)
    errors = checker.check()

    if errors:
        print("\n" + "="*70)
        print("WELL-FORMEDNESS ERRORS DETECTED")
        print("="*70)
        print(f"\nFound {len(errors)} well-formedness violation(s):\n")

        for i, error in enumerate(errors, 1):
            print(f"{i}. {error}")

        print("\n" + "="*70)
        print("Aborting: fix the errors above and try again.")
        print("="*70 + "\n")
        return False

    return True
