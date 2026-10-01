"""The static lint pass (`tasknet_lint`).

Two severities, and the tests are organised around what separates them:

* PROVEN findings quantify over the WHOLE network — "no impact anywhere writes this
  timeline" — so no other task can rescue the situation and there are no false
  positives. The tests therefore pin both directions: it fires when nothing writes
  the timeline, and stays silent as soon as something does.
* ADVISORY findings reason about one taskdef at a time and may be wrong. Only the
  firing direction is a contract; silence is not promised.

Lint must never block a run, so the CLI tests check it reports and carries on.
"""

import subprocess
import sys

import pytest

from .conftest import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT / 'src' / 'smt'))

from tasknet_parser import parse_tasknet          # noqa: E402
from tasknet_transforms import apply_transforms   # noqa: E402
from tasknet_lint import lint, Severity           # noqa: E402


def findings(src: str, rule: str = None):
    tn, _ = apply_transforms(parse_tasknet(src))
    out = lint(tn)
    return [f for f in out if rule is None or f.rule == rule]


def net(timelines: str, body: str) -> str:
    return f"tasknet L {{\n  end = 1000;\n  timelines {{ {timelines} }}\n  {body}\n}}\n"


class TestUnsatisfiableInitial:
    """PROVEN: a timeline no impact writes, whose initial value fails a condition."""

    def test_fires_when_nothing_writes_the_timeline(self):
        f = findings(net("mode : state(off, on) = off;",
                         "taskdef A { duration_range [1, 2]; pre { mode = on; } }\n"
                         "  task a : A;"), 'unsatisfiable-initial')
        assert len(f) == 1
        assert f[0].severity is Severity.PROVEN
        assert "'mode'" in f[0].message and "'off'" in f[0].message

    def test_silent_when_some_task_writes_it(self):
        """The whole-network quantification: one writer anywhere and the proof is off,
        even though this task still cannot supply the value itself."""
        assert findings(net("mode : state(off, on) = off;",
                            "taskdef W { duration_range [1, 2];"
                            " impacts { maint { mode = on; } } }\n"
                            "  taskdef A { duration_range [1, 2]; pre { mode = on; } }\n"
                            "  task w : W;\n  task a : A;"),
                        'unsatisfiable-initial') == []

    def test_silent_when_the_initial_value_satisfies(self):
        """`e_stop` in the MEXEC nets: never written, but initial Off meets every
        constraint on it, so it is a legitimate external input, not a defect."""
        assert findings(net("e_stop : state(Off, On) = Off;",
                            "taskdef A { duration_range [1, 2]; pre { e_stop = Off; } }\n"
                            "  task a : A;"), 'unsatisfiable-initial') == []

    def test_numeric_state_names_still_match(self):
        """`state(0, 1)` has states '0'/'1' as STRINGS while a condition on it parses as
        IntVal(1). Comparing without normalizing never matches, which would miss the
        MEXEC `opsci_enabled` defect this rule exists for."""
        assert findings(net("f : state(0, 1) = 1;",
                            "taskdef A { duration_range [1, 2]; pre { f = 1; } }\n"
                            "  task a : A;"), 'unsatisfiable-initial') == []
        assert len(findings(net("f : state(0, 1) = 0;",
                                "taskdef A { duration_range [1, 2]; pre { f = 1; } }\n"
                                "  task a : A;"), 'unsatisfiable-initial')) == 1

    def test_range_condition_on_a_numeric_timeline(self):
        hit = findings(net("n : cumulative [0, 100] = 5;",
                           "taskdef A { duration_range [1, 2]; pre { n in [20, 30]; } }\n"
                           "  task a : A;"), 'unsatisfiable-initial')
        assert len(hit) == 1
        ok = findings(net("n : cumulative [0, 100] = 25;",
                          "taskdef A { duration_range [1, 2]; pre { n in [20, 30]; } }\n"
                          "  task a : A;"), 'unsatisfiable-initial')
        assert ok == []

    def test_a_disjunction_is_satisfied_by_any_branch(self):
        assert findings(net("h : state(UNKNOWN, HEALTHY, CND) = HEALTHY;",
                            "taskdef A { duration_range [1, 2];"
                            " pre { h in HEALTHY CND; } }\n  task a : A;"),
                        'unsatisfiable-initial') == []

    def test_the_finding_is_consistent_with_the_solver(self):
        """A PROVEN finding claims no schedule exists. Check the solver agrees."""
        src = net("mode : state(off, on) = off;",
                  "taskdef A { duration_range [1, 2]; pre { mode = on; } }\n  task a : A;")
        assert len(findings(src, 'unsatisfiable-initial')) == 1
        from tasknet_smt import TaskNetTL
        tn, _ = apply_transforms(parse_tasknet(src))
        enc = TaskNetTL(tn, error_trace=False, use_optimization=False)
        assert str(enc.solver.check()) == 'unsat'


