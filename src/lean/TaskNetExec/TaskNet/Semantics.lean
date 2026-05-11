
import Std
import TaskNet.Syntax

open Std

namespace TaskNet

-- =========
-- SEMANTICS
-- =========

-----------------------
-- Library functions --
-----------------------

def dom {α β} [BEq α] [Hashable α] (m : Std.HashMap α β) : Std.HashSet α :=
  m.fold (init := ∅) (fun s k _ => s.insert k)

abbrev Set (α : Type) := α → Bool

def hashSetEq [BEq α] [Hashable α] (s₁ s₂ : HashSet α) : Bool :=
  s₁.toList.all (fun x => s₂.contains x) &&
  s₂.toList.all (fun x => s₁.contains x)

----------------------------
-- Semantic base domains --
----------------------------

abbrev Interval := Float × Float
abbrev TimeInterval := Time × Time
abbrev Schedule    := Std.HashMap TaskName TimeInterval
abbrev State       := Std.HashMap TimeLineName Value
abbrev Trace       := List State
abbrev SparseTrace := List (Time × State)
abbrev IntervalMap := Std.HashMap TimeLineName Interval
abbrev Change      := Option Value × Option Float
abbrev ChangeMap   := Std.HashMap TimeLineName Change

structure Violation where
  time     : Time
  task     : String
  kind     : String  -- "pre", "inv", "post", "range", "timing"
  timeline : String
  message  : String
deriving Repr

abbrev ValidationResult := Bool × List Violation

-------------------------
-- Auxiliary Functions --
-------------------------

def mergeChanges (c1 c2 : Change) : Change :=
  let (as1, d1) := c1
  let (as2, d2) := c2
  let asgn  := as2 <|> as1
  let delta := some ((d1.getD 0) + (d2.getD 0))
  (asgn, delta)

def inIntRange (r : IntRange) (t : Nat) : Bool :=
  let ti := Int.ofNat t
  r.low ≤ ti ∧ ti ≤ r.high

def valueToReal? : Value → Option Float
  | .intVal i  => some (Float.ofInt i)
  | .realVal r => some r
  | .strVal _  => none
  | .boolVal _ => none

def addValues (v : Value) (δ : Float) : Option Value :=
  match v with
  | .intVal i  => some (.realVal (Float.ofInt i + δ))
  | .realVal r => some (.realVal (r + δ))
  | .strVal _  => none
  | .boolVal b =>
      -- For atomic timelines: treat false as 0, true as 1, then add delta
      -- Result is non-zero (> 0.5) means true, otherwise false
      let val := if b then 1.0 else 0.0
      let result := val + δ
      some (.boolVal (result > 0.5))

def clamp (x low high : Float) : Float :=
  if x < low then low else if x > high then high else x

-------------------------
--- Semantic Equations --
-------------------------

-- Names and ids

def ImpactId (imp : Impact) : TimeLineName :=
  imp.id

def TaskNameOf (tsk : TaskDef) : TaskName :=
  tsk.id

def TaskNamesOf (tsks : List TaskDef) : HashSet TaskName :=
  tsks.foldl (fun acc t => acc.insert (TaskNameOf t)) (HashSet.emptyWithCapacity)

-- ObligationsHold

def ConHolds (c : Con) (v : Value) : Bool :=
  match c with
  | Con.val v'      => v == v'
  | Con.i_rng r     =>
      match v with
      | .intVal i   => r.low ≤ i ∧ i ≤ r.high
      | _           => False
  | Con.r_rng r     =>
      match valueToReal? v with
      | some x      => r.low ≤ x ∧ x ≤ r.high
      | none        => False

def Cons (cons : List Con) (v : Value) : Bool :=
  match cons with
  | []       => False
  | c :: cs  => ConHolds c v ∨ Cons cs v

def TimeLineCondition (cond : TlCon) (state : State) : Bool :=
  match state.get? cond.id with
  | some v => Cons cond.cons v
  | none   => False   -- no value for this timeline ⇒ condition fails

def TimeLineConditions (conds : List TlCon) (state : State) : Bool :=
  match conds with
  | []        => True
  | c :: cs   => TimeLineCondition c state ∧ TimeLineConditions cs state

