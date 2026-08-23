"""
Compositional inductive-invariant sequencing check for TaskSAT (`--compositional`).

Goal: verify that ONE session preserves a predicate P ({P}S{P}) and conclude that
ANY-length sequence of that session preserves P — verify once, sequence for free,
N-independent. This is the `pre = post = P` special case of a session interface.

Correctness requires BOTH checks over the same P::

  AA safety           forall i . forall s . valid(i, s) -> P(final)
  AE realizability-P  forall state |= P . exists s . valid(state, s) AND P(final)

Safety ALONE is vacuously true for P-states that admit no schedule (the "vacuity
trap") and does not license sequencing; AE closes that gap. The overall verdict is
HOLDS iff BOTH hold.

Mechanism (all sugar / reuse — no new encoder):
  * `invariant { P }` desugars (tasknet_transforms.desugar_invariant) to
    `initial { P }` + `final within initial;`, so effective_final_constraints() == P
    and P@0 seeds init_region_constraints.
  * AA is exactly the existing `final within initial` property check
    (TaskNetTL.check_temporal_properties()).
  * AE is check_realizability(..., require_final=True) — the realizability CEGIS
    confined to region P and requiring the schedule to land back in P.
  * project_single_session() reduces an N-instance session network to a 1-instance
    network so both checks run in Theta(1) task time regardless of N.

Assumption (this cut): gamma = 0 — no inter-session gap drift. Cross-session
dependencies are dropped by the projection. The gamma-closure check
(`forall v |= P . P(v + gamma)`) is a deferred follow-up.
"""

import copy
import time
from typing import List, Optional, Tuple

from tasknet_ast import TaskNet, Task, TaskRange, TaskKind
from tasknet_smt import TaskNetTL
from tasknet_realizability import check_realizability

FORMULA_STR = ("{P} S {P}  =>  forall N . {P} S^N {P}   (gamma = 0)"
               "  —  if one run of the session keeps invariant P true, "
               "then running it any number of times back-to-back also keeps P true "
               "(assuming no timing-gap drift between sessions).")


def _session_defs(tn: TaskNet) -> dict:
    """Session taskdefs = DEFINITION tasks with nested children (matches
    flatten_sessions' detection)."""
    return {t.id: t for t in tn.tasks
            if t.kind == TaskKind.DEFINITION and t.children}


def _instance_signature(t: Task) -> str:
    """Structural signature of a session instance, IGNORING its identity (id/ident)
    and its cross-session dependencies (after/containedin — dropped under gamma=0).

    Two instances with the same signature denote the SAME session S: same taskdef,
    same params, same body. The compositional argument (verify once, hold for all N)
    is only sound for a UNIFORM chain S^N, so we use this to reject networks whose
    session instances are not all interchangeable."""
    c = copy.deepcopy(t)
    c.id = None
    c.ident = None
    c.after_instances = None
    c.containedin_instances = None
    c.after_definitions = None
    c.containedin_definitions = None
    return repr(c)


def _assert_uniform(instances: List[Task]) -> None:
    """Raise ValueError unless every session instance is interchangeable with the
    first (same session S modulo identity and cross-session deps).

    Without this guard the projection would silently keep instances[0] and drop the
    rest, yielding a false HOLDS when a dropped instance is a DIFFERENT session that
    breaks P (verified: a P-preserving session followed by a P-breaking one)."""
    sig0 = _instance_signature(instances[0])
    divergent = sorted(t.id for t in instances[1:]
                       if _instance_signature(t) != sig0)
    if divergent:
        raise ValueError(
            "compositional check requires a UNIFORM session chain (every session "
            "instance must be the same session S — same taskdef, params, and body); "
            f"instance(s) {divergent} differ from '{instances[0].id}'. Cross-session "
            "dependencies are ignored (gamma=0), but other differences are not "
            "permitted for the verify-once-hold-for-all-N argument. Verify without "
            "--compositional to check the full heterogeneous network instead.")


