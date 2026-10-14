"""
The Phase-1 portfolio race must leave the main Z3 context usable.

Regression: when the untracked racer won, the tracked racer was stopped by
interrupting the main context while its check was running. That damaged the
context, and the property checks that followed in it could return incomplete
models (a required task without start/end values), crashing the counterexample
printout in `extract_schedule`. It happened in about 30% of runs, depending on
which racer won, so the case is repeated.
"""

from .conftest import verify


def test_counterexample_after_portfolio_race():
    for _ in range(10):
        out = verify('tasknet10_verify.tn', mode='satisfy')
        assert "Counterexample:" in out
        assert "Summary: 0 hold, 1 violated, 0 unknown" in out
