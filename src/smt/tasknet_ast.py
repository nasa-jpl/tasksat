"""TaskNet abstract syntax tree.

The dataclasses in this module are the shared vocabulary of the whole pipeline:
the parser builds them, the transforms rewrite them, the well-formedness checker
validates them, the SMT encoder consumes them and the printer turns them back
into `.tn` syntax.

The main groups are:

- **Network**: `TaskNet`, the root, holding parameters, timelines, tasks,
  constraints, properties and the `initial` / `final` / `invariant` blocks.
- **Tasks**: `Task` (a definition, an instance, optional or requested, per
  `TaskKind`), `TaskRange` for the `T[min..max]` sugar, and the dependency
  nodes `AfterDependency` / `ContainedinDependency`.
- **Timelines**: `Timeline` and its impacts — the state a task reads and writes.
- **Formulas**: the `Formula` hierarchy for constraints and temporal (LTL-style)
  properties, including the sugar nodes `TLMutex` and `TLSequence` that the
  transforms desugar away.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Union, Literal, Tuple
from abc import ABC
from enum import Enum

TaskNetName  = str
TaskName     = str
TaskId       = int
TimeLineName = str
Time         = int

@dataclass
class IntRange:
    """An inclusive integer interval `[low, high]`, as written `[10, 20]`.

    Used for the time-valued ranges: durations, start/end windows, `after` gaps
    and `containedin` offsets.
    """
    low: int
    high: int

@dataclass
class RealRange:
    """An inclusive real interval `[low, high]`, as written `[0.0, 100.0]`.

    Used for the numeric timeline ranges and bounds, and for real-valued
    conditions.
    """
    low: float
    high: float

# ----- Temporal Dependencies -----

@dataclass
class AfterDependency:
    """After dependency with optional time gap.

    Semantics:
    - gap=None: B.start >= A.end (immediate succession allowed)
    - gap=[min, max]: B.start ∈ [A.end + min, A.end + max]
    """
    task_id: str  # Task or taskdef name
    gap: Optional[IntRange] = None  # Optional [min, max] gap after predecessor ends

@dataclass
class ContainedinDependency:
    """Containedin dependency with optional start/end offsets.

    Semantics:

    - No offsets: parent.start <= child.start AND child.end <= parent.end
    - With offsets:

      - start_offset=[min, max]: child.start ∈ [parent.start + min, parent.start + max]
      - end_offset=[min, max]: child.end ∈ [parent.end - max, parent.end - min]
    """
    task_id: str  # Task or taskdef name
    start_offset: Optional[IntRange] = None  # Optional [min, max] offset from parent start
    end_offset: Optional[IntRange] = None  # Optional [min, max] offset from parent end

# ----- Values -----

@dataclass
class IntVal:
    """An integer literal."""
    v: int

@dataclass
class RealVal:
    """A floating-point literal."""
    v: float

@dataclass
class StrVal:
    """A name literal: a state of a state timeline, e.g. `idle`.

    Also the fallback for a `ParamRef` that resolved to nothing: unresolved
    parameter references are turned into `StrVal` by `resolve_parameters()`,
    on the assumption that the name denotes a timeline state.
    """
    v: str

@dataclass
class BoolVal:
    """A boolean literal, i.e. a state of a `bool` (two-state) timeline."""
    v: bool

@dataclass
class ParamRef:
    """Reference to a parameter by name."""
    name: str

Value = Union[IntVal, RealVal, StrVal, BoolVal, ParamRef]

# ----- Timelines -----

@dataclass
class StateTimeline:
    """A discrete timeline ranging over a finite set of named states.

    Written `mode : state(idle, driving)`. The `bool` timeline type is sugar
    for `state(true, false)`. Only assignment impacts (`=`), in pre or post.
    """
    id: TimeLineName
    states: List[str]
    initial: Optional[str]

@dataclass
class AtomicTimeline:
    """An integer `[0, 1]` timeline enforcing mutual exclusion.

    Written `res : atomic = 0` (0 = unclaimed, 1 = claimed). Only cumulative
    impacts are allowed — `+= 1` to claim, `-= 1` to release, typically as a
    `maint` impact so the claim is released automatically. Assignment is
    rejected: it cannot detect a conflict, whereas two overlapping `+= 1`
    claims push the value to 2 and violate the `[0, 1]` range.

    The `__T_active` timelines synthesized for `active(T)` are of this type.
    """
    id: TimeLineName
    initial: Optional[int] = 0  # 0 or 1

@dataclass
class ClaimableTimeline:
    """A numeric timeline for resources claimed for the duration of a task.

    Written `res : claim [0.0, 4.0] = 4.0`. Accepts delta impacts (`+=`, `-=`)
    in `maint` only, so a claim is always matched by its release. `range` is
    the interval the schedule must stay within.
    """
    id: TimeLineName
    range: RealRange
    initial: Optional[float]

@dataclass
class CumulativeTimeline:
    """A numeric timeline accumulating deltas, e.g. data volume or fuel.

    Written `data : cumulative [0.0, 100.0] bounds [0.0, 100.0] = 0.0`.
    Accepts assignment (pre/post) and delta impacts (pre/maint/post).

    The two intervals differ: `range` is the interval a valid schedule must
    stay within, while `bounds` is the timeline's type — computed values are
    clamped into it. `range` is effectively a subtype of `bounds`.
    """
    id: TimeLineName
    range: RealRange
    bounds: RealRange
    initial: Optional[float]

@dataclass
class RateTimeline:
    """A numeric timeline that also evolves on its own, at a rate.

    Written `battery : rate [0.0, 100.0] bounds [0.0, 100.0] = 50.0
    initial_rate = -0.5`. The value is the integral of the rate over time,
    so it changes even while no task acts on it.

    This is the only timeline carrying two pieces of state, and impacts can
    target either: value impacts (`=`, `+=`, `-=`) and rate impacts (`=~`,
    `+~`, `-~`). `range`/`bounds` are as for `CumulativeTimeline`; `bounds`
    may be omitted.
    """
    id: TimeLineName
    range: RealRange
    bounds: Optional[RealRange]  # Optional: bounds can be omitted
    initial: Optional[float]
    initial_rate: Optional[float] = None

Timeline = Union[
    StateTimeline,
    AtomicTimeline,
    ClaimableTimeline,
    CumulativeTimeline,
    RateTimeline,
]

# ----- Impacts -----

ImpactWhen = Literal["pre", "maint", "post"]

@dataclass
class ImpactAssign:
    """Assignment impact, `timeline = value`: set the value outright."""
    v: Value

@dataclass
class ImpactCumulative:
    """Delta impact, `timeline += v` / `-= v`: add to the current value.

    As a `maint` impact it is self-restoring: applied at the task's start and
    undone at its end.
    """
    v: float

@dataclass
class ImpactRateCumulative:
    """Rate delta impact, `timeline +~ d` / `-~ d`: add to the current rate.

    Rate timelines only. Self-restoring under `maint`, and unlike a value
    impact it is written to zone s rather than s+1, so it governs the whole
    execution interval of the task.
    """
    delta: float  # Amount to add to current rate

@dataclass
class ImpactRateAssignment:
    """Rate assignment impact, `timeline =~ r`: set the rate outright.

    Rate timelines only, and not allowed under `maint` (there is nothing to
    restore the previous rate to).
    """
    r: float  # Absolute rate value to set

ImpactHow = Union[ImpactAssign, ImpactCumulative, ImpactRateCumulative, ImpactRateAssignment]

@dataclass
class Impact:
    """One effect a task has on one timeline: what, when, and how.

    `when` places it at the task's start (`pre`), across its execution
    (`maint`, applied at the start and undone at the end), or at its end
    (`post`). Which `how` a timeline accepts, and at which `when`, is
    validated by `tasknet_wellformedness`.
    """
    id: TimeLineName
    when: ImpactWhen
    how: ImpactHow

# ----- Conditions -----

@dataclass
class ConVal:
    """Condition on an exact value: `timeline = idle`, `battery = 50.0`."""
    v: Value

@dataclass
class ConIntRange:
    """Condition on an integer interval: `timeline in [10, 20]`."""
    r: IntRange

@dataclass
class ConRealRange:
    """Condition on a real interval: `battery in [20.0, 100.0]`."""
    r: RealRange

Con = Union[ConVal, ConIntRange, ConRealRange]

@dataclass
class TlCon:
    """A constraint on one timeline: a name plus the alternatives it may take.

    The `cons` list is a disjunction — `mode in idle, [5, 10]` holds if the
    timeline is `idle` OR within `[5, 10]`.

    This is the shared body of the `initial`, `final` and `invariant` blocks
    and of a task's `pre` / `inv` / `post` conditions.
    """
    id: TimeLineName
    cons: List[Con]

# ----- Tasks -----

class TaskKind(Enum):
    """Type of task: definition, instance (required), optional (minimized), or request (maximized)"""
    DEFINITION = "definition"
    INSTANCE = "instance"
    OPTIONAL = "optional"
    REQUEST = "request"

@dataclass
class Task:
    """Unified task representation supporting definitions, instances, and optional tasks.

    - kind=DEFINITION: Template task, not scheduled, can be referenced by instances
    - kind=INSTANCE: Required task that must be scheduled
    - kind=OPTIONAL: Task included only if needed, minimized by optimizer
    """
    id: TaskName
    ident: TaskId
    kind: TaskKind
    params: List[ParamDecl] = field(default_factory=list)  # Parameter declarations
    definition: Optional[TaskName] = None  # Reference to definition task (for instances/optional)
    priority: Optional[int] = None
    startrng: Optional[IntRange] = None
    endrng: Optional[IntRange] = None
    durrng: Optional[IntRange] = None
    dur: Optional[int] = None
    start: Optional[int] = None
    # Instance-level temporal constraints (reference specific task IDs)
    after_instances: Optional[List[AfterDependency]] = None
    containedin_instances: Optional[List[ContainedinDependency]] = None
    # Type-level temporal constraints (reference definition IDs)
    after_definitions: Optional[List[AfterDependency]] = None
    containedin_definitions: Optional[List[ContainedinDependency]] = None
    pre: Optional[List[TlCon]] = None
    inv: Optional[List[TlCon]] = None
    post: Optional[List[TlCon]] = None
    impacts: Optional[List[Impact]] = None
    # Nested subtasks (session sugar): declared inside a taskdef body.
    # Flattened into ordinary qualified instances by flatten_sessions() in
    # tasknet_transforms.py; empty for ordinary tasks.
    children: List["Task"] = field(default_factory=list)

@dataclass
class TaskRange:
    """Task instance range - expands to multiple Task instances in transform pass.

    Example: task T[2..4] : def { } creates:
        - T_0, T_1 (required, kind=INSTANCE)
        - T_2, T_3 (optional, kind=OPTIONAL or REQUEST depending on is_request)
    """
    id: TaskName                      # Base name (e.g., "science")
    min_instances: int                # Required instances
    max_instances: int                # Total instances (required + optional/request)
    definition: TaskName              # Task definition name
    is_request: bool                  # True if request task, False for regular task
    params: List[ParamDecl] = field(default_factory=list)  # Parameter declarations
    ident: Optional[TaskId] = None    # Base ID for auto-increment
    priority: Optional[int] = None
    startrng: Optional[IntRange] = None
    endrng: Optional[IntRange] = None
    durrng: Optional[IntRange] = None
    dur: Optional[int] = None
    start: Optional[int] = None
    after_instances: Optional[List[AfterDependency]] = None
    containedin_instances: Optional[List[ContainedinDependency]] = None
    after_definitions: Optional[List[AfterDependency]] = None
    containedin_definitions: Optional[List[ContainedinDependency]] = None
    pre: Optional[List[TlCon]] = None
    inv: Optional[List[TlCon]] = None
    post: Optional[List[TlCon]] = None
    impacts: Optional[List[Impact]] = None
    # Nested subtasks (session sugar), same as Task.children.
    children: List["Task"] = field(default_factory=list)

# ----- Temporal-logic formulas -----

class Formula(ABC):
    """Base class of the constraint / temporal-property expression language.

    Subclasses fall into four groups: atoms over timeline state (`TLNumCmp`,
    `TLStateIs`, `TLBoolIs`, `TLTaskActive`, `TLTrue`, `TLFalse`), atoms over
    time (`TLTimeCmp` and its terms), the propositional and temporal operators
    (`TLAnd` ... `TLSince`), and the sugar nodes `TLMutex` / `TLSequence` that
    the transforms rewrite away.

    A formula is evaluated at a zone; the temporal operators quantify over the
    zone sequence, forward (`TLAlways`, `TLEventually`, `TLUntil`) or backward
    (`TLSoFar`, `TLOnce`, `TLSince`).
    """
    pass

@dataclass
class TLNumCmp(Formula):
    """Numeric comparison on a timeline value: `battery >= 20.0`."""
    tl: TimeLineName
    op: Literal["<", "<=", "=", ">=", ">"]
    bound: float

@dataclass
class TLStateIs(Formula):
    """Test that a state timeline holds a given state: `mode = idle`."""
    tl: TimeLineName
    value: str

@dataclass
class TLBoolIs(Formula):
    """Test that a bool timeline holds a given value: `ready = true`."""
    tl: TimeLineName
    value: bool

@dataclass
class TLTaskActive(Formula):
    """Syntactic sugar for task activity: active(T) desugars to __T_active = true"""
    task: TaskName

@dataclass
class TLTrue(Formula):
    """Temporal logic constant: true"""
    pass

@dataclass
class TLFalse(Formula):
    """Temporal logic constant: false"""
    pass

@dataclass
class TLTimeVar(Formula):
    """Reference to current time in temporal formulas"""
    pass

@dataclass
class TLTaskBoundary(Formula):
    """Reference to task start or end time: task.start or task.end"""
    task: TaskName
    boundary: Literal["start", "end"]

# Temporal term types for arithmetic comparisons
TemporalTerm = Union['TLTimeVar', 'TLTaskBoundary', float]

@dataclass
class TLTimeCmp(Formula):
    """Comparison between temporal terms: time, task.start, task.end, or numbers"""
    left: TemporalTerm
    op: Literal["<", "<=", "=", ">=", ">"]
    right: TemporalTerm

@dataclass
class TLAnd(Formula):
    """Conjunction: `left and right`."""
    left: Formula
    right: Formula

@dataclass
class TLOr(Formula):
    """Disjunction: `left or right`."""
    left: Formula
    right: Formula

@dataclass
class TLNot(Formula):
    """Negation: `not sub`."""
    sub: Formula

@dataclass
class TLImplies(Formula):
    """Implication: `left -> right`."""
    left: Formula
    right: Formula

@dataclass
class TLAlways(Formula):
    """`always sub` — sub holds at this zone and every later one."""
    sub: Formula

@dataclass
class TLEventually(Formula):
    """`eventually sub` — sub holds at this zone or some later one."""
    sub: Formula

@dataclass
class TLUntil(Formula):
    """`left until right` — right holds eventually, and left holds up to then.

    The strong reading: `right` must actually occur.
    """
    left: Formula
    right: Formula

@dataclass
class TLSoFar(Formula):
    """`sofar sub` — the past mirror of `always`: sub has held up to here."""
    sub: Formula

@dataclass
class TLOnce(Formula):
    """`once sub` — the past mirror of `eventually`: sub has held at some point."""
    sub: Formula

@dataclass
class TLSince(Formula):
    """`left since right` — the past mirror of `until`.

    `right` held at some earlier zone, and `left` has held ever since.
    """
    left: Formula
    right: Formula

@dataclass
class TLSequence(Formula):
    """Sequence constraint: tasks must execute in the given order.
    Desugared to: task[0].end <= task[1].start and task[1].end <= task[2].start ..."""
    tasks: List[TaskName]

@dataclass
class TLMutex(Formula):
    """Mutual exclusion constraint: tasks cannot overlap.

    - mutex [T1, T2, T3]: within-group (all pairs mutually exclusive)
    - mutex [T1, T2] with [T3, T4]: between-group (cross-product)

    Operands may be task instances or taskdefs. A taskdef operand expands to all
    of its instances (manual + auto-instantiated) during desugaring.

    Within-group semantics for taskdef operands (group_b is None):

    - cross_only=False (default, `mutex [A, B]`): flatten all operands to instances
      and exclude every pair, INCLUDING same-taskdef pairs.
    - cross_only=True (`mutex cross [A, B]`): exclude only pairs from DIFFERENT
      operands; instances of the same taskdef may overlap.

    Desugared to: (A.end <= B.start) or (B.end <= A.start) for each excluded pair
    """
    group_a: List[TaskName]           # First group of tasks
    group_b: Optional[List[TaskName]] # Second group (None for within-group)
    cross_only: bool = False          # Within-group: exclude cross-operand pairs only

@dataclass
class TemporalProperty:
    """A named formula, from either the `constraints` or `properties` block.

    The name is what identifies the entry in the verification report; the
    parser auto-names unnamed entries (`mutex_A_B`, `constraint_3`, ...).

    The same node serves both blocks, and the distinction is in how they are
    used, not in their shape: a `constraints` entry is asserted (it restricts
    which schedules are valid), a `properties` entry is checked (it must hold
    for every valid schedule).
    """
    name: str
    formula: Formula

# ----- Parameters -----

@dataclass
class ParamDecl:
    """Parameter declaration: NAME = value or NAME = range"""
    name: str
    value: Union[Value, 'IntRange', 'RealRange']  # Can be literal value OR range

# ----- TaskNet -----

@dataclass
class TaskNet:
    """The root node: one complete tasknet specification.

    Holds everything a `.tn` file declares — parameters, timelines, tasks, the
    scheduling horizon `endTime`, and the constraint/property blocks — and is
    the value passed between every stage of the pipeline. The transforms in
    `tasknet_transforms` rewrite it in place of the sugar it was parsed with,
    so a post-transform `TaskNet` contains only core constructs.

    On the boundary blocks: `initial_constraints` are asserted at time 0 and
    restrict which schedules are valid, whereas `final_constraints` are
    *checked* against the terminal state of every valid schedule (see
    `effective_final_constraints`). `invariant_constraints` is the raw
    `invariant { P }` block, kept for provenance and desugared into the other
    two.
    """
    id: TaskNetName
    params: List[ParamDecl]
    timelines: List[Timeline]
    tasks: List[Task]
    endTime: int
    initial_constraints: List[TlCon] = field(default_factory=list)
    constraints: List[TemporalProperty] = field(default_factory=list)
    properties: List[TemporalProperty] = field(default_factory=list)
    # Final block: checked as a property (for all schedules, the terminal state
    # after the last scheduled task must satisfy these). None = no final block.
    final_constraints: Optional[List[TlCon]] = None
    final_extends_initial: bool = False
    # Invariant block (compositional sugar): a predicate P on shared state that a
    # session is claimed to preserve ({P}S{P}). Kept raw here so --transform-only
    # shows provenance; desugar_invariant() folds it into initial_constraints +
    # `final within initial` (so effective_final_constraints() == P). None = no block.
    invariant_constraints: Optional[List[TlCon]] = None
    # Opt-in to the compositional inductive-invariant check (set by `invariant
    # compositional { ... }` surface syntax, or by the --compositional CLI flag).
    compositional: bool = False

    def effective_final_constraints(self) -> List[TlCon]:
        """The full list of final constraints to check, resolving the
        `extends initial` sugar (initial's constraints plus the block's own)."""
        if self.final_constraints is None:
            return []
        if self.final_extends_initial:
            return list(self.initial_constraints) + list(self.final_constraints)
        return list(self.final_constraints)
