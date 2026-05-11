
import TaskNet.Syntax
import TaskNet.Semantics
import Lean.Data.Json

open Lean
open TaskNet

-- JSON parsing helpers

def parseIntRange (j : Json) : Except String IntRange := do
  let low ← j.getObjValAs? Int "low"
  let high ← j.getObjValAs? Int "high"
  return { low := low, high := high }

def parseValue (j : Json) : Except String Value := do
  let tag ← j.getObjValAs? String "tag"
  match tag with
  | "intVal" =>
      let v ← j.getObjValAs? Int "v"
      return Value.intVal v
  | "realVal" =>
      let v ← j.getObjValAs? Float "v"
      return Value.realVal v
  | "strVal" =>
      let v ← j.getObjValAs? String "v"
      return Value.strVal v
  | "boolVal" =>
      let v ← j.getObjValAs? Bool "v"
      return Value.boolVal v
  | _ => throw s!"Unknown value tag: {tag}"

def parseTimeline (j : Json) : Except String Timeline := do
  let tag ← j.getObjValAs? String "tag"
  let id ← j.getObjValAs? String "id"
  match tag with
  | "stateTimeline" =>
      let states ← j.getObjValAs? (Array String) "states"
      let initial ← j.getObjValAs? String "initial"
      return Timeline.stateTimeline id states.toList initial
  | "atomicTimeline" =>
      return Timeline.atomicTimeline id
  | "claimableTimeline" =>
      let rangeJ ← j.getObjVal? "range"
      let low ← rangeJ.getObjValAs? Float "low"
      let high ← rangeJ.getObjValAs? Float "high"
      let initial ← j.getObjValAs? Float "initial"
      return Timeline.claimableTimeline id { low := low, high := high } initial
  | "cumulativeTimeline" =>
      let rangeJ ← j.getObjVal? "range"
      let rlow ← rangeJ.getObjValAs? Float "low"
      let rhigh ← rangeJ.getObjValAs? Float "high"
      let boundsJ ← j.getObjVal? "bounds"
      let blow ← boundsJ.getObjValAs? Float "low"
      let bhigh ← boundsJ.getObjValAs? Float "high"
      let initial ← j.getObjValAs? Float "initial"
      return Timeline.cumulativeTimeline id { low := rlow, high := rhigh } { low := blow, high := bhigh } initial
  | "rateTimeline" =>
      let rangeJ ← j.getObjVal? "range"
      let rlow ← rangeJ.getObjValAs? Float "low"
      let rhigh ← rangeJ.getObjValAs? Float "high"
      let boundsJ ← j.getObjVal? "bounds"
      let blow ← boundsJ.getObjValAs? Float "low"
      let bhigh ← boundsJ.getObjValAs? Float "high"
      let initial ← j.getObjValAs? Float "initial"
      return Timeline.rateTimeline id { low := rlow, high := rhigh } { low := blow, high := bhigh } initial
  | _ => throw s!"Unknown timeline tag: {tag}"

def parseCon (j : Json) : Except String Con := do
  let tag ← j.getObjValAs? String "tag"
  match tag with
  | "val" =>
      let vj ← j.getObjVal? "v"
      let v ← parseValue vj
      return Con.val v
  | "i_rng" =>
      let rj ← j.getObjVal? "r"
      let r ← parseIntRange rj
      return Con.i_rng r
  | "r_rng" =>
      let rj ← j.getObjVal? "r"
      let low ← rj.getObjValAs? Float "low"
      let high ← rj.getObjValAs? Float "high"
      return Con.r_rng { low := low, high := high }
  | _ => throw s!"Unknown Con tag: {tag}"

def parseTlCon (j : Json) : Except String TlCon := do
  let id ← j.getObjValAs? String "id"
  let consArr ← j.getObjValAs? (Array Json) "cons"
  let cons ← consArr.toList.mapM parseCon
  return { id := id, cons := cons }

def parseImpact (j : Json) : Except String Impact := do
  let id ← j.getObjValAs? String "id"
  let whenStr ← j.getObjValAs? String "when"
  let when ← match whenStr with
    | "pre" => pure ImpactWhen.pre
    | "maint" => pure ImpactWhen.maint
    | "post" => pure ImpactWhen.post
    | _ => throw s!"Unknown impact when: {whenStr}"
  let howJ ← j.getObjVal? "how"
  let howTag ← howJ.getObjValAs? String "tag"
  let how ← match howTag with
    | "assign" =>
        let vj ← howJ.getObjVal? "v"
        let v ← parseValue vj
        pure (ImpactHow.assign v)
    | "cumulative" =>
        let v ← howJ.getObjValAs? Float "v"
        pure (ImpactHow.cumulative v)
    | "rate" =>
        let v ← howJ.getObjValAs? Float "v"
        pure (ImpactHow.rate v)
    | _ => throw s!"Unknown impact how tag: {howTag}"
  return { id := id, when := when, how := how }

def parseTaskKind (s : String) : Except String TaskKind :=
  match s with
  | "required" | "instance" | "definition" => pure TaskKind.required
  | "optional" => pure TaskKind.optional
  | "request" => pure TaskKind.request
  | _ => throw s!"Unknown task kind: {s}"

