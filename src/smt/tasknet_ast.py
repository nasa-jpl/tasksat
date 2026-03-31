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

Value = Union[IntVal, RealVal, StrVal, BoolVal]

# ----- Timelines -----

@dataclass
class StateTimeline:
    id: TimeLineName
    states: List[str]
    initial: Optional[str]

@dataclass
class AtomicTimeline:
    id: TimeLineName
    initial: Optional[bool] = None

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
    bounds: RealRange
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
    """Type of task: definition (template), instance (required), or optional (minimized)"""
    DEFINITION = "definition"
    INSTANCE = "instance"
    OPTIONAL = "optional"

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
    definition: Optional[TaskName] = None  # Reference to definition task (for instances/optional)
    priority: Optional[int] = None
    startrng: Optional[IntRange] = None
    endrng: Optional[IntRange] = None
    durrng: Optional[IntRange] = None
    dur: Optional[int] = None
    start: Optional[int] = None
    # Instance-level temporal constraints (reference specific task IDs)
    after_instances: Optional[List[str]] = None
    containedin_instances: Optional[List[str]] = None
    # Type-level temporal constraints (reference definition IDs)
    after_definitions: Optional[List[str]] = None
    containedin_definitions: Optional[List[str]] = None
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
class TemporalProperty:
    name: str
    formula: Formula

# ----- TaskNet -----

@dataclass
class TaskNet:
    id: TaskNetName
    timelines: List[Timeline]
    tasks: List[Task]
    endTime: int
    initial_constraints: List[TlCon] = field(default_factory=list)
    constraints: List[TemporalProperty] = field(default_factory=list)
    properties: List[TemporalProperty] = field(default_factory=list)
