"""
Compositional inductive-invariant sequencing check for TaskSAT (`--compositional`).

Goal: verify that ONE session preserves a predicate P ({P}S{P}) and conclude that
ANY-length sequence of that session preserves P — verify once, sequence for free,
N-independent. This is the `pre = post = P` special case of a session interface.

Correctness requires BOTH checks over the same P:

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
(forall v |= P . P(v + gamma)) is a deferred follow-up.
"""

import copy
import time
from typing import List, Optional, Tuple

from tasknet_ast import TaskNet, Task, TaskRange, TaskKind
from tasknet_smt import TaskNetTL
from tasknet_realizability import check_realizability

FORMULA_STR = "{P} S {P}  =>  forall N . {P} S^N {P}   (gamma = 0)"


def _session_defs(tn: TaskNet) -> dict:
    """Session taskdefs = DEFINITION tasks with nested children (matches
    flatten_sessions' detection)."""
    return {t.id: t for t in tn.tasks
            if t.kind == TaskKind.DEFINITION and t.children}


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
        return (not isinstance(t, TaskRange)
                and t.kind != TaskKind.DEFINITION
                and t.definition in sdefs)

    instances = sorted((t for t in tn_pre_transform.tasks if is_session_instance(t)),
                       key=lambda t: t.id)
    if not instances:
        raise ValueError(
            "compositional check requires at least one session instance "
            f"(instances of {sorted(sdefs)}); none found")

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
                        verbose: bool = True) -> dict:
    """Run the inductive-invariant sequencing check.

    Projects one session, runs AA (safety) + AE (realizability-under-P), combines.
    Verdict HOLDS iff AA holds AND AE holds; VIOLATED if either is violated; else
    UNKNOWN.

    Args:
      tn_pre_transform: the AST BEFORE apply_transforms (session children intact,
        invariant block not yet desugared).
      apply_transforms: the transform pipeline (injected to avoid an import cycle).
      TaskNetTL_cls: the encoder class (injectable for testing).

    Returns a property-result-shaped dict: name/status/duration_sec/formula plus
      session, aa, ae, note, counterexample_initial_state, unsat_core.
    """
    t0 = time.time()

    def result(status, note, session=None, aa=None, ae=None,
               counterexample=None, unsat_core=None) -> dict:
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

    # 3) AA safety: the `final within initial` property check.
    enc = TaskNetTL_cls(projected, error_trace=False, use_optimization=False)
    prop_results, _violations = enc.check_temporal_properties()
    final_entry = next((r for r in prop_results if r.get('name') == 'final'), None)
    aa_status = final_entry['status'] if final_entry else 'unknown'

    # 4) AE realizability-under-P: schedule must land back in P.
    ae = check_realizability(
        projected, max_iters=max_iters, budget_sec=budget_sec,
        verbose=verbose, require_final=True, name='realizability_under_P',
        formula="forall state |= P . exists s . valid(state, s) AND P(final)")
    ae_status = ae['status']

    # 5) Combine: HOLDS iff both hold; VIOLATED if either violated; else UNKNOWN.
    if aa_status == 'holds' and ae_status == 'holds':
        status = 'holds'
        note = (f"session '{session}' preserves the invariant (AA safety + "
                f"AE realizability-under-P both hold); any-length sequence "
                f"preserves it. gamma = 0 assumed.")
        cex, core = None, None
    elif aa_status == 'violated' or ae_status == 'violated':
        status = 'violated'
        if aa_status == 'violated':
            note = ("AA safety VIOLATED: some valid schedule ends outside the "
                    "invariant P — the session does not preserve P.")
            cex, core = None, None
        else:
            note = ("AE VIOLATED: a P-state admits no P-preserving schedule "
                    "(the vacuity trap) — sequencing is not licensed.")
            cex = ae.get('counterexample_initial_state')
            core = ae.get('unsat_core')
    else:
        status = 'unknown'
        note = (f"inconclusive (AA={aa_status}, AE={ae_status}); "
                f"see budgets/iteration limits.")
        cex, core = None, None

    return result(status, note, session=session, aa=aa_status, ae=ae_status,
                  counterexample=cex, unsat_core=core)