def project_single_session(tn_pre_transform: TaskNet) -> Tuple[TaskNet, str]:
    """Reduce an N-instance session network to a 1-instance network.

    Reads session structure from the PRE-transform AST (session taskdefs still
    carry Task.children; post-flatten this is gone). Deterministically keeps the
    first session instance (sorted by id), all taskdef templates, and drops every
    other instance. Cross-session dependencies referencing dropped instances are
    stripped (gamma = 0 assumption).

    Returns (projected_tn, session_instance_name). Raises ValueError if the
    network has no session instance to project.
    """
    sdefs = _session_defs(tn_pre_transform)
    if not sdefs:
        raise ValueError(
            "compositional check requires a session (a taskdef with nested `task` "
            "children) instantiated at least once; none found")

    def is_session_instance(t) -> bool:
        """True if `t` is an instance of one of this network's session defs."""
        return (not isinstance(t, TaskRange)
                and t.kind != TaskKind.DEFINITION
                and t.definition in sdefs)

    instances = sorted((t for t in tn_pre_transform.tasks if is_session_instance(t)),
                       key=lambda t: t.id)
    if not instances:
        raise ValueError(
            "compositional check requires at least one session instance "
            f"(instances of {sorted(sdefs)}); none found")

    # Soundness precondition: the verify-once-hold-for-all-N argument only holds
    # for a uniform chain S^N. Reject networks mixing distinct sessions.
    _assert_uniform(instances)

    chosen = instances[0]

    projected = copy.deepcopy(tn_pre_transform)

    # Names of every task we drop: all instances except the chosen one. (Taskdef
    # templates are kept — harmless and needed for field resolution.)
    dropped_ids = {t.id for t in projected.tasks
                   if t.id != chosen.id and t.kind != TaskKind.DEFINITION}

    kept_tasks: List[Task] = []
    for t in projected.tasks:
        if t.kind == TaskKind.DEFINITION:
            kept_tasks.append(t)
            continue
        if t.id != chosen.id:
            continue  # drop other instances
        # Strip the chosen instance's deps that reference dropped tasks (gamma=0).
        if t.after_instances:
            t.after_instances = [d for d in t.after_instances
                                 if d.task_id not in dropped_ids] or None
        if t.containedin_instances:
            t.containedin_instances = [d for d in t.containedin_instances
                                       if d.task_id not in dropped_ids] or None
        kept_tasks.append(t)

    projected.tasks = kept_tasks
    return projected, chosen.id


