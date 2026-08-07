"""Tests for the compositional inductive-invariant sequencing check (--compositional).

Semantics: verify ONE session preserves a predicate P ({P}S{P}) and conclude that
ANY-length sequence preserves P. Correctness requires BOTH sub-checks over the same P:

  AA safety           forall i . forall s . valid(i,s) -> P(final)
  AE realizability-P  forall state |= P . exists s . valid(state,s) AND P(final)

Safety alone is vacuously true for P-states admitting no schedule (the "vacuity
trap"); the AE check closes that gap. Verdict is HOLDS iff BOTH hold. The check
first projects an N-instance session network to ONE instance (N-independence).

Implemented in src/smt/tasknet_compositional.py + the `invariant {}` block sugar
(desugars to `initial { P }` + `final within initial;`).

Note on testing strategy: the HOLDS fixture (tasknet62) has 20 chained session
instances to demonstrate N-independence. The compositional check itself projects
20 -> 1 and runs in ~0.03s, but the verifier's *standard* validity + property
phases (which always run first, before the compositional phase) are NOT
N-independent and take ~60s+ on the full 40-task network. So the HOLDS case is
exercised by calling check_compositional() DIRECTLY (the pattern test_sessions.py
uses) rather than through the full CLI. The AE-violated fixture (tasknet63) is a
single instance, so it is exercised end-to-end through the CLI.
"""

import json
import sys
import time
from pathlib import Path

import pytest
from .conftest import *

sys.path.insert(0, str(Path(__file__).parent.parent / 'src' / 'smt'))
from tasknet_parser import parse_tasknet_file  # noqa: E402
from tasknet_transforms import apply_transforms  # noqa: E402
from tasknet_compositional import check_compositional, project_single_session  # noqa: E402
from tasknet_ast import TaskKind  # noqa: E402

HOLDS_FIXTURE = 'tests/tasknet_files/valid/tasknet62_compositional_holds.tn'


class TestCompositionalProjection:
    """The HOLDS case, driven directly through check_compositional() so the
    N-independence win is visible: 20 session instances collapse to one and the
    check is fast, even though the full-network CLI would not be."""

    def test_projection_collapses_many_instances_to_one(self):
        """tasknet62 has 20 chained Cycle instances; projection keeps exactly one
        representative session (cycle1) regardless of N."""
        tn = parse_tasknet_file(HOLDS_FIXTURE)
        n_instances = sum(1 for t in tn.tasks
                          if t.kind != TaskKind.DEFINITION and t.definition == 'Cycle')
        assert n_instances == 20, f"fixture should have 20 instances, has {n_instances}"

        projected, session = project_single_session(tn)
        assert session == 'cycle1'
        kept = [t for t in projected.tasks
                if t.kind != TaskKind.DEFINITION and t.definition == 'Cycle']
        assert len(kept) == 1, "projection must keep exactly one session instance"
        assert kept[0].id == 'cycle1'

    def test_holds_and_is_n_independent(self):
        """{P}S{P} holds (AA safety + AE realizability-under-P) for the 20-instance
        network, and the check is fast because it runs on the single projected
        session, not the full 20-deep chain -- the whole point of the feature."""
        tn = parse_tasknet_file(HOLDS_FIXTURE)
        t0 = time.time()
        result = check_compositional(tn, apply_transforms, verbose=False)
        elapsed = time.time() - t0

        assert result['status'] == 'holds'
        assert result['aa'] == 'holds'
        assert result['ae'] == 'holds'
        assert result['session'] == 'cycle1'
        # Projection makes this Theta(1) in the instance count. Generous bound to
        # stay robust on slow CI while still catching a regression that lets the
        # check touch the full 20-instance encoding (which takes ~60s+).
        assert elapsed < 10.0, f"compositional check took {elapsed:.1f}s (expected << full-net time)"

    def test_holds_result_shape(self):
        """The HOLDS result dict carries the property-result shape the verifier
        persists to properties.json (name/status/formula/session/aa/ae)."""
        tn = parse_tasknet_file(HOLDS_FIXTURE)
        result = check_compositional(tn, apply_transforms, verbose=False)
        assert result['name'] == 'compositional'
        assert result['formula']
        assert result['aa'] == 'holds' and result['ae'] == 'holds'
        assert result['session'] == 'cycle1'
        assert result['counterexample_initial_state'] is None
        # No user properties block -> no per-session results.
        assert result['per_session_properties'] == []


