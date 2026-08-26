"""Tests for the LLM advisor loop, driven by a mock proposer (no API key).

The mock stands in for the Anthropic call, so these exercise the full machinery:
proposal -> syntactic gate -> apply-to-copy -> real verifier subprocess -> scoring
-> session/report persistence, plus the copy-only safety guarantee and step-mode
resume. The `anthropic` SDK is never imported.
"""

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "smt"))
import tasknet_advisor as A  # noqa: E402


MINI = """\
tasknet Mini {
  end = 100;
  taskdef a { duration_range [1, 5]; }
  task t1 : a {}
}
"""

# A valid rewrite (adds a second task) — parses and verifies SAT.
IMPROVED = """\
tasknet Mini {
  end = 100;
  taskdef a { duration_range [1, 5]; }
  task t1 : a {}
  task t2 : a { after t1; }
}
"""


# A spec with a shared timeline and an active impact, for fidelity-guard tests.
MINI_TL = """\
tasknet MiniTL {
  end = 100;
  timelines {
    battery : rate [0.0, 100.0] bounds [0.0, 100.0] initial_rate = 0.0;
  }
  taskdef a {
    duration_range [1, 5];
    impacts { maint { battery +~ -0.5; } }
  }
  task t1 : a {}
}
"""

# Cheat 1: keep taskdef `a` by name but zero its impact on battery.
CHEAT_ZERO = MINI_TL.replace("battery +~ -0.5;", "battery +~ 0.0;")

# Cheat 2: drop the battery timeline (and its impact) entirely.
CHEAT_DROP = """\
tasknet MiniTL {
  end = 100;
  taskdef a { duration_range [1, 5]; }
  task t1 : a {}
}
"""

# Cheat 3: demote the required `t1` to a request task (a is no longer required-live).
CHEAT_DEMOTE = MINI_TL.replace("task t1 : a {}", "request task t1 : a {}")


def test_check_fidelity_accepts_identity_and_faithful():
    ok, err = A.check_fidelity(MINI_TL, MINI_TL)
    assert ok and err is None
    # Strengthening the drain is a faithful change (impact still active).
    stronger = MINI_TL.replace("battery +~ -0.5;", "battery +~ -0.9;")
    ok, err = A.check_fidelity(MINI_TL, stronger)
    assert ok and err is None


def test_check_fidelity_rejects_neutralized_impact():
    ok, err = A.check_fidelity(MINI_TL, CHEAT_ZERO)
    assert not ok
    assert "no longer actively impacts" in err and "battery" in err


def test_check_fidelity_rejects_dropped_timeline():
    ok, err = A.check_fidelity(MINI_TL, CHEAT_DROP)
    assert not ok
    assert "dropped timeline" in err and "battery" in err


def test_check_fidelity_rejects_demoted_required_task():
    ok, err = A.check_fidelity(MINI_TL, CHEAT_DEMOTE)
    assert not ok
    assert "demoted" in err and "a" in err


def test_fidelity_guard_rejects_then_feeds_back(tmp_path):
    src = tmp_path / "minitl.tn"
    src.write_text(MINI_TL, encoding="utf-8")
    # First proposal cheats (zeroes the impact); second is faithful.
    proposer = _proposer((CHEAT_ZERO, "cheat: zero the drain"),
                         (MINI_TL, "faithful: keep the drain"))
    session = A.advise(str(src), goal="make it compositional", mode="loop",
                       max_iters=3, budget=120, out_dir=str(tmp_path / "run"),
                       proposer=proposer, timeout=60)

    first = session["history"][0]
    assert first["valid"] is False
    assert first.get("fidelity_error") and "battery" in first["fidelity_error"]
    assert first["diagnostics"] is None  # rejected before any solve
    # The faithful follow-up was applied and verified.
    verified = [h for h in session["history"] if h.get("diagnostics")]
    assert verified and verified[0]["valid"] is True


def test_fidelity_guard_can_be_disabled(tmp_path):
    src = tmp_path / "minitl.tn"
    src.write_text(MINI_TL, encoding="utf-8")
    session = A.advise(str(src), goal="whatever", mode="step",
                       out_dir=str(tmp_path / "run"),
                       proposer=_proposer((CHEAT_ZERO, "cheat allowed")),
                       timeout=60, fidelity_guard=False)
    # With the guard off, the cheat is applied and verified (no fidelity_error).
    h = session["history"][0]
    assert h.get("fidelity_error") is None
    assert h["valid"] is True and h["diagnostics"] is not None