def TimeLineRangeOk (tl : Timeline) (state : State) : Bool :=
  match tl with
  | .stateTimeline _ _ _ => True
  | .atomicTimeline _    => True

  | .claimableTimeline id range _ =>
      match state.get? id with
      | some v =>
          match valueToReal? v with
          | some r => range.low ≤ r ∧ r ≤ range.high
          | none   => False
      | none => False

  | .cumulativeTimeline id range _ _ =>
      match state.get? id with
      | some v =>
          match valueToReal? v with
          | some r => range.low ≤ r ∧ r ≤ range.high
          | none   => False
      | none => False

  | .rateTimeline id range _ _ =>
      match state.get? id with
      | some v =>
          match valueToReal? v with
          | some r => range.low ≤ r ∧ r ≤ range.high
          | none   => False
      | none => False

def TimeLineRangesOk (tls : List Timeline) (state : State) : Bool :=
  match tls with
  | []       => True
  | tl :: ts => TimeLineRangeOk tl state ∧ TimeLineRangesOk ts state

def PreInvPostAt (tsk : TaskDef) (sch : Schedule)
  (prev cur next : State) (k : Time) : Bool :=
  match sch.get? tsk.id with
  | none => false
  | some (st, en) =>
      let preOk  := if k = st then TimeLineConditions tsk.pre prev else true
      -- At k=en, check INV against prev (before MAINT reverse); at other times use cur
      let invOk  := if st < k ∧ k ≤ en then
                      let state := if k = en then prev else cur
                      TimeLineConditions tsk.inv state
                    else true
      let postOk := if k = en then TimeLineConditions tsk.post cur else true
      preOk && invOk && postOk

def ObligationsHold (tn : TaskNet) (sch : Schedule) (σ : Trace) : Bool :=
  let len := σ.length
  let rec loop (k : Nat) : Bool :=
    if k < len then
      let prev := if k > 0 then σ[k-1]! else σ[k]!
      let cur  := σ[k]!
      let next := if k + 1 < len then σ[k+1]! else cur
      let ok1  := TimeLineRangesOk tn.timelines cur
      let ok2  :=
        match tn.tasks with
        | []       => true
        | _        => tn.tasks.all (fun t => PreInvPostAt t sch prev cur next k)
      if ok1 && ok2 then loop (k+1) else false
    else true
  loop 0

/-- Sparse version of ObligationsHold - only checks at boundary times. -/
def ObligationsHoldSparse (tn : TaskNet) (sch : Schedule) (σs : SparseTrace) : Bool :=
  let rec loop (trace : SparseTrace) (prev : State) : Bool :=
    match trace with
    | [] => true
    | (k, cur) :: rest =>
        let next := match rest with
                    | [] => cur
                    | (_, s) :: _ => s
        let ok1 := TimeLineRangesOk tn.timelines cur
        let ok2 :=
          match tn.tasks with
          | [] => true
          | _  => tn.tasks.all (fun t => PreInvPostAt t sch prev cur next k)
        if ok1 && ok2 then loop rest cur else false
  match σs with
  | [] => true
  | (_, σ0) :: rest => loop rest σ0

-- Violation collection versions

def checkTimeLineCondition (cond : TlCon) (state : State) (taskId : String) (k : Time) (kind : String) : List Violation :=
  match state.get? cond.id with
  | some v =>
      if Cons cond.cons v then []
      else [{
        time := k,
        task := taskId,
        kind := kind,
        timeline := cond.id,
        message := s!"{kind} condition failed for timeline {cond.id}"
      }]
  | none => [{
      time := k,
      task := taskId,
      kind := kind,
      timeline := cond.id,
      message := s!"Timeline {cond.id} not found in state"
    }]

def checkTimeLineConditions (conds : List TlCon) (state : State) (taskId : String) (k : Time) (kind : String) : List Violation :=
  conds.flatMap (fun cond => checkTimeLineCondition cond state taskId k kind)

def checkPreInvPostAt (tsk : TaskDef) (sch : Schedule) (prev cur next : State) (k : Time) : List Violation :=
  match sch.get? tsk.id with
  | none => []
  | some (st, en) =>
      let preViolations  := if k = st then checkTimeLineConditions tsk.pre prev tsk.id k "pre" else []
      -- At k=en, check INV against prev (before MAINT reverse); at other times use cur
      let invViolations  := if st < k ∧ k ≤ en then
                              let state := if k = en then prev else cur
                              checkTimeLineConditions tsk.inv state tsk.id k "inv"
                            else []
      let postViolations := if k = en then checkTimeLineConditions tsk.post cur tsk.id k "post" else []
      preViolations ++ invViolations ++ postViolations