def parseTask (j : Json) : Except String TaskDef := do
  let id ← j.getObjValAs? String "id"
  let ident ← j.getObjValAs? Nat "ident"
  let priority ← j.getObjValAs? Nat "priority"
  let startJ ← j.getObjVal? "startrng"
  let startrng ← parseIntRange startJ
  let endJ ← j.getObjVal? "endrng"
  let endrng ← parseIntRange endJ
  let durJ ← j.getObjVal? "durrng"
  let durrng ← parseIntRange durJ
  let dur ← j.getObjValAs? Nat "dur"
  let start ← j.getObjValAs? Nat "start"
  let afterArr ← j.getObjValAs? (Array String) "after"
  let containedinArr ← j.getObjValAs? (Array String) "containedin"
  let afterDefArr ← j.getObjValAs? (Array String) "after_definitions"
  let containedinDefArr ← j.getObjValAs? (Array String) "containedin_definitions"
  let kindStr ← j.getObjValAs? String "kind"
  let kind ← parseTaskKind kindStr
  let preArr ← j.getObjValAs? (Array Json) "pre"
  let pre ← preArr.toList.mapM parseTlCon
  let invArr ← j.getObjValAs? (Array Json) "inv"
  let inv ← invArr.toList.mapM parseTlCon
  let postArr ← j.getObjValAs? (Array Json) "post"
  let post ← postArr.toList.mapM parseTlCon
  let impactsArr ← j.getObjValAs? (Array Json) "impacts"
  let impacts ← impactsArr.toList.mapM parseImpact
  return {
    id := id,
    ident := ident,
    priority := priority,
    startrng := startrng,
    endrng := endrng,
    durrng := durrng,
    dur := dur,
    start := start,
    after := afterArr.toList,
    containedin := containedinArr.toList,
    after_definitions := afterDefArr.toList,
    containedin_definitions := containedinDefArr.toList,
    kind := kind,
    pre := pre,
    inv := inv,
    post := post,
    impacts := impacts
  }

def parseTaskNet (j : Json) : Except String TaskNet := do
  let id ← j.getObjValAs? String "id"
  let timelinesArr ← j.getObjValAs? (Array Json) "timelines"
  let timelines ← timelinesArr.toList.mapM parseTimeline
  let tasksArr ← j.getObjValAs? (Array Json) "tasks"
  let tasks ← tasksArr.toList.mapM parseTask
  let taskdefsArr ← j.getObjValAs? (Array Json) "taskdefs"
  let taskdefs ← taskdefsArr.toList.mapM parseTask
  let endTime ← j.getObjValAs? Nat "endTime"
  return { id := id, timelines := timelines, tasks := tasks, taskdefs := taskdefs, endTime := endTime }

def parseSchedule (j : Json) : Except String (Schedule × Std.HashSet TaskName) := do
  let tasksJ ← j.getObjVal? "tasks"
  let tasksObj ← match tasksJ with
    | Json.obj m => pure m
    | _ => throw "Expected tasks to be an object"

  let mut sch : Schedule := Std.HashMap.emptyWithCapacity
  for (taskId, taskJ) in tasksObj do
    let st ← taskJ.getObjValAs? Nat "start"
    let en ← taskJ.getObjValAs? Nat "end"
    sch := sch.insert taskId (st, en)

  -- Parse included optional/request tasks
  let includedArr ← j.getObjValAs? (Array String) "included"
  let mut included : Std.HashSet TaskName := Std.HashSet.emptyWithCapacity
  for taskId in includedArr do
    included := included.insert taskId

  return (sch, included)

def formatValidationResult (valid : Bool) (violations : List String := []) : Json :=
  Json.mkObj [
    ("valid", Json.bool valid),
    ("violations", Json.arr (violations.map Json.str).toArray)
  ]

def main (args : List String) : IO UInt32 := do
  match args with
  | ["--tasknet", tasknetPath, "--schedule", schedulePath] => do
      -- Load tasknet JSON
      let tasknetStr ← IO.FS.readFile tasknetPath
      let tasknetJson ← match Json.parse tasknetStr with
        | Except.ok j => pure j
        | Except.error e => do
            IO.eprintln s!"Failed to parse tasknet JSON: {e}"
            return 1

      let tasknet ← match parseTaskNet tasknetJson with
        | Except.ok tn => pure tn
        | Except.error e => do
            IO.eprintln s!"Failed to parse tasknet: {e}"
            return 1

      -- Load schedule JSON
      let scheduleStr ← IO.FS.readFile schedulePath
      let scheduleJson ← match Json.parse scheduleStr with
        | Except.ok j => pure j
        | Except.error e => do
            IO.eprintln s!"Failed to parse schedule JSON: {e}"
            return 1

      let (schedule, included) ← match parseSchedule scheduleJson with
        | Except.ok s => pure s
        | Except.error e => do
            IO.eprintln s!"Failed to parse schedule: {e}"
            return 1

      -- Validate using sparse semantics with violation collection
      let (valid, violations) := AdmissibleWithViolations tasknet schedule included

      -- Format violations as strings
      let violationMessages := violations.map (fun v =>
        s!"[t={v.time}] {v.task} ({v.kind}): {v.message}")

      -- Output result as JSON
      let result := formatValidationResult valid violationMessages
      IO.println result.pretty

      return if valid then 0 else 1

  | _ => do
      IO.eprintln "Usage: tasknet-validate --tasknet <tasknet.json> --schedule <schedule.json>"
      return 1
