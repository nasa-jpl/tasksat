
namespace TaskNet

-- ===============
-- ABSTRACT SYNTAX
-- ===============

-----------------------
-- Values and ranges --
-----------------------

abbrev TaskNetName  := String
abbrev TaskName     := String
abbrev TaskId       := Nat
abbrev TimeLineName := String
abbrev Ident        := String
abbrev Time         := Nat

inductive Value where
  | intVal  (v : Int)
  | realVal (v : Float)
  | strVal  (v : String)
  | boolVal (v : Bool)
deriving Repr, BEq

structure IntRange where
  low : Int
  high: Int
deriving Repr, BEq

structure RealRange where
  low : Float
  high : Float
deriving Repr, BEq

----------------
--- Timelines --
----------------

inductive Timeline where
  | stateTimeline
      (id : TimeLineName)
      (states : List String)
      (initial : String)
  | atomicTimeline
      (id : TimeLineName)
  | claimableTimeline
      (id : TimeLineName)
      (range : RealRange)
      (initial : Float)
  | cumulativeTimeline
      (id : TimeLineName)
      (range : RealRange)
      (bounds : RealRange)
      (initial : Float)
  | rateTimeline
      (id : TimeLineName)
      (range : RealRange)
      (bounds : RealRange)
      (initial : Float)
deriving Repr, BEq

----------------------------
-- Impacts and conditions --
----------------------------

inductive ImpactWhen where
  | pre | maint | post
deriving Repr, BEq

inductive ImpactHow where
  | assign     (v : Value)
  | cumulative (v : Float)
  | rate       (r : Float)
deriving Repr, BEq

structure Impact where
  id   : TimeLineName
  when : ImpactWhen
  how  : ImpactHow
deriving Repr, BEq

--------------------------
-- Timeline constraints --
--------------------------

inductive Con where
  | val   (v : Value)
  | i_rng (r : IntRange)
  | r_rng (r : RealRange)
deriving Repr, BEq

structure TlCon where
  id   : TimeLineName
  cons : List Con
deriving Repr, BEq

-----------
-- Tasks --
-----------

inductive TaskKind where
  | required | optional | request
deriving Repr, BEq

structure TaskDef where
  id         : TaskName
  ident      : TaskId
  priority   : Nat
  startrng   : IntRange
  endrng     : IntRange
  durrng     : IntRange      -- duration range
  dur        : Nat           -- preferred duration
  start      : Nat
  after      : List Ident    -- instance-level: specific task IDs
  containedin: List Ident    -- instance-level: specific task IDs
  after_definitions      : List String  -- type-level: taskdef names
  containedin_definitions: List String  -- type-level: taskdef names
  kind       : TaskKind      -- required/optional/request
  pre        : List TlCon
  inv        : List TlCon
  post       : List TlCon
  impacts    : List Impact
deriving Repr, BEq

------------------
-- Task Network --
------------------

structure TaskNet where
  id        : TaskNetName
  timelines : List Timeline
  tasks     : List TaskDef       -- Task instances
  taskdefs  : List TaskDef       -- Task definitions (templates)
  endTime   : Nat
deriving Repr, BEq

end TaskNet
