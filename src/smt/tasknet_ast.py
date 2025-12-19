# tn_ast.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Union, Literal, Tuple
from abc import ABC

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
class ImpactRate:
    r: float           

ImpactHow = Union[ImpactAssign, ImpactCumulative, ImpactRate]

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

@dataclass
class TaskDef:
    id: TaskName
    ident: TaskId
    priority: int
    startrng: IntRange
    endrng: IntRange
    dur: int
    start: int
    after: List[str]
    containedin: List[str]
    pre: List[TlCon]
    inv: List[TlCon]
    post: List[TlCon]
    impacts: List[Impact]

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
    tasks: List[TaskDef]
    endTime: int
    initial_constraints: List[TlCon] = field(default_factory=list)
    constraints: List[TemporalProperty] = field(default_factory=list)
    properties: List[TemporalProperty] = field(default_factory=list)
