"""
Numeric comparisons on state timelines with numeric state names, e.g.
`m : state(0,1,2)` with `m = 2` in a property.

Regression: the encoder used to assert False into the whole solver for such a
comparison, so every property mentioning it was reported to HOLD.
"""

import subprocess
import sys

from .conftest import PROJECT_ROOT, VERIFIER_SCRIPT


TASKNET = '''
tasknet NumericStateCmp {
  end = 50;
  timelines {
    m : state(0,1,2) = 0;
  }
  task t { id 1; duration 5; impacts { pre { m = 1; } post { m = 2; } } }
  properties {
    prop reaches2: eventually (m = 2);
    prop at_most2: always (m <= 2);
    prop never_above2: always not (m > 2);
    prop always0: always (m = 0);
    prop always2: always (m = 2);
  }
}
'''


def _verify(tmp_path, source):
    path = tmp_path / "numeric_state_cmp.tn"
    path.write_text(source)
    result = subprocess.run(
        [sys.executable, VERIFIER_SCRIPT, str(path), '--mode', 'satisfy'],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _verdict(output, prop):
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if f"Checking property '{prop}'" in line:
            return lines[i + 1].strip()
    raise AssertionError(f"no verdict for {prop}:\n{output}")


def test_numeric_state_comparisons(tmp_path):
    out = _verify(tmp_path, TASKNET)
    assert "HOLDS" in _verdict(out, "reaches2")
    assert "HOLDS" in _verdict(out, "at_most2")
    assert "HOLDS" in _verdict(out, "never_above2")
    assert "VIOLATED" in _verdict(out, "always0")
    assert "VIOLATED" in _verdict(out, "always2")
