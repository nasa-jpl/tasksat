import TaskNet.Syntax
import TaskNet.Semantics
import Lean.Data.Json

namespace TaskNet
namespace Export

open Std
open Lean

/-=========================
  JSON helpers (typed, safe)
  =========================-/

-- prefer Lean’s `toJson` and `Json.mkObj` to avoid RBMap hassles
private def jstr  (s : String) : Json := toJson s
private def jnumF (f : Float)  : Json := toJson f
private def jnumI (i : Int)    : Json := toJson i
private def jbool (b : Bool)   : Json := toJson b
private def jobj  (xs : List (String × Json)) : Json := Json.mkObj xs
private def jarr  (xs : List Json) : Json := Json.arr xs.toArray

/-- Convert domain `Value` to typed `Json`. -/
def valueToJson : Value → Json
  | .intVal  i => jnumI i
  | .realVal r  => jnumF r
  | .strVal  s  => jstr s
  | .boolVal b  => jbool b

/-- All timeline ids in a stable order (reuse your helper). -/
def sortedTimelineIds (tls : List Timeline) : List TimeLineName :=
  let rec go : List Timeline → List TimeLineName
    | [] => []
    | (tl : Timeline) :: xs =>
      match tl with
      | .stateTimeline id _ _        => id :: go xs
      | .atomicTimeline id           => id :: go xs
      | .claimableTimeline id _ _    => id :: go xs
      | .cumulativeTimeline id _ _ _ => id :: go xs
      | .rateTimeline id _ _ _       => id :: go xs
  (go tls).mergeSort (· ≤ ·)

/-- Encode a full `State` as a JSON object: { id: <typed value>, ... }. -/
def stateToJson (tn : TaskNet) (σ : State) : Json :=
  let ids := sortedTimelineIds tn.timelines
  let fields :=
    ids.map (fun id =>
      (id,
        match σ.get? id with
        | some v => valueToJson v
        | none   => Json.null))
  jobj fields

/-- JSON for a single Con (expected set element). -/
def conToJson : Con → Json
  | .val v    => jobj [("kind", jstr "val"),    ("value", valueToJson v)]
  | .i_rng r  => jobj [("kind", jstr "i_rng"),  ("low", toJson r.low),  ("high", toJson r.high)]
  | .r_rng r  => jobj [("kind", jstr "r_rng"),  ("low", jnumF r.low),   ("high", jnumF r.high)]

/-- JSON for one TlCon explanation at a given state. -/
def tlConExplainJson (state : State) (c : TlCon) : Json :=
  let actual :=
    match state.get? c.id with
    | some v => valueToJson v
    | none   => Json.null
  let holds := TimeLineCondition c state
  jobj
    [ ("id",      jstr c.id)
    , ("actual",  actual)
    , ("holds",   jbool holds)
    , ("expect",  jarr (c.cons.map conToJson))
    ]

/-- PRE/INV/POST block for one task at time `k`. -/
def pipForTaskJson (t : TaskDef) (sch : Schedule) (cur next : State) (k : Nat) : Json :=
  match sch.get? t.id with
  | none => jobj [("task", jstr t.id), ("missingInSchedule", jbool true)]
  | some (st,en) =>
    let preActive  := (k = st)
    let invActive  := (st ≤ k ∧ k ≤ en)
    let postActive := (k = en)
    let preHolds   := if preActive  then TimeLineConditions t.pre  cur  else true
    let invHolds   := if invActive  then TimeLineConditions t.inv  cur  else true
    let postHolds  := if postActive then TimeLineConditions t.post next else true
    let preDet  := if preActive  then jarr (t.pre.map  (tlConExplainJson cur))  else Json.null
    let invDet  := if invActive  then jarr (t.inv.map  (tlConExplainJson cur))  else Json.null
    let postDet := if postActive then jarr (t.post.map (tlConExplainJson next)) else Json.null
    jobj
      [ ("task", jstr t.id)
      , ("pre",  jobj [("active", jbool preActive),  ("holds", jbool preHolds),  ("details", preDet)])
      , ("inv",  jobj [("active", jbool invActive),  ("holds", jbool invHolds),  ("details", invDet)])
      , ("post", jobj [("active", jbool postActive), ("holds", jbool postHolds), ("details", postDet)])
      ]

