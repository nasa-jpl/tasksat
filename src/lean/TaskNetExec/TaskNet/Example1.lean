
import TaskNet.Syntax
import TaskNet.Semantics
import TaskNet.Debug
import TaskNet.Export
import TaskNet.Temporal

namespace TaskNet

open Std
open Temp

-- ========
-- Task Net
-- ========

def tasknet : TaskNet :=
  { id := "HeatDriveCommunicate",
    timelines := [
      Timeline.stateTimeline "heating" ["off", "on"] "off",
      Timeline.stateTimeline "driving" ["off", "on"] "off",
      Timeline.stateTimeline "communicating" ["off", "on"] "off",
      Timeline.atomicTimeline "radio",
      Timeline.claimableTimeline "memory" {low := 0.0, high := 100.0} 100.0,
      Timeline.cumulativeTimeline "distance" {low := 0.0, high := 100.0} {low := 0.0, high := 100.0} 100.0,
      Timeline.rateTimeline "temperature" {low := 0.0, high := 100.0} {low := 0.0, high := 100.0} 50.0,
      Timeline.rateTimeline "battery" {low := 20.0, high := 100.0} {low := 0.0, high := 100.0} 100.0
    ],
    tasks := [
      --------------
      -- heating: --
      --------------
      { id := "heating",
        ident := 1,
        priority := 1,
        startrng := {low := 0, high := 20},
        endrng   := {low := 80, high := 100},
        durrng   := {low := 70, high := 90},
        dur := 80,
        start := 10,
        after := [],
        containedin := [],
        kind := TaskKind.required,
        pre := [
          {id := "driving", cons := [Con.val (Value.strVal "off")]},
          {id := "communicating", cons := [Con.val (Value.strVal "off")]},
          {id := "battery", cons := [Con.r_rng {low := 40, high := 100}]},
          ],
        inv := [
          {id := "driving", cons := [Con.val (Value.strVal "off")]},
          {id := "communicating", cons := [Con.val (Value.strVal "off")]},
          {id := "battery", cons := [Con.r_rng {low := 30, high := 100}]},
          ],
        post := [{id := "temperature", cons := [Con.r_rng {low := 20.0, high := 100.0}]}],
        impacts := [
          {id := "heating", when := ImpactWhen.pre, how := ImpactHow.assign (Value.strVal "on")},
          {id := "heating", when := ImpactWhen.post, how := ImpactHow.assign (Value.strVal "off")},
          {id := "temperature", when := ImpactWhen.maint, how := ImpactHow.rate 1.0},
          {id := "battery", when := ImpactWhen.maint, how := ImpactHow.rate (-0.01)}
        ]},
        --------------
        -- driving: --
        --------------
        { id := "driving",
          ident := 2,
          priority := 1,
          startrng := {low := 100, high := 120},
          endrng   := {low := 180, high := 200},
          durrng   := {low := 70, high := 90},
          dur := 80,
          start := 110,
          after := ["heating"],
          containedin := [],
          kind := TaskKind.required,
          pre := [
            {id := "communicating", cons := [Con.val (Value.strVal "off")]},
            {id := "distance", cons := [Con.r_rng {low := 5.0, high := 100.0}]},
            {id := "temperature", cons := [Con.r_rng {low := 50, high := 100}]},
            {id := "battery", cons := [Con.r_rng {low := 40, high := 100}]},
          ],
          inv := [
            {id := "communicating", cons := [Con.val (Value.strVal "off")]},
            {id := "temperature", cons := [Con.r_rng {low := 50, high := 100}]},
            {id := "battery", cons := [Con.r_rng {low := 20, high := 100}]},
          ],
          post := [{id := "distance", cons := [Con.r_rng {low := 10, high := 50}]}],
          impacts := [
            {id := "driving",     when := ImpactWhen.pre,   how := ImpactHow.assign (Value.strVal "on")},
            {id := "driving",     when := ImpactWhen.post,  how := ImpactHow.assign (Value.strVal "off")},
            {id := "distance",    when := ImpactWhen.maint, how := ImpactHow.rate (-1.0)},
            {id := "temperature", when := ImpactWhen.maint, how := ImpactHow.rate (-0.2)},
            {id := "battery",     when := ImpactWhen.maint, how := ImpactHow.rate (-0.2)}
        ]},
        --------------------
        -- communicating: --
        --------------------
        { id := "communicating",
          ident := 3,
          priority := 1,
          startrng := {low := 200, high := 220},
          endrng   := {low := 280, high := 300},
          durrng   := {low := 70, high := 90},
          dur := 80,
          start := 210,
          after := [],
          containedin := [],
          kind := TaskKind.required,
          pre := [
            {id := "driving", cons := [Con.val (Value.strVal "off")]},
            {id := "radio", cons := [Con.val (Value.boolVal false)]},
            {id := "memory", cons := [Con.r_rng {low := 40, high := 100}]},
            {id := "battery", cons := [Con.r_rng {low := 50, high := 100}]},
          ],
          inv := [
            --{id := "driving", cons := [Con.val (Value.strVal "off")]},
            {id := "battery", cons := [Con.r_rng {low := 20, high := 100}]},
          ],
          post := [
            {id := "memory", cons := [Con.r_rng {low := 0.0, high := 100.0}]}
          ],
          impacts := [
            {id := "communicating", when := ImpactWhen.pre, how := ImpactHow.assign (Value.strVal "on")},
            {id := "communicating", when := ImpactWhen.post, how := ImpactHow.assign (Value.strVal "off")},
            {id := "radio", when := ImpactWhen.pre, how := ImpactHow.assign (Value.boolVal true)},
            {id := "radio", when := ImpactWhen.post, how := ImpactHow.assign (Value.boolVal false)},
            {id := "memory", when := ImpactWhen.post, how := ImpactHow.cumulative (-100.0)},
            {id := "battery", when := ImpactWhen.maint, how := ImpactHow.rate (-0.2)}
        ]}

    ],
    endTime := 300
    }

