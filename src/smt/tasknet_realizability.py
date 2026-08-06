"""
Realizability (initial-state coverage) check for TaskSAT.

Verifies:  forall i in InitRegion . exists schedule pi . valid(i, pi)

i.e. EVERY initial state admitted by the spec (declared timeline initial values,
the `initial {...}` block, zone-0 ranges/bounds/domains) admits some valid
schedule. This complements the two existing checks:

  1. Validity:    exists i, pi . valid(i, pi)                (planning)
  2. Properties:  forall i, pi . valid(i, pi) -> sat(pi, phi) (checking)

Check 2 is vacuously true for an initial state with NO valid schedule, and
check 1 only proves that SOME initial state has one. This check closes the gap:
its counterexample is a concrete initial state from which nothing can be
scheduled, reported together with the unsat core explaining why.

Algorithm: CEGIS (counterexample-guided) loop. A direct quantified query would
face the encoding's nonlinear terms (rate * zone-duration); instead:

  S_init := the initial region (TaskNetSMT.init_region_constraints)
  repeat:
    1. ask S_init for a candidate initial state i* not covered yet
       (UNSAT => every initial state is covered => HOLDS)
    2. solve the full planning problem pinned to i*
       (UNSAT => i* is a genuine counterexample => VIOLATED)
    3. otherwise generalize the found schedule: substituting its concrete
       times/inclusions into the full constraint set Phi makes it LINEAR in the
       remaining variables, so `Not(Exists(aux, Phi_sigma))` blocks from S_init
       the ENTIRE set of initial states this schedule skeleton covers.

If a quantified blocking clause makes S_init return unknown, the loop falls
back to point blocking (sound, but HOLDS becomes unreachable over real-valued
regions - reported in the note).
"""

import time
from typing import List, Optional, Tuple

from z3 import Solver, And, Not, Exists, simplify, substitute, sat, unsat
from z3.z3util import get_vars

from tasknet_ast import (
    TaskNet, StateTimeline, AtomicTimeline, ClaimableTimeline,
    CumulativeTimeline, RateTimeline,
)
from tasknet_smt import TaskNetTL

FORMULA_STR = "forall initial state i . exists schedule s . valid(i, s)"


def _zone0_vars(enc) -> List:
    """All zone-0 (initial state) variables of an encoder."""
    out = []
    for _, (_, _, _, vars_z) in enc.state_tl_zone.items():
        out.append(vars_z[0])
    for vars_z in enc.atomic_tl_zone.values():
        out.append(vars_z[0])
    for _, (_, _, vars_z) in enc.numeric_tl_zone.items():
        out.append(vars_z[0])
    for rate_vars in enc.rate_tl_rate_zone.values():
        out.append(rate_vars[0])
    return out


def _initial_fully_determined(enc) -> bool:
    """True if every timeline's zone-0 value is pinned by a declaration.
    Atomic timelines and rate timelines' rates are always pinned (defaults);
    numeric and state timelines are pinned iff they declare an initial value."""
    for tl in enc.tn.timelines:
        if isinstance(tl, (ClaimableTimeline, CumulativeTimeline, RateTimeline)):
            if tl.initial is None:
                return False
        elif isinstance(tl, StateTimeline):
            if tl.initial is None:
                return False
    return True


def _schedule_subs(enc, model) -> List[Tuple]:
    """(var, value) substitution pairs pinning the schedule skeleton: zone
    boundary times, task start/end times, optional/request inclusions."""
    subs = []
    for z in enc.zones:
        subs.append((z, model.eval(z, model_completion=True)))
    for v in enc.start_vars.values():
        subs.append((v, model.eval(v, model_completion=True)))
    for v in enc.end_vars.values():
        subs.append((v, model.eval(v, model_completion=True)))
    for v in enc.optional_included.values():
        subs.append((v, model.eval(v, model_completion=True)))
    for v in enc.request_included.values():
        subs.append((v, model.eval(v, model_completion=True)))
    return subs


def _format_value(enc, var, val) -> Tuple[str, str]:
    """(timeline_id, human-readable value) for a zone-0 var and its Z3 value."""
    name = str(var)
    # zone-0 vars are named "<tl>_z0" / "<tl>_rate_z0"
    if name.endswith("_rate_z0"):
        tl_id = name[: -len("_rate_z0")]
        label = f"{tl_id} (rate)"
    else:
        tl_id = name[: -len("_z0")]
        label = tl_id
    if tl_id in enc.state_tl_zone:
        _, _, i2s, _ = enc.state_tl_zone[tl_id]
        try:
            return label, i2s[val.as_long()]
        except Exception:
            return label, str(val)
    try:
        return label, str(val.as_decimal(6)).rstrip("?")
    except Exception:
        return label, str(val)


def _format_initial_state(enc, istar) -> dict:
    """{timeline: value} human-readable rendering of a candidate initial state."""
    out = {}
    for var, val in istar:
        label, pretty = _format_value(enc, var, val)
        out[label] = pretty
    return out