class TestUnsupportedTransition:
    """ADVISORY: pre and inv disjoint on one timeline, with no impact of its own."""

    def test_fires_on_the_maintainheat_shape(self):
        f = findings(net("r : atomic = 0;",
                         "taskdef MH { duration_range [1, 9]; pre { r = 0; } inv { r = 1; } }\n"
                         "  task mh : MH;"), 'unsupported-transition')
        assert len(f) == 1 and f[0].severity is Severity.ADVISORY

    def test_silent_when_the_task_supplies_it(self):
        assert findings(net("r : atomic = 0;",
                            "taskdef T { duration_range [1, 9]; pre { r = 0; } inv { r = 1; }"
                            " impacts { maint { r += 1; } } }\n  task t : T;"),
                        'unsupported-transition') == []

    def test_disjointness_not_inequality(self):
        """`pre battery_soc = 30` with `inv battery_soc in [20, 100]` differ but need no
        change, since 30 already satisfies the invariant. An inequality test would
        wrongly flag it."""
        assert findings(net("b : cumulative [0, 100] = 30;",
                            "taskdef T { duration_range [1, 9]; pre { b = 30; }"
                            " inv { b in [20, 100]; } }\n  task t : T;"),
                        'unsupported-transition') == []


class TestAdvisorySmells:

    def test_unused_timeline(self):
        f = findings(net("spare : atomic = 0;\n    used : atomic = 0;",
                         "taskdef A { duration_range [1, 2]; pre { used = 0; } }\n"
                         "  task a : A;"), 'unused-timeline')
        assert [x.message.count('spare') for x in f] == [1]

    def test_no_op_impact(self):
        f = findings(net("n : cumulative [0, 100] = 0;",
                         "taskdef A { duration_range [1, 2];"
                         " impacts { maint { n += 0; } } }\n  task a : A;"),
                     'no-op-impact')
        assert len(f) == 1 and f[0].severity is Severity.ADVISORY

    def test_a_real_impact_is_not_flagged(self):
        assert findings(net("n : cumulative [0, 100] = 0;",
                            "taskdef A { duration_range [1, 2];"
                            " impacts { maint { n += 1; } } }\n  task a : A;"),
                        'no-op-impact') == []


class TestCLI:

    SRC = ("tasknet L {\n  end = 1000;\n  timelines { mode : state(off, on) = off; }\n"
           "  taskdef A { duration_range [1, 2]; pre { mode = on; } }\n  task a : A;\n}\n")

    def run(self, tmp_path, *flags):
        p = tmp_path / 'lintme.tn'
        p.write_text(self.SRC)
        return subprocess.run(
            [sys.executable, str(PROJECT_ROOT / 'src' / 'smt' / 'tasknet_verifier.py'),
             str(p), *flags], capture_output=True, text=True, cwd=tmp_path).stdout

    def test_lint_only_reports_and_skips_the_solve(self, tmp_path):
        out = self.run(tmp_path, '--lint-only')
        assert 'proven unschedulable' in out
        assert 'unsatisfiable-initial' in out
        assert 'Exiting without verification' in out
        assert 'Phase 1' not in out

    def test_runs_by_default_and_does_not_block(self, tmp_path):
        """Even a PROVEN finding must leave the solve to proceed: the timeline may be
        set outside the plan, and refusing would stop the modeller looking further."""
        out = self.run(tmp_path)
        assert 'proven unschedulable' in out
        assert 'Phase 1' in out

    def test_no_lint_suppresses_it(self, tmp_path):
        assert 'LINT' not in self.run(tmp_path, '--no-lint')

    def test_silent_when_there_is_nothing_to_say(self, tmp_path):
        """Lint runs on every verification, so a clean network must print no banner —
        otherwise it is noise between the user and their schedule."""
        p = tmp_path / 'clean.tn'
        p.write_text("tasknet C {\n  end = 100;\n  timelines { n : atomic = 0; }\n"
                     "  taskdef A { duration_range [1, 2]; pre { n = 0; }"
                     " impacts { maint { n += 1; } } }\n  task a : A;\n}\n")
        out = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / 'src' / 'smt' / 'tasknet_verifier.py'),
             str(p)], capture_output=True, text=True, cwd=tmp_path).stdout
        assert 'LINT' not in out
        assert 'Phase 1' in out

    def test_lint_only_still_reports_when_clean(self, tmp_path):
        """--lint-only must print SOMETHING when clean: there, the report is the whole
        output, and silence would read as a crash."""
        p = tmp_path / 'clean.tn'
        p.write_text("tasknet C {\n  end = 100;\n  timelines { n : atomic = 0; }\n"
                     "  taskdef A { duration_range [1, 2]; pre { n = 0; }"
                     " impacts { maint { n += 1; } } }\n  task a : A;\n}\n")
        out = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / 'src' / 'smt' / 'tasknet_verifier.py'),
             str(p), '--lint-only'], capture_output=True, text=True, cwd=tmp_path).stdout
        assert 'LINT' in out and 'No findings' in out

    def test_flags_exposed(self):
        out = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / 'src' / 'smt' / 'tasknet_verifier.py'),
             '--help'], capture_output=True, text=True).stdout
        assert '--no-lint' in out and '--lint-only' in out