def _proposer(*rewrites):
    """Build a mock proposer that yields the given (tn, rationale) pairs in order."""
    seq = list(rewrites)
    calls = {"n": 0}

    def proposer(source, diagnostics, reference, goal, history, model):
        i = min(calls["n"], len(seq) - 1)
        calls["n"] += 1
        tn, rationale = seq[i]
        return {"tn": tn, "rationale": rationale}

    proposer.calls = calls
    return proposer


def _write_mini(tmp_path):
    src = tmp_path / "mini.tn"
    src.write_text(MINI, encoding="utf-8")
    return src


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_module_imports_without_anthropic():
    # Importing the module must not require the SDK; the lazy import lives inside
    # propose_rewrite and is never hit when a mock proposer is supplied.
    assert "anthropic" not in sys.modules
    assert callable(A.advise) and callable(A.advise_once)


def test_validate_rewrite_gate():
    ok, err = A.validate_rewrite(MINI)
    assert ok and err is None
    ok, err = A.validate_rewrite("not a tasknet }{")
    assert not ok and err
    ok, err = A.validate_rewrite("")
    assert not ok


def test_step_mode_runs_one_iteration(tmp_path):
    src = _write_mini(tmp_path)
    before = _sha(src)
    session = A.advise(str(src), goal="make it a bit bigger", mode="step",
                       out_dir=str(tmp_path / "run"),
                       proposer=_proposer((IMPROVED, "add a dependent task")),
                       timeout=60)

    # Exactly one iteration, and it was applied + verified.
    verified = [h for h in session["history"] if h.get("diagnostics")]
    assert len(verified) == 1
    assert session["history"][0]["valid"] is True
    assert session["best"] is not None
    assert session["stop_reason"] == "step"

    # Artifacts written; original untouched.
    run = Path(session["workdir"])
    assert (run / "session.json").exists()
    assert (run / "report.json").exists()
    assert (run / "report.md").exists()
    assert Path(session["history"][0]["attempt_path"]).exists()
    assert _sha(src) == before


def test_invalid_proposal_is_caught_then_valid_applied(tmp_path):
    src = _write_mini(tmp_path)
    proposer = _proposer(("this is not valid tasknet }{", "bad attempt"),
                         (IMPROVED, "good attempt"))
    session = A.advise(str(src), goal="improve", mode="loop", max_iters=3, budget=120,
                       out_dir=str(tmp_path / "run"), proposer=proposer, timeout=60)

    # First iteration rejected at the syntactic gate (no verify), second applied.
    assert session["history"][0]["valid"] is False
    assert session["history"][0]["parse_error"]
    assert session["history"][0]["diagnostics"] is None
    valid = [h for h in session["history"] if h.get("valid")]
    assert valid and valid[0]["diagnostics"] is not None
    assert session["best"]["diagnostics"]["status"] in ("success", "violated")


def test_original_never_modified(tmp_path):
    src = _write_mini(tmp_path)
    before = _sha(src)
    A.advise(str(src), goal="improve", mode="loop", max_iters=2, budget=120,
             out_dir=str(tmp_path / "run"),
             proposer=_proposer((IMPROVED, "change")), timeout=60)
    assert _sha(src) == before


def test_step_then_continue_with_feedback(tmp_path):
    src = _write_mini(tmp_path)
    run = tmp_path / "run"
    A.advise(str(src), goal="improve", mode="step", out_dir=str(run),
             proposer=_proposer((IMPROVED, "first")), timeout=60)

    session_path = run / "session.json"
    assert session_path.exists()

    session2 = A.advise(str(src), goal="improve", mode="step",
                        resume=str(session_path), feedback="prefer fewer tasks",
                        proposer=_proposer((MINI, "second, simpler")), timeout=60)

    # Feedback recorded, and a second real iteration ran after it.
    assert "prefer fewer tasks" in session2.get("feedback", [])
    assert any(h.get("note") == "feedback" for h in session2["history"])
    verified = [h for h in session2["history"] if h.get("diagnostics")]
    assert len(verified) == 2


def test_accept_copies_best_without_touching_original(tmp_path):
    src = _write_mini(tmp_path)
    before = _sha(src)
    run = tmp_path / "run"
    A.advise(str(src), goal="improve", mode="step", out_dir=str(run),
             proposer=_proposer((IMPROVED, "one")), timeout=60)

    out = tmp_path / "accepted.tn"
    A.accept(str(run / "session.json"), str(out))
    assert out.exists()
    assert out.read_text() == IMPROVED
    assert _sha(src) == before  # original still untouched
