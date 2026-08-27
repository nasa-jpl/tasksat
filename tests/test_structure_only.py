"""Tests for the parse-only structure render (--structure-only + web /api/structure).

`--structure-only` renders the static structure diagram straight from the
pre-transform AST and exits — no transforms, no well-formedness, no solve. It
writes structure.png into `.tasksat/schedules/<name>/latest/` with a
`structure_only` metadata status, so the web UI can list and display it without
paying for a full verification. The web layer exposes it as /api/structure/<name>.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT / 'src' / 'smt'))

FIXTURE = 'tasknet61_session_containedin.tn'

# dot is needed to actually emit structure.png; the metadata/status is written
# regardless, so gate only the PNG-existence assertions on Graphviz.
from tasknet_structure_viz import check_dot_available  # noqa: E402
HAVE_DOT = check_dot_available()


class TestStructureOnlyCLI:
    """End-to-end via the verifier subprocess."""

    def _run(self, tmp_path, fixture=FIXTURE, extra=None):
        src = PROJECT_ROOT / 'tests' / 'tasknet_files' / 'valid' / fixture
        cmd = [sys.executable, str(PROJECT_ROOT / 'src' / 'smt' / 'tasknet_verifier.py'),
               str(src), '--structure-only']
        if extra:
            cmd.extend(extra)
        return subprocess.run(cmd, cwd=tmp_path, capture_output=True, text=True)

    def test_cli_exposes_flag(self):
        out = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / 'src' / 'smt' / 'tasknet_verifier.py'),
             '--help'], capture_output=True, text=True).stdout
        assert '--structure-only' in out

    def test_does_not_solve(self, tmp_path):
        # Parse-only: it must NOT run the validity solve.
        res = self._run(tmp_path)
        assert res.returncode == 0
        assert 'Valid schedule found' not in res.stdout
        # No schedule artifact is produced (that is a solve output).
        assert not (tmp_path / '.tasksat' / 'schedules' / 'tasknet61_session_containedin'
                    / 'latest' / 'schedule.json').exists()

    def test_metadata_status(self, tmp_path):
        self._run(tmp_path)
        meta = (tmp_path / '.tasksat' / 'schedules' / 'tasknet61_session_containedin'
                / 'latest' / 'metadata.json')
        assert meta.exists()
        assert json.loads(meta.read_text())['status'] == 'structure_only'

    @pytest.mark.skipif(not HAVE_DOT, reason="Graphviz 'dot' not installed")
    def test_writes_structure_png(self, tmp_path):
        self._run(tmp_path)
        png = (tmp_path / '.tasksat' / 'schedules' / 'tasknet61_session_containedin'
               / 'latest' / 'structure.png')
        assert png.exists() and png.stat().st_size > 0

    def test_main_accepts_structure_only(self):
        import inspect
        import tasknet_verifier as v
        assert 'structure_only' in inspect.signature(v.main).parameters


class TestStructureOnlyWebPlumbing:
    """The web command builder and endpoint."""

    def test_verifier_cmd_structure_only(self):
        import tasknet_web as w
        cmd = w.verifier_cmd('x.tn', 'optimize', structure_only=True)
        assert cmd[-1] == '--structure-only'
        # It ignores solve options — no --mode / --timeout noise.
        assert '--mode' not in cmd and '--timeout' not in cmd

    @pytest.mark.skipif(not HAVE_DOT, reason="Graphviz 'dot' not installed")
    def test_api_structure_renders(self):
        import tasknet_web as w
        client = w.app.test_client()
        r = client.post('/api/structure/tasknet61_session_containedin', json={})
        assert r.status_code == 200
        body = r.get_json()
        assert body['status'] == 'success'
        assert body['has_structure'] is True

    def test_api_structure_unknown_tasknet(self):
        import tasknet_web as w
        client = w.app.test_client()
        r = client.post('/api/structure/does_not_exist_xyz', json={})
        assert r.status_code == 404