def check_realizability(tn: TaskNet, max_iters: int = 50, budget_sec: float = 60.0,
                        per_check_timeout_ms: int = 10000, verbose: bool = True,
                        require_final: bool = False, name: str = 'realizability',
                        formula: Optional[str] = None) -> dict:
    """
    Run the realizability check. Returns a dict shaped like a property result
    (name/status/duration_sec/formula) plus:
      iterations, skeletons_found, note,
      counterexample_initial_state (dict or None), unsat_core (dict or None).

    require_final: when True, the existential schedule must additionally land in
    the final region (``_encode_final_holds()``), turning the check into the
    inductive-invariant realizability-under-P form
    ``forall state |= P . exists s . valid(state, s) AND P(final)`` used by the
    compositional checker. The initial region already includes P@0 (the invariant
    desugar folds P into the initial block, which seeds init_region_constraints).
    name/formula override the reported labels.
    """
    t0 = time.time()
    formula_str = formula if formula is not None else FORMULA_STR

    def result(status: str, note: str, iterations: int = 0, skeletons: int = 0,
               counterexample=None, unsat_core=None) -> dict:
        return {
            'name': name,
            'status': status,
            'duration_sec': round(time.time() - t0, 3),
            'formula': formula_str,
            'iterations': iterations,
            'skeletons_found': skeletons,
            'note': note,
            'counterexample_initial_state': counterexample,
            'unsat_core': unsat_core,
        }

    # Template encoder: supplies the initial-region constraints, the zone-0
    # variables, and (with track=False) the exact full constraint set Phi via
    # solver.assertions(). Its solver is never checked.
    template = TaskNetTL(tn, error_trace=False, use_optimization=False, track=False)
    init_vars = _zone0_vars(template)
    init_names = {str(v) for v in init_vars}

    # Under require_final we must confirm an ACTUAL P-preserving schedule exists
    # for every P-state (a fully-determined initial state still needs its final
    # landing verified), so skip the validity-coincides fast path.
    if not require_final and _initial_fully_determined(template):
        return result(
            'holds',
            "initial state is fully determined by declarations; "
            "coincides with the validity check")

    Phi = And(*template.solver.assertions())
    if require_final:
        # Phi must also require the schedule to land in P(final), so that the
        # generalized covered-region (Not(Exists(aux, Phi_sigma))) blocks ONLY
        # initial states covered by a P-PRESERVING skeleton — else HOLDS would be
        # unsound. The template is track=False and its solver is never checked, so
        # _encode_final_holds()'s _con_holds_zone side effects are harmless here.
        final_holds = template._encode_final_holds()
        if final_holds is not True:
            Phi = And(Phi, final_holds)

    # S_init: the initial region, progressively carved by blocking clauses.
    S = Solver()
    S.set("timeout", per_check_timeout_ms)
    S.add(*template.init_region_constraints)

    skeletons = 0
    blocked_points = []   # And(v == val, ...) per covered candidate (fallback)
    point_blocking = False

    for it in range(1, max_iters + 1):
        if time.time() - t0 > budget_sec:
            return result('unknown',
                          f"budget of {budget_sec}s exhausted after {it - 1} iterations",
                          iterations=it - 1, skeletons=skeletons)

        r = S.check()

        if r == unsat:
            note = f"every initial state is covered by {skeletons} schedule skeleton(s)"
            return result('holds', note, iterations=it, skeletons=skeletons)

        if r != sat:
            # unknown: if quantified blocking is the suspect, fall back to
            # point blocking (sound; HOLDS becomes unreachable over real regions)
            if not point_blocking:
                point_blocking = True
                if verbose:
                    print("  (quantified blocking returned unknown; "
                          "falling back to point blocking)")
                S = Solver()
                S.set("timeout", per_check_timeout_ms)
                S.add(*template.init_region_constraints)
                for p in blocked_points:
                    S.add(Not(p))
                continue
            return result('unknown',
                          f"solver returned unknown on the initial region after "
                          f"{skeletons} skeleton(s); point-blocking fallback also inconclusive",
                          iterations=it, skeletons=skeletons)

        # Candidate initial state not covered by any skeleton found so far
        m_init = S.model()
        istar = [(v, m_init.eval(v, model_completion=True)) for v in init_vars]

        if verbose:
            free_dims = _format_initial_state(template, istar)
            print(f"  [iter {it}] trying initial state: "
                  + ", ".join(f"{k} = {v}" for k, v in free_dims.items()))

        # Full planning problem pinned to i* (tracked: pins join the unsat core)
        enc = TaskNetTL(tn, error_trace=False, use_optimization=False)
        for v, val in istar:
            enc.add_tracked(v == val, f"realizability_pin: initial {v} = {val}")
        if require_final:
            # Require the schedule to end back in P: UNSAT now means this P-state
            # admits no P-PRESERVING schedule (the vacuity-trap witness).
            final_holds = enc._encode_final_holds()
            if final_holds is not True:
                enc.add_tracked(final_holds,
                                "compositional: invariant P must hold at final state")
        model, unsat_core_data = enc.solve()

        if model is None:
            counterexample = _format_initial_state(enc, istar)
            note = ("initial state satisfying P with NO P-preserving schedule found"
                    if require_final else
                    "initial state with NO valid schedule found")
            return result('violated', note,
                          iterations=it, skeletons=skeletons,
                          counterexample=counterexample,
                          unsat_core=unsat_core_data)

        # Generalize: pin the schedule skeleton; the residual formula is linear
        # in the initial-state (and timeline evolution) variables. Block every
        # initial state this skeleton covers.
        skeletons += 1
        blocked_points.append(And(*[v == val for v, val in istar]))

        if point_blocking:
            S.add(Not(blocked_points[-1]))
        else:
            subs = _schedule_subs(enc, model)
            phi_sigma = simplify(substitute(Phi, subs))
            aux = [v for v in get_vars(phi_sigma) if str(v) not in init_names]
            covered = Exists(aux, phi_sigma) if aux else phi_sigma
            S.add(Not(covered))

    return result('unknown',
                  f"iteration limit of {max_iters} reached; "
                  f"{skeletons} skeleton(s) found so far",
                  iterations=max_iters, skeletons=skeletons)
