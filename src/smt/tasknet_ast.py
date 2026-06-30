# tn_ast.py
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
    low: int
    high: int

@dataclass
class RealRange:
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
    v: int

@dataclass
class RealVal:
    v: float

@dataclass
class StrVal:
    v: str

@dataclass
class BoolVal:
    v: bool

@dataclass
class ParamRef:
    """Reference to a parameter by name."""
    name: str

Value = Union[IntVal, RealVal, StrVal, BoolVal, ParamRef]

# ----- Timelines -----

@dataclass
class StateTimeline:
    id: TimeLineName
    states: List[str]
    initial: Optional[str]

@dataclass
class AtomicTimeline:
    id: TimeLineName
    initial: Optional[int] = 0  # 0 or 1

@dataclass
class ClaimableTimeline:
    id: TimeLineName
    range: RealRange
    initial: Optional[float]

@dataclass
class CumulativeTimeline:
    id: TimeLineName
    range: RealRange
    bounds: RealRange
    initial: Optional[float]

@dataclass
class RateTimeline:
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
    v: Value           

@dataclass
class ImpactCumulative:
    v: float           

@dataclass
class ImpactRateCumulative:
    delta: float  # Amount to add to current rate

@dataclass
class ImpactRateAssignment:
    r: float  # Absolute rate value to set

ImpactHow = Union[ImpactAssign, ImpactCumulative, ImpactRateCumulative, ImpactRateAssignment]

@dataclass
class Impact:
    id: TimeLineName   
    when: ImpactWhen   
    how: ImpactHow

# ----- Conditions -----

@dataclass
class ConVal:
    v: Value

@dataclass
class ConIntRange:
    r: IntRange

@dataclass
class ConRealRange:
    r: RealRange

Con = Union[ConVal, ConIntRange, ConRealRange]

@dataclass
class TlCon:
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

# ----- Temporal-logic formulas -----

class Formula(ABC):
    pass

@dataclass
class TLNumCmp(Formula):
    tl: TimeLineName
    op: Literal["<", "<=", "=", ">=", ">"]
    bound: float

@dataclass
class TLStateIs(Formula):
    tl: TimeLineName
    value: str

@dataclass
class TLBoolIs(Formula):
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
    left: Formula
    right: Formula

@dataclass
class TLOr(Formula):
    left: Formula
    right: Formula

@dataclass
class TLNot(Formula):
    sub: Formula

@dataclass
class TLImplies(Formula):
    left: Formula
    right: Formula

@dataclass
class TLAlways(Formula):
    sub: Formula

@dataclass
class TLEventually(Formula):
    sub: Formula

@dataclass
class TLUntil(Formula):
    left: Formula
    right: Formula

@dataclass
class TLSoFar(Formula):
    sub: Formula

@dataclass
class TLOnce(Formula):
    sub: Formula

@dataclass
class TLSince(Formula):
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

    Desugared to: (A.end <= B.start) or (B.end <= A.start) for all pairs
    """
    group_a: List[TaskName]           # First group of tasks
    group_b: Optional[List[TaskName]] # Second group (None for within-group)

@dataclass
class TemporalProperty:
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
    id: TaskNetName
    params: List[ParamDecl]
    timelines: List[Timeline]
    tasks: List[Task]
    endTime: int
    initial_constraints: List[TlCon] = field(default_factory=list)
    constraints: List[TemporalProperty] = field(default_factory=list)
    properties: List[TemporalProperty] = field(default_factory=list)