def checkTimeLineRangeOk (tl : Timeline) (state : State) (k : Time) : List Violation :=
  match tl with
  | .stateTimeline _ _ _ => []
  | .atomicTimeline _    => []
  | .claimableTimeline id range _ =>
      match state.get? id with
      | some v =>
          match valueToReal? v with
          | some r =>
              if range.low ≤ r ∧ r ≤ range.high then []
              else [{
                time := k,
                task := "",
                kind := "range",
                timeline := id,
                message := s!"Timeline {id} value {r} outside range [{range.low}, {range.high}]"
              }]
          | none => []
      | none => []
  | .cumulativeTimeline id range _ _ =>
      match state.get? id with
      | some v =>
          match valueToReal? v with
          | some r =>
              if range.low ≤ r ∧ r ≤ range.high then []
              else [{
                time := k,
                task := "",
                kind := "range",
                timeline := id,
                message := s!"Timeline {id} value {r} outside range [{range.low}, {range.high}]"
              }]
          | none => []
      | none => []
  | .rateTimeline id range _ _ =>
      match state.get? id with
      | some v =>
          match valueToReal? v with
          | some r =>
              if range.low ≤ r ∧ r ≤ range.high then []
              else [{
                time := k,
                task := "",
                kind := "range",
                timeline := id,
                message := s!"Timeline {id} value {r} outside range [{range.low}, {range.high}]"
              }]
          | none => []
      | none => []

def checkTimeLineRangesOk (tls : List Timeline) (state : State) (k : Time) : List Violation :=
  tls.flatMap (fun tl => checkTimeLineRangeOk tl state k)

def collectObligationViolations (tn : TaskNet) (sch : Schedule) (σs : SparseTrace) : List Violation :=
  let rec loop (trace : SparseTrace) (prev : State) (acc : List Violation) : List Violation :=
    match trace with
    | [] => acc
    | (k, cur) :: rest =>
        let next := match rest with
                    | [] => cur
                    | (_, s) :: _ => s
        let rangeViolations := checkTimeLineRangesOk tn.timelines cur k
        let taskViolations := tn.tasks.flatMap (fun t => checkPreInvPostAt t sch prev cur next k)
        loop rest cur (acc ++ rangeViolations ++ taskViolations)
  match σs with
  | [] => []
  | (_, σ0) :: rest => loop rest σ0 []

-- Impacts

def Bound (tl : Timeline) : IntervalMap :=
  match tl with
  | .stateTimeline _ _ _        => ({} : IntervalMap)
  | .atomicTimeline _           => ({} : IntervalMap)
  | .claimableTimeline _ _ _ => ({} : IntervalMap)
  | .cumulativeTimeline id _ bounds _ =>
      ({} : IntervalMap).insert id (bounds.low, bounds.high)
  | .rateTimeline id _ bounds _ =>
      ({} : IntervalMap).insert id (bounds.low, bounds.high)

def Bounds (tls : List Timeline) : IntervalMap :=
  match tls with
  | []        => ({} : IntervalMap)
  | tl :: ts  =>
      let rest := Bounds ts
      let b    := Bound tl
      b.fold (init := rest) (fun acc id iv => acc.insert id iv)

def ImpactChange (imp : Impact) (i : TimeInterval) (k : Time) : Change :=
  let (st, en) := i
  match imp.when, imp.how with
  -- assign
  | .pre,   .assign v => if k = st then (some v, none) else (none, none)
  | .maint, .assign _ => (none, none)   -- not well-formed per spec; handled by a WF check
  | .post,  .assign v => if k = en then (some v, none) else (none, none)
  -- cumulative
  | .pre,   .cumulative v => if k = st then (none, some v) else (none, none)
  | .maint, .cumulative v =>
      if k = st then (none, some v)
      else if k = en then (none, some (-v))
      else (none, none)
  | .post,  .cumulative v => if k = en then (none, some v) else (none, none)
  -- rate
  | .pre,   .rate r => if st ≤ k then (none, some r) else (none, none)
  | .maint, .rate r =>
      if st ≤ k then
        if k ≤ en then (none, some r) else (none, none)
      else (none, none)
  | .post,  .rate r => if en ≤ k then (none, some r) else (none, none)