-- ========
-- Schedule
-- ========

def sch : Schedule :=
  (Std.HashMap.emptyWithCapacity : Schedule)
    |>.insert "heating"       (10, 90)
    |>.insert "driving"       (110, 190)
    |>.insert "communicating" (210, 290)

-- ======================================
-- Test that it is an satisfactory schedule
-- ======================================

def Prop1 : TPred :=
  □ (changeFrom "heating" "on" "off" ⟹ ◇ ⟨on "driving"⟩)

/-- (2) Whenever driving switches off→on, in the past heating = "on". -/
def Prop2 : TPred :=
  □ (changeFrom "driving" "off" "on" ⟹ ◇- ⟨on "heating"⟩)

/-- (3) Never both heating and driving on at the same time. -/
def Prop3 : TPred :=
  □ (¬ (⟨on "heating"⟩ ∧ ⟨on "driving"⟩))

def Prop4: TPred :=
  □ (⟨realGE "battery" 50.0⟩)

def Prop5: TPred :=
  ◇ ⟨realApproxEq "memory" 0.0⟩

def Prop6: TPred :=
  □ (crossesUp "temperature" 80.0 ⟹ ◇ crossesDown "temperature" 90.0)

/-- Combine them. Extend as needed. -/
def Props : TPred :=
  Prop1 ∧ Prop2 ∧ Prop3 ∧ Prop4 ∧ Prop5 ∧ Prop6

#eval Admissible tasknet sch ∅  -- empty set: all tasks are required
#eval TemporalHolds tasknet sch Props
-- Admmissible and TemporalHolds should both be true:
#eval Satisfactory tasknet sch Props

#eval do
  IO.FS.writeFile "schedule.json" (Export.scheduleJson tasknet sch |>.pretty)
  IO.println "wrote schedule.json"

end TaskNet

-- Other evaluations:
-- #eval IO.println (Debug.scheduleReport tasknet sch)
-- #eval IO.println (Export.scheduleJson tasknet sch |>.pretty)
