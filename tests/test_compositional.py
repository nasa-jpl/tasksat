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
"""

import json
from pathlib import Path

import pytest
from .conftest import *


class TestCompositional:
    """End-to-end tests via the verifier CLI."""

    def test_holds(self):
        """Session Cycle drives idle->busy->idle; P = {mode = idle} is preserved:
        AA safety holds AND AE realizability-under-P holds -> compositional HOLDS.
        Projection reduces the two-instance network (cycle1, cycle2) to cycle1."""
        verify_out('tasknet62_compositional_holds.tn',
                   extra_args=['--compositional'])(
            "Checking compositional invariant",
            "→ HOLDS ✓ (AA safety=holds, AE realizability-under-P=holds)",
            "session 'cycle1' preserves the invariant",
            # projection kept cycle1 (its qualified children appear in the schedule)
            "cycle1__activate",
        )

    def test_ae_violated(self):
        """The vacuity trap: P = {charge in [20,100]} but the work task needs
        charge >= 30 and nothing replenishes it first. AA safety (vacuously)
        holds, but charge = 20 satisfies P with NO P-preserving schedule ->
        AE VIOLATED -> compositional VIOLATED, with the counterexample state."""
        verify_out('tasknet63_compositional_ae_violated.tn',
                   extra_args=['--compositional'])(
            "Checking compositional invariant",
            "→ VIOLATED! (AA safety=holds, AE realizability-under-P=violated)",
            "vacuity trap",
            "Initial state (satisfies P) with no P-preserving schedule:",
            "charge = 20",
        )

    def test_flag_off_no_check(self):
        """Without --compositional the compositional check must still fire here
        because tasknet62 declares `invariant compositional {...}` in the spec;
        tasknet63 likewise. Use a plain net to confirm the check is silent."""
        output = verify('tasknet52_realizability_holds.tn')
        assert "Checking compositional invariant" not in output

    def test_spec_level_opt_in(self):
        """`invariant compositional {...}` in the spec triggers the check with no
        CLI flag."""
        output = verify('tasknet62_compositional_holds.tn')
        assert "Checking compositional invariant" in output
        assert "AA safety=holds, AE realizability-under-P=holds" in output


class TestCompositionalPropertiesJson:
    """The compositional verdict is persisted to properties.json with aa/ae
    sub-statuses (protects the Phase-3.5 result-append in tasknet_verifier.py)."""

    def _latest_properties(self, stem):
        path = (PROJECT_ROOT / '.tasksat' / 'schedules' / stem / 'latest'
                / 'properties.json')
        with open(path) as f:
            return json.load(f)

    def test_holds_entry(self):
        verify('tasknet62_compositional_holds.tn', extra_args=['--compositional'])
        props = self._latest_properties('tasknet62_compositional_holds')
        entry = next((r for r in props if r.get('name') == 'compositional'), None)
        assert entry is not None, "no compositional entry in properties.json"
        assert entry['status'] == 'holds'
        assert entry['aa'] == 'holds'
        assert entry['ae'] == 'holds'
        assert entry['session'] == 'cycle1'
        # unsat_core is stripped from the persisted entry
        assert 'unsat_core' not in entry

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