def ComputeChangesByTaskImpacts (imps : List Impact) (i : TimeInterval) (k : Time) : ChangeMap :=
  match imps with
  | [] => (Std.HashMap.emptyWithCapacity : ChangeMap)
  | imp :: is =>
      let id     := ImpactId imp
      let change := ImpactChange imp i k
      let tail   := ComputeChangesByTaskImpacts is i k
      -- small fix: skip no-ops and merge when key already present
      match change with
      | (none, none) => tail
      | _ => tail.insert id change

def ComputeChangesByTask (tsk : TaskDef) (sch : Schedule) (k : Time) : ChangeMap :=
  match sch.get? tsk.id with
  | some (st, en) => ComputeChangesByTaskImpacts tsk.impacts (st, en) k
  | none          => (Std.HashMap.emptyWithCapacity : ChangeMap)

def ComputeChanges (tsks : List TaskDef) (sch : Schedule) (k : Time) : ChangeMap :=
  match tsks with
  | []       => (Std.HashMap.emptyWithCapacity : ChangeMap)
  | t :: ts  =>
    let m1 := ComputeChangesByTask t sch k
    let m2 := ComputeChanges ts sch k
    m1.fold (init := m2) (fun acc id c1 =>
      match acc.get? id with
      | some c2 => acc.insert id (mergeChanges c1 c2)
      | none    => acc.insert id c1)

-- StartEndTimesOk

def AssignmentsByTaskImpact (imp : Impact) (i : TimeInterval): List (TimeLineName × Time) :=
  let (st, en) := i
  match imp.when, imp.how with
  | .pre,  .assign _ => [(imp.id, st)]
  | .post, .assign _ => [(imp.id, en)]
  | .maint, .assign _ => []          -- “error” in spec; here: no assignment
  | _,     .cumulative _ => []
  | _,     .rate _       => []

def AssignmentsByTaskImpacts (imps : List Impact) (i : TimeInterval): List (TimeLineName × Time) :=
  match imps with
  | []        => []
  | imp :: is => AssignmentsByTaskImpact imp i ++ AssignmentsByTaskImpacts is i

def AssignmentsByTask (tsk : TaskDef) (sch : Schedule) : List (TimeLineName × Time) :=
  match sch.get? tsk.id with
  | some (st, en) => AssignmentsByTaskImpacts tsk.impacts (st, en)
  | none => []


def Assignments (tsks : List TaskDef) (sch : Schedule) : List (TimeLineName × Time) :=
  match tsks with
  | [] => []
  | t :: ts => AssignmentsByTask t sch ++ Assignments ts sch

 def NoSimultaneousAssignments (tsks : List TaskDef) (sch : Schedule) : Bool :=
  let asgns := Assignments tsks sch
  let n := asgns.length
  (List.range n).all (fun i =>
    (List.range n).all (fun j =>
      if i == j then true
      else
        let (x₁, t₁) := asgns[i]!
        let (x₂, t₂) := asgns[j]!
        if x₁ == x₂ then t₁ ≠ t₂ else true))

-- Helper: Check if task matches a definition name (by extracting prefix before numbers)
def taskMatchesDefinition (taskId : String) (defName : String) : Bool :=
  -- Simple heuristic: task "downlink_all1" matches definition "downlink_all"
  -- More robust: check if taskId starts with defName (may have suffix like "_1", "1", "__1")
  taskId.startsWith defName

-- Check type-level "after" constraint (existential)
def checkAfterDefinitions (tsk : TaskDef) (sch : Schedule) (allTasks : List TaskDef) : Bool :=
  tsk.after_definitions.all (fun defName =>
    -- ∃ dep : TaskDef such that dep matches defName and dep ends before tsk starts
    allTasks.any (fun dep =>
      taskMatchesDefinition dep.id defName &&
      match sch.get? dep.id, sch.get? tsk.id with
      | some (_, dep_end), some (tsk_start, _) => dep_end ≤ tsk_start
      | _, _ => false
    )
  )