PER_SESSION_FIXTURE = ('tests/tasknet_files/valid/'
                       'tasknet64_compositional_per_session_props.tn')


class TestPerSessionProperties:
    """User `properties {...}` under --compositional are checked ONCE on the
    projected single session and reported per-session (verify once, holds for
    all N) rather than on the full N-instance network."""

    def test_properties_checked_per_session(self):
        """Both shared-timeline properties hold on the projected session and are
        tagged per_session=True; the compositional verdict still HOLDS."""
        tn = parse_tasknet_file(PER_SESSION_FIXTURE)
        result = check_compositional(tn, apply_transforms, verbose=False)

        assert result['status'] == 'holds'
        ps = {p['name']: p for p in result['per_session_properties']}
        assert set(ps) == {'mode_well_defined', 'reaches_idle'}
        for p in ps.values():
            assert p['status'] == 'holds'
            assert p['per_session'] is True

    def test_per_session_is_n_independent(self):
        """The per-session property check runs on the single projected session,
        so it is fast regardless of the 5-instance (N) chain length."""
        tn = parse_tasknet_file(PER_SESSION_FIXTURE)
        t0 = time.time()
        result = check_compositional(tn, apply_transforms, verbose=False)
        elapsed = time.time() - t0
        assert result['status'] == 'holds'
        assert len(result['per_session_properties']) == 2
        assert elapsed < 10.0, f"per-session check took {elapsed:.1f}s (expected << full-net)"


class TestCompositionalCLI:
    """End-to-end tests via the verifier CLI. Uses the single-instance AE-violated
    fixture (tasknet63), which is fast through the full pipeline."""

    def test_ae_violated(self):
        """The vacuity trap: P = {charge in [20,100]} but the work task needs
        charge >= 30 and nothing replenishes it first. AA safety (vacuously)
        holds, but charge = 20 satisfies P with NO P-preserving schedule ->
        AE VIOLATED -> compositional VIOLATED, with the counterexample state."""
        verify_out('tasknet63_compositional_ae_violated.tn',
                   extra_args=['--compositional'])(
            "Checking compositional invariant",
            "→ VIOLATED! (safety (every run keeps P)=holds, "
            "realizability (some run keeps P)=violated)",
            "Realizability VIOLATED",
            "Initial state (satisfies P) with no P-preserving schedule:",
            "charge = 20",
        )

    def test_spec_level_opt_in(self):
        """`invariant compositional {...}` in the spec triggers the check with no
        CLI flag (tasknet63 declares it)."""
        output = verify('tasknet63_compositional_ae_violated.tn')
        assert "Checking compositional invariant" in output

    def test_flag_off_no_check(self):
        """A net without an `invariant compositional` block and no --compositional
        flag must not run the check."""
        output = verify('tasknet52_realizability_holds.tn')
        assert "Checking compositional invariant" not in output


class TestCompositionalPropertiesJson:
    """The compositional verdict is persisted to properties.json with aa/ae
    sub-statuses (protects the Phase-3.5 result-append in tasknet_verifier.py)."""

    def _latest_properties(self, stem):
        path = (PROJECT_ROOT / '.tasksat' / 'schedules' / stem / 'latest'
                / 'properties.json')
        with open(path) as f:
            return json.load(f)

    def test_violated_entry(self):
        verify('tasknet63_compositional_ae_violated.tn',
               extra_args=['--compositional'])
        props = self._latest_properties('tasknet63_compositional_ae_violated')
        entry = next((r for r in props if r.get('name') == 'compositional'), None)
        assert entry is not None, "no compositional entry in properties.json"
        assert entry['status'] == 'violated'
        assert entry['aa'] == 'holds'
        assert entry['ae'] == 'violated'
        assert entry['counterexample_initial_state']
        # unsat_core is stripped from the persisted entry
        assert 'unsat_core' not in entry