class TestArtifactAndWebUI:
    """`lint.json` and the Lint card on the verification report."""

    SRC = ("tasknet LintArtifact {\n  end = 1000;\n"
           "  timelines { mode : state(off, on) = off; spare : atomic = 0; }\n"
           "  taskdef A { duration_range [1, 2]; pre { mode = on; } }\n"
           "  task a : A;\n}\n")

    @pytest.fixture
    def run_dir(self, tmp_path):
        """Verify a network with findings. It is UNSAT, which is the path that matters:
        lint explains the UNSAT, and that path returns early from main()."""
        src = tmp_path / 'lintartifact.tn'
        src.write_text(self.SRC)
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / 'src' / 'smt' / 'tasknet_verifier.py'),
             str(src), '--timeout', '20'],
            capture_output=True, text=True, cwd=tmp_path)
        return tmp_path / '.tasksat' / 'schedules' / 'lintartifact' / 'latest'

    def test_lint_json_written_on_the_unsat_path(self, run_dir):
        import json
        f = run_dir / 'lint.json'
        assert f.exists(), "lint.json must survive main()'s early return on UNSAT"
        data = json.loads(f.read_text())
        assert {d['severity'] for d in data} == {'proven', 'advisory'}
        proven = [d for d in data if d['severity'] == 'proven']
        assert [d['rule'] for d in proven] == ['unsatisfiable-initial']

    def test_no_lint_json_when_clean(self, tmp_path):
        """A missing file is how the UI reads 'clean', so it must not be written empty."""
        src = tmp_path / 'cleanrun.tn'
        src.write_text("tasknet C {\n  end = 100;\n  timelines { n : atomic = 0; }\n"
                       "  taskdef A { duration_range [1, 2]; pre { n = 0; }"
                       " impacts { maint { n += 1; } } }\n  task a : A;\n}\n")
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / 'src' / 'smt' / 'tasknet_verifier.py'),
             str(src), '--timeout', '20'], capture_output=True, text=True, cwd=tmp_path)
        d = tmp_path / '.tasksat' / 'schedules' / 'cleanrun' / 'latest'
        assert d.exists() and not (d / 'lint.json').exists()

    def test_report_page_renders_the_lint_card(self, tmp_path, monkeypatch):
        import json
        import tasknet_web as w
        # The web app anchors its paths at the repo root, so point it at a temp tree
        # rather than writing fixtures into the real .tasksat/.
        sched = tmp_path / '.tasksat' / 'schedules' / 'x' / 'latest'
        sched.mkdir(parents=True)
        src = tmp_path / 'x.tn'
        src.write_text(self.SRC)
        (sched / 'metadata.json').write_text(json.dumps({
            'source_path': str(src), 'status': 'unsat', 'timestamp': 'now',
            'duration_sec': 0.1, 'mode': 'optimize'}))
        (sched / 'lint.json').write_text(json.dumps([
            {'severity': 'proven', 'rule': 'unsatisfiable-initial', 'message': 'M-PROVEN'},
            {'severity': 'advisory', 'rule': 'unused-timeline', 'message': 'M-ADVISORY'}]))
        monkeypatch.setattr(w, 'SCHEDULES_DIR', tmp_path / '.tasksat' / 'schedules')

        w.app.config['TESTING'] = True
        html = w.app.test_client().get('/report/x/latest').get_data(as_text=True)
        assert '1 proven' in html and '1 advisory' in html
        assert 'M-PROVEN' in html and 'M-ADVISORY' in html
        # The proven block must come BEFORE the UNSAT core section: it is usually the
        # reason for it, stated in the spec's own terms.
        assert html.index('M-PROVEN') < html.index('UNSAT: No Valid Schedule Found')

    def test_report_page_omits_the_card_when_clean(self, tmp_path, monkeypatch):
        import json
        import tasknet_web as w
        sched = tmp_path / '.tasksat' / 'schedules' / 'y' / 'latest'
        sched.mkdir(parents=True)
        src = tmp_path / 'y.tn'
        src.write_text(self.SRC)
        (sched / 'metadata.json').write_text(json.dumps({
            'source_path': str(src), 'status': 'sat', 'timestamp': 'now',
            'duration_sec': 0.1, 'mode': 'optimize'}))
        monkeypatch.setattr(w, 'SCHEDULES_DIR', tmp_path / '.tasksat' / 'schedules')

        w.app.config['TESTING'] = True
        html = w.app.test_client().get('/report/y/latest').get_data(as_text=True)
        assert 'Proven unschedulable' not in html
