"""Tests for the Phase-1 validity-solve timeout (--timeout).

A per-solver Z3 `timeout` bounds the Phase-1 validity solve. When it fires, the
solve returns `unknown`, which `TaskNetTL.solve()` surfaces as `SolverTimeout`
rather than silently misreading it as UNSAT. The verifier CLI turns that into a
`timeout` status; the web layer parses the request field and passes it through.
"""

import sys
from pathlib import Path

import pytest

from .conftest import verify, PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT / 'src' / 'smt'))

# A network whose Phase-1 solve is clearly non-instant (~5s), so a 1 ms deadline
# reliably fires while a generous one succeeds.
SLOW_TN = 'tasknet69_flat_rover.tn'


def _encode(tn_file, **kwargs):
    from tasknet_parser import parse_tasknet_file
    from tasknet_transforms import apply_transforms
    from tasknet_smt import TaskNetTL
    tn = parse_tasknet_file(f'tests/tasknet_files/valid/{tn_file}')
    tn, _ = apply_transforms(tn)
    return TaskNetTL(tn, error_trace=True, use_optimization=False, **kwargs)


class TestSolveTimeoutUnit:
    """In-process: the encoder raises SolverTimeout when the deadline fires."""

    def test_tiny_timeout_raises_solvertimeout(self):
        from tasknet_smt import SolverTimeout
        enc = _encode(SLOW_TN, track=False, portfolio=True, timeout_ms=1)
        with pytest.raises(SolverTimeout):
            enc.solve(analyze_core=False)

    def test_tiny_timeout_raises_without_portfolio(self):
        from tasknet_smt import SolverTimeout
        enc = _encode(SLOW_TN, track=False, portfolio=False, timeout_ms=1)
        with pytest.raises(SolverTimeout):
            enc.solve(analyze_core=False)

    def test_no_timeout_solves_normally(self):
        # Default (no deadline): a model is found, not a timeout.
        enc = _encode(SLOW_TN, track=False, portfolio=True)
        m, _core = enc.solve(analyze_core=False)
        assert m is not None


class TestTimeoutCLI:
    """End-to-end via the verifier subprocess."""

    def test_tiny_timeout_reports_timeout(self):
        out = verify(SLOW_TN, extra_args=['--timeout', '0.2'])
        assert 'TIMEOUT' in out
        # Graceful stop, not a crash: no schedule and no UNSAT claim.
        assert 'Valid schedule found' not in out

    def test_generous_timeout_still_succeeds(self):
        out = verify(SLOW_TN, extra_args=['--timeout', '60'])
        assert 'Valid schedule found' in out

    def test_timeout_metadata_status(self, tmp_path):
        import json
        # Run in an isolated cwd so we read this run's own metadata.
        import subprocess
        src = PROJECT_ROOT / 'tests' / 'tasknet_files' / 'valid' / SLOW_TN
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / 'src' / 'smt' / 'tasknet_verifier.py'),
             str(src), '--timeout', '0.2'],
            cwd=tmp_path, capture_output=True, text=True)
        meta = tmp_path / '.tasksat' / 'schedules' / 'tasknet69_flat_rover' / 'latest' / 'metadata.json'
        assert meta.exists()
        assert json.loads(meta.read_text())['status'] == 'timeout'


class TestTimeoutWebPlumbing:
    """The web layer's request parsing and command building."""

    def test_verifier_cmd_appends_timeout(self):
        import tasknet_web as w
        assert w.verifier_cmd('x.tn', 'optimize', timeout=5.0)[-2:] == ['--timeout', '5.0']
        assert '--timeout' not in w.verifier_cmd('x.tn', 'optimize')

    def test_parse_timeout(self):
        import tasknet_web as w
        assert w.parse_timeout({'timeout': '5'}) == 5.0
        assert w.parse_timeout({'timeout': ''}) is None
        assert w.parse_timeout({'timeout': '0'}) is None
        assert w.parse_timeout({'timeout': 'abc'}) is None
        assert w.parse_timeout({}) is None

    def test_subprocess_backstop(self):
        import tasknet_web as w
        assert w.verify_subprocess_timeout(5) == 35     # solve cap + 30 s grace
        assert w.verify_subprocess_timeout(None) == 300  # default when unbounded


class TestPropertyTimeout:
    """The Phase-2 property-check cap (--property-timeout), distinct from --timeout.

    Bounds the per-property ∀∀ solve (user properties, `final`, compositional AA).
    Default 10 s per property (a no-op unless the flag is set)."""

    def test_check_temporal_properties_accepts_and_defaults(self):
        import inspect
        from tasknet_smt import TaskNetTL
        sig = inspect.signature(TaskNetTL.check_temporal_properties)
        assert 'property_timeout_ms' in sig.parameters
        assert sig.parameters['property_timeout_ms'].default == 10000

    def test_check_compositional_threads_the_cap(self):
        import inspect
        from tasknet_compositional import check_compositional
        sig = inspect.signature(check_compositional)
        assert 'property_timeout_ms' in sig.parameters
        assert sig.parameters['property_timeout_ms'].default == 10000

    def test_main_accepts_property_timeout(self):
        import inspect
        import tasknet_verifier as v
        assert 'property_timeout' in inspect.signature(v.main).parameters

    def test_cli_exposes_flag(self):
        import subprocess
        out = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / 'src' / 'smt' / 'tasknet_verifier.py'),
             '--help'], capture_output=True, text=True).stdout
        assert '--property-timeout' in out

    def test_generous_cap_still_decides_properties(self):
        # A raised cap must not change a normal, fast property outcome: the `final`
        # property of tasknet46 holds, and still holds under a 180 s cap.
        enc = _encode('tasknet46_final_holds.tn')
        results, _violations = enc.check_temporal_properties(property_timeout_ms=180000)
        final = next((r for r in results if r.get('name') == 'final'), None)
        assert final is not None and final['status'] == 'holds'