-- Check type-level "containedin" constraint (existential)
def checkContainedinDefinitions (tsk : TaskDef) (sch : Schedule) (allTasks : List TaskDef) : Bool :=
  tsk.containedin_definitions.all (fun defName =>
    -- ∃ container : TaskDef such that container matches defName and tsk is contained within it
    allTasks.any (fun container =>
      taskMatchesDefinition container.id defName &&
      match sch.get? container.id, sch.get? tsk.id with
      | some (c_start, c_end), some (tsk_start, tsk_end) =>
          c_start ≤ tsk_start ∧ tsk_end ≤ c_end
      | _, _ => false
    )
  )

def StartEndTimesOkTask(tsk : TaskDef) (sch : Schedule) (allTasks : List TaskDef) (n : Time) : Bool :=
  match sch.get? tsk.id with
  | some (st, en) =>
      let duration := en - st
      en ≤ n ∧
      inIntRange tsk.startrng st ∧
      inIntRange tsk.endrng   en ∧
      inIntRange tsk.durrng   duration ∧
      tsk.after.all (fun bid =>
        match sch.get? bid with
        | some (_, ben) => ben ≤ st
        | none => false) ∧
      tsk.containedin.all (fun cid =>
        match sch.get? cid with
        | some (cst, cen) => cst ≤ st ∧ en ≤ cen
        | none => false) ∧
      checkAfterDefinitions tsk sch allTasks ∧
      checkContainedinDefinitions tsk sch allTasks
  | none => false

-- Helper: find taskdef by name
def findTaskdef (taskdefs : List TaskDef) (name : String) : Option TaskDef :=
  taskdefs.find? (fun td => td.id == name)

def checkStartEndTimesOkTask (tsk : TaskDef) (sch : Schedule) (allTasks : List TaskDef) (taskdefs : List TaskDef) (n : Time) : List Violation :=
  match sch.get? tsk.id with
  | some (st, en) =>
      let duration := en - st

      let v1 := if ¬(en ≤ n) then [{
          time := en,
          task := tsk.id,
          kind := "timing",
          timeline := "",
          message := s!"Task {tsk.id} ends at {en} after endTime {n}"
        }] else []

      let v2 := if ¬(inIntRange tsk.startrng st) then [{
          time := st,
          task := tsk.id,
          kind := "timing",
          timeline := "",
          message := s!"Task {tsk.id} starts at {st} outside range [{tsk.startrng.low}, {tsk.startrng.high}]"
        }] else []

      let v3 := if ¬(inIntRange tsk.endrng en) then [{
          time := en,
          task := tsk.id,
          kind := "timing",
          timeline := "",
          message := s!"Task {tsk.id} ends at {en} outside range [{tsk.endrng.low}, {tsk.endrng.high}]"
        }] else []

      let v4 := if ¬(inIntRange tsk.durrng duration) then [{
          time := st,
          task := tsk.id,
          kind := "timing",
          timeline := "",
          message := s!"Task {tsk.id} duration {duration} outside range [{tsk.durrng.low}, {tsk.durrng.high}]"
        }] else []

      let v5 := tsk.after.flatMap (fun bid =>
        match sch.get? bid with
        | some (_, ben) =>
            if ¬(ben ≤ st) then [{
              time := st,
              task := tsk.id,
              kind := "timing",
              timeline := "",
              message := s!"Task {tsk.id} violates 'after {bid}' constraint (starts at {st}, {bid} ends at {ben})"
            }] else []
        | none => [{
            time := st,
            task := tsk.id,
            kind := "timing",
            timeline := "",
            message := s!"Task {tsk.id} references unknown task {bid} in 'after' constraint"
          }])

      let v6 := tsk.containedin.flatMap (fun cid =>
        match sch.get? cid with
        | some (cst, cen) =>
            if ¬(cst ≤ st ∧ en ≤ cen) then [{
              time := st,
              task := tsk.id,
              kind := "timing",
              timeline := "",
              message := s!"Task {tsk.id} not contained in {cid} ([{st},{en}] not in [{cst},{cen}])"
            }] else []
        | none => [{
            time := st,
            task := tsk.id,
            kind := "timing",
            timeline := "",
            message := s!"Task {tsk.id} references unknown task {cid} in 'containedin' constraint"
          }])

      let v7 := tsk.after_definitions.flatMap (fun defName =>
        let matchingTasks := allTasks.filter (fun dep => taskMatchesDefinition dep.id defName)
        if matchingTasks.isEmpty then
          match findTaskdef taskdefs defName with
          | some taskdef =>
              let constraintInfo := s!"(durrng=[{taskdef.durrng.low},{taskdef.durrng.high}], pre={taskdef.pre.length} conds, inv={taskdef.inv.length} conds)"
              [{
                time := st,
                task := tsk.id,
                kind := "timing",
                timeline := "",
                message := s!"Task {tsk.id} requires 'after {defName}' but no instances exist. Need {defName} instance {constraintInfo}"
              }]
          | none => [{
              time := st,
              task := tsk.id,
              kind := "timing",
              timeline := "",
              message := s!"Task {tsk.id} requires 'after {defName}' but no instances exist (taskdef not found)"
            }]
        else
          let satisfied := matchingTasks.any (fun dep =>
            match sch.get? dep.id with
            | some (_, dep_end) => dep_end ≤ st
            | none => false)
          if ¬satisfied then [{
            time := st,
            task := tsk.id,
            kind := "timing",
            timeline := "",
            message := s!"Task {tsk.id} violates 'after {defName}' constraint: no instance of {defName} ends before {st}"
          }] else [])

      let v8 := tsk.containedin_definitions.flatMap (fun defName =>
        let matchingTasks := allTasks.filter (fun container => taskMatchesDefinition container.id defName)
        if matchingTasks.isEmpty then
          match findTaskdef taskdefs defName with
          | some taskdef =>
              let constraintInfo := s!"(durrng=[{taskdef.durrng.low},{taskdef.durrng.high}], pre={taskdef.pre.length} conds, inv={taskdef.inv.length} conds)"
              [{
                time := st,
                task := tsk.id,
                kind := "timing",
                timeline := "",
                message := s!"Task {tsk.id} requires 'containedin {defName}' but no instances exist. Need {defName} instance {constraintInfo}"
              }]
          | none => [{
              time := st,
              task := tsk.id,
              kind := "timing",
              timeline := "",
              message := s!"Task {tsk.id} requires 'containedin {defName}' but no instances exist (taskdef not found)"
            }]
        else
          let satisfied := matchingTasks.any (fun container =>
            match sch.get? container.id with
            | some (c_start, c_end) => c_start ≤ st ∧ en ≤ c_end
            | none => false)
          if ¬satisfied then [{
            time := st,
            task := tsk.id,
            kind := "timing",
            timeline := "",
            message := s!"Task {tsk.id} violates 'containedin {defName}' constraint: no instance of {defName} contains [{st},{en}]"
          }] else [])

      v1 ++ v2 ++ v3 ++ v4 ++ v5 ++ v6 ++ v7 ++ v8
  | none => [{
      time := 0,
      task := tsk.id,
      kind := "timing",
      timeline := "",
      message := s!"Task {tsk.id} not found in schedule"
    }]