/-- JSON entry for a single timeline change at time k. -/
def changeJson (id : String) (chg : Change) : Json :=
  match chg with
  | (some v, _)      => jobj [("id", jstr id), ("kind", jstr "assign"), ("value", valueToJson v)]
  | (none, some r)   => jobj [("id", jstr id), ("kind", jstr "delta"),  ("value", jnumF r)]
  | (none, none)     => jobj [("id", jstr id), ("kind", jstr "none")]

/-- All changes at time k, sorted by id, as JSON array of objects. -/
def changesAtJson (tn : TaskNet) (sch : Schedule) (k : Nat) : Json :=
  let cm  := ComputeChanges tn.tasks sch k
  let ids := (dom cm).toList.mergeSort (· ≤ ·)
  jarr (ids.map (fun id => changeJson id (cm.get! id)))

/-- Diffs from k to k+1 (only where value really changed), as JSON array. -/
def diffsAtJson (tn : TaskNet) (σ : Trace) (k : Nat) : Json :=
  let cur  := σ[k]!
  let next := if k + 1 < σ.length then σ[k+1]! else cur
  let ids  := sortedTimelineIds tn.timelines
  let changed :=
    ids.filter (fun id =>
      match cur.get? id, next.get? id with
      | some v1, some v2 => v1 != v2
      | none, none       => false
      | _, _             => true)
  let rows :=
    changed.map (fun id =>
      let fromvalue :=
        match cur.get? id with
        | some v => valueToJson v
        | none   => Json.null
      let tovalue :=
        match next.get? id with
        | some v => valueToJson v
        | none   => Json.null
      jobj [("id", jstr id), ("from", fromvalue), ("to", tovalue)])
  jarr rows

/-- Which tasks start/end at k. -/
def taskStartsAt (tsks : List TaskDef) (sch : Schedule) (k : Nat) : List TaskName :=
  tsks.filterMap (fun t =>
    match sch.get? t.id with
    | some (st, _) => if st = k then some t.id else none
    | none         => none)

def taskEndsAt (tsks : List TaskDef) (sch : Schedule) (k : Nat) : List TaskName :=
  tsks.filterMap (fun t =>
    match sch.get? t.id with
    | some (_, en) => if en = k then some t.id else none
    | none         => none)

/-- Boundary times (sorted, dedup). -/
def insertSortedUnique (x : Nat) : List Nat → List Nat
  | []      => [x]
  | y :: ys => if x < y then x :: y :: ys else if x = y then y :: ys else y :: insertSortedUnique x ys

def sortUnique (xs : List Nat) : List Nat :=
  xs.foldl (fun acc x => insertSortedUnique x acc) []

def boundaryTimes (sch : Schedule) : List Nat :=
  let pairs := sch.fold (init := ([] : List (Nat × Nat))) (fun acc _ (st,en) => (st,en) :: acc)
  let flat  := pairs.foldl (fun acc (st,en) => acc ++ [st, en]) []
  sortUnique flat

/-- One full step (boundary) as JSON. -/
def stepJson (tn : TaskNet) (sch : Schedule) (σ : Trace) (k : Nat) : Json :=
  let len    := σ.length
  let cur    := σ[k]!
  let next   := if k + 1 < len then σ[k+1]! else cur
  let starts := taskStartsAt tn.tasks sch k
  let ends   := taskEndsAt   tn.tasks sch k
  let pip    := tn.tasks.map (fun t => pipForTaskJson t sch cur next k)
  jobj
    [ ("k",           toJson k)
    , ("starts",      toJson starts)
    , ("ends",        toJson ends)
    , ("stateBefore", stateToJson tn cur)
    , ("changes",     changesAtJson tn sch k)
    , ("diffs",       diffsAtJson tn σ k)
    , ("preInvPost",  jarr pip)
    , ("stateAfter",  stateToJson tn next)
    ]

/-- Whole schedule, structured. -/
def scheduleJson (tn : TaskNet) (sch : Schedule) : Json :=
  let σ  := Execute tn sch
  let ks := boundaryTimes sch
  jobj
    [ ("tasknetId", jstr tn.id)
    , ("endTime",   toJson tn.endTime)
    , ("valid",     jbool (Admissible tn sch ∅))  -- empty set: all tasks are required
    , ("steps",     jarr (ks.map (stepJson tn sch σ)))
    ]

end Export
end TaskNet