def check_compositional(tn_pre_transform: TaskNet, apply_transforms, TaskNetTL_cls=TaskNetTL,
                        max_iters: int = 50, budget_sec: float = 60.0,
                        verbose: bool = True, aa_result=None) -> dict:
    """Run the inductive-invariant sequencing check.

    Projects one session, runs AA (safety) + AE (realizability-under-P), combines.
    Verdict HOLDS iff AA holds AND AE holds; VIOLATED if either is violated; else
    UNKNOWN.

    Args:
      tn_pre_transform: the AST BEFORE apply_transforms (session children intact,
        invariant block not yet desugared).
      apply_transforms: the transform pipeline (injected to avoid an import cycle).
      TaskNetTL_cls: the encoder class (injectable for testing).
      aa_result: optional (aa_status, per_session_props) precomputed by the caller's
        AA/property phase on the SAME projected session. When provided, the AA
        property check is NOT recomputed here (the verifier runs it once in Phase 2
        and reuses it, avoiding duplicate work and double-listed property results).
        When None (standalone use), AA is computed internally as before.

    Returns a property-result-shaped dict: name/status/duration_sec/formula plus
      session, aa, ae, note, counterexample_initial_state, unsat_core.
    """
    t0 = time.time()

    def result(status, note, session=None, aa=None, ae=None,
               counterexample=None, unsat_core=None,
               per_session_properties=None) -> dict:
        """Build the result dict, stamping the elapsed time.

        Every exit path of the check goes through here, so the shape reported
        to the caller is the same whether the verdict is HOLDS, VIOLATED or
        UNKNOWN.
        """
        return {
            'name': 'compositional',
            'status': status,
            'duration_sec': round(time.time() - t0, 3),
            'formula': FORMULA_STR,
            'session': session,
            'aa': aa,
            'ae': ae,
            'note': note,
            'counterexample_initial_state': counterexample,
            'unsat_core': unsat_core,
            # User `properties {...}` checked once on the projected session; the
            # caller merges these into the overall property results (each tagged
            # per_session=True). Empty when the spec has no properties block.
            'per_session_properties': per_session_properties or [],
        }

    # 1) Project to a single session instance.
    try:
        projected, session = project_single_session(tn_pre_transform)
    except ValueError as e:
        return result('unknown', str(e))

    if not getattr(projected, 'invariant_constraints', None) \
            and not getattr(projected, 'final_extends_initial', False):
        return result('unknown',
                      "no invariant { P } block found; nothing to check",
                      session=session)

    # 2) Desugar the invariant + run the rest of the pipeline on the projected net.
    projected, _ = apply_transforms(projected)

    # 3) AA safety + per-session user properties, both on the projected net.
    #
    # The projected net carries `initial {P}` (from the invariant desugar), so a
    # property that holds here holds "from any P-state, within one session" — the
    # per-session guarantee. Because every session is interchangeable (enforced by
    # the uniformity guard in project_single_session), that discharges the property
    # for all N sessions in the chain. We check the user properties AND the `final`
    # block (= AA safety) in one pass; only the user properties get the per_session
    # tag.
    #
    # If the caller already ran this exact check on the same projected session
    # (aa_result), reuse it instead of recomputing — avoids duplicate solver work
    # and double-listed properties in the report.
    if aa_result is not None:
        aa_status, per_session_props = aa_result
    else:
        enc = TaskNetTL_cls(projected, error_trace=False, use_optimization=False)
        prop_results, _violations = enc.check_temporal_properties(per_session=True)
        final_entry = next((r for r in prop_results if r.get('name') == 'final'), None)
        aa_status = final_entry['status'] if final_entry else 'unknown'
        # Per-session user-property results (everything except the `final` AA
        # artifact) are surfaced to the caller for properties.json / the report.
        per_session_props = [r for r in prop_results if r.get('name') != 'final']

    # 4) AE realizability-under-P: schedule must land back in P.
    ae = check_realizability(
        projected, max_iters=max_iters, budget_sec=budget_sec,
        verbose=verbose, require_final=True, name='realizability_under_P',
        formula="forall state |= P . exists s . valid(state, s) AND P(final)")
    ae_status = ae['status']

    # 5) Combine: HOLDS iff both hold; VIOLATED if either violated; else UNKNOWN.
    if aa_status == 'holds' and ae_status == 'holds':
        status = 'holds'
        note = (f"Session '{session}' keeps invariant P true: from any state "
                f"where P holds, (1) every valid schedule ends with P still true "
                f"(safety) and (2) at least one valid schedule exists that ends "
                f"with P still true (realizability). So chaining any number of "
                f"these sessions keeps P true — verified once, holds for all N. "
                f"(Assumes no timing-gap drift between sessions.)")
        cex, core = None, None
    elif aa_status == 'violated' or ae_status == 'violated':
        status = 'violated'
        if aa_status == 'violated':
            note = ("Safety VIOLATED: some valid schedule starts with invariant "
                    "P true but ends with P false — one run of the session can "
                    "break P, so chaining sessions is not safe.")
            cex, core = None, None
        else:
            note = ("Realizability VIOLATED: there is a state where P holds but "
                    "NO valid schedule exists that keeps P true. Safety alone is "
                    "vacuously true there (no schedule to break P), so it does "
                    "not license chaining — see the counterexample state below.")
            cex = ae.get('counterexample_initial_state')
            core = ae.get('unsat_core')
    else:
        status = 'unknown'
        note = (f"inconclusive (AA={aa_status}, AE={ae_status}); "
                f"see budgets/iteration limits.")
        cex, core = None, None

    return result(status, note, session=session, aa=aa_status, ae=ae_status,
                  counterexample=cex, unsat_core=core,
                  per_session_properties=per_session_props)