def collectStartEndTimesViolations (tsks : List TaskDef) (allTasks : List TaskDef) (taskdefs : List TaskDef) (sch : Schedule) (n : Time) : List Violation :=
  tsks.flatMap (fun t => checkStartEndTimesOkTask t sch allTasks taskdefs n)

def StartEndTimesOkTasks (tsks : List TaskDef) (allTasks : List TaskDef) (sch : Schedule) (n : Time) : Bool :=
  match tsks with
  | []       => True
  | t :: ts  => StartEndTimesOkTask t sch allTasks n ∧ StartEndTimesOkTasks ts allTasks sch n

def StartEndTimesOk (tn : TaskNet) (sch : Schedule) : Bool :=
  let ids    := TaskNamesOf tn.tasks
  let domOk  := hashSetEq (dom sch) ids
  let noSim  := NoSimultaneousAssignments tn.tasks sch
  let timeOk := StartEndTimesOkTasks tn.tasks tn.tasks sch tn.endTime
  domOk && noSim && timeOk

-- Task networks

/-- Build the deterministic initial state from timelines. -/
def initialState (tls : List Timeline) : State :=
  tls.foldl
    (fun st tl =>
      match tl with
      | .stateTimeline id _ initial => st.insert id (Value.strVal initial)
      | .atomicTimeline id          => st.insert id (Value.boolVal false)
      | .claimableTimeline id _ i   => st.insert id (Value.realVal i)
      | .cumulativeTimeline id _ _ i=> st.insert id (Value.realVal i)
      | .rateTimeline id _ _ i      => st.insert id (Value.realVal i))
    (Std.HashMap.emptyWithCapacity)

/-- Apply one tick of changes with clamping. -/
def applyChanges (oldState : State) (changeMap : ChangeMap) (bnds : IntervalMap) : State :=
  changeMap.fold (init := oldState) (fun acc tl change =>
    let (asgn?, add?) := change
    let startV :=
      match asgn? with
      | some v => v
      | none   => acc.getD tl (Value.strVal "<undef>")
    let resultV :=
      match add? with
      | some δ =>
          match addValues startV δ with
          | some v => v
          | none   => startV
      | none => startV
    let finalV :=
      match bnds.get? tl with
      | some (low, high) =>
          match valueToReal? resultV with
          | some r => Value.realVal (clamp r low high)
          | none   => resultV
      | none => resultV
    acc.insert tl finalV)

/-- Collect all task boundary times (start and end times) from schedule. -/
def boundaryTimes (sch : Schedule) : List Time :=
  let times := sch.fold (init := []) (fun acc _ (st, en) => st :: en :: acc)
  let withZero := 0 :: times
  let unique := withZero.eraseDups
  unique.mergeSort (· ≤ ·)

/-- Look up state at given time in a sparse trace (returns state from most recent boundary). -/
def stateAtTime (σ : SparseTrace) (t : Time) (default : State) : State :=
  match σ with
  | [] => default
  | (t', s) :: rest =>
      if t' ≤ t then
        match rest with
        | [] => s  -- Last boundary
        | (t'', _) :: _ =>
            if t < t'' then s  -- Before next boundary
            else stateAtTime rest t default
      else default

/-- Execute schedule using zone-based computation (sparse trace with only boundary states).
    Much more efficient than tick-by-tick for large endTime. -/
def ExecuteSparse (tn : TaskNet) (sch : Schedule) : SparseTrace :=
  let bnds := Bounds tn.timelines
  let σ0   := initialState tn.timelines
  let boundaries := boundaryTimes sch
  -- Compute states at each boundary
  let rec go (times : List Time) (cur : State) (acc : SparseTrace) : SparseTrace :=
    match times with
    | [] => acc.reverse
    | t :: rest =>
        let cm  := ComputeChanges tn.tasks sch t
        let nxt := applyChanges cur cm bnds
        go rest nxt ((t, nxt) :: acc)
  go boundaries σ0 [(0, σ0)]

/-- Legacy Execute for backwards compatibility (builds full trace). -/
def Execute (tn : TaskNet) (sch : Schedule) : Trace :=
  let σs := ExecuteSparse tn sch
  let rec expand (k : Nat) (acc : List State) : List State :=
    if k > tn.endTime then
      acc.reverse
    else
      let σ := stateAtTime σs k (initialState tn.timelines)
      expand (k+1) (σ :: acc)
  termination_by tn.endTime + 1 - k
  expand 0 []

/-- Efficient validation with detailed violation reporting. -/
def AdmissibleWithViolations (tn : TaskNet) (sch : Schedule) (included : HashSet TaskName) : ValidationResult :=
  -- Filter tasks by what's included in schedule
  let activeTasks := tn.tasks.filter (fun t =>
    match t.kind with
    | .required => true
    | .optional => included.contains t.id
    | .request  => included.contains t.id)
  -- Create modified tasknet with only active tasks
  let tn' := { tn with tasks := activeTasks }
  let σs := ExecuteSparse tn' sch

  -- Collect all violations
  -- Use tn.tasks (full list) for dependency checking, but only validate active tasks
  let timingViolations := collectStartEndTimesViolations tn'.tasks tn.tasks tn.taskdefs sch tn'.endTime
  let obligationViolations := collectObligationViolations tn' sch σs
  let allViolations := timingViolations ++ obligationViolations

  (allViolations.isEmpty, allViolations)

/-- Efficient sparse version of Admissible (recommended for large endTime). -/
def AdmissibleSparse (tn : TaskNet) (sch : Schedule) (included : HashSet TaskName) : Bool :=
  let (valid, _) := AdmissibleWithViolations tn sch included
  valid

/-- Legacy Admissible (builds full trace, slow for large endTime). -/
def Admissible (tn : TaskNet) (sch : Schedule) (included : HashSet TaskName) : Bool :=
  AdmissibleSparse tn sch included

end TaskNet
