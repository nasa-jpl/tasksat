#!/usr/bin/env python3
"""
TaskSAT Web Interface - Browse tasknets, schedules, and timeline visualizations.

Usage:
    python src/smt/tasknet_web.py
    # Opens browser to http://localhost:5000
"""

from flask import Flask, render_template, send_from_directory, jsonify, request
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import webbrowser
import threading

app = Flask(__name__)

# Configure paths
TASKSAT_ROOT = Path(__file__).parent.parent.parent
SCHEDULES_DIR = TASKSAT_ROOT / '.tasksat' / 'schedules'
ERRORS_DIR = TASKSAT_ROOT / '.tasksat' / 'errors'
ADVISOR_DIR = TASKSAT_ROOT / '.tasksat' / 'advisor'
TESTS_DIR = TASKSAT_ROOT / 'tests' / 'tasknet_files'

# Registry of in-flight verification subprocesses, keyed by a client-supplied
# task id, so /api/kill can cancel a run while its (blocking) request is still
# open. Guarded by a lock because Flask serves requests on multiple threads.
RUNNING_TASKS = {}
RUNNING_TASKS_LOCK = threading.Lock()


def verifier_cmd(tn_path, mode, realizability=False, compositional=False,
                 unsat_core=True, timeout=None):
    """Build the tasknet_verifier.py command line."""
    # sys.executable, not 'python': the latter is absent on systems that ship
    # only 'python3', and it would ignore the interpreter this server runs under.
    cmd = [sys.executable, str(TASKSAT_ROOT / 'src' / 'smt' / 'tasknet_verifier.py'),
           str(tn_path), '--mode', mode]
    if realizability:
        cmd.append('--realizability')
    if compositional:
        cmd.append('--compositional')
    if not unsat_core:
        cmd.append('--no-unsat-core')
    if timeout and timeout > 0:
        cmd.extend(['--timeout', str(timeout)])
    return cmd


def parse_timeout(data):
    """Read an optional Phase-1 solve timeout (seconds) from a request body.

    Returns a positive float, or None for 'no limit' (blank/missing/invalid/<=0).
    """
    timeout = data.get('timeout')
    try:
        timeout = float(timeout) if timeout not in (None, '') else None
    except (TypeError, ValueError):
        timeout = None
    return timeout if (timeout is not None and timeout > 0) else None


def verify_subprocess_timeout(timeout):
    """Wall-clock backstop for the verifier subprocess: the solve timeout plus a
    grace margin, or the 300 s default when no solve timeout is set."""
    return (timeout + 30) if timeout else 300


def run_verifier(cmd, task_id=None, timeout=300):
    """Run the verifier as a tracked subprocess so it can be cancelled.

    Registers the process under ``task_id`` (if given) for the duration of the
    run, then returns a dict describing how it ended:

        outcome    'completed' | 'timeout' | 'killed'
        stdout     captured stdout (str)
        stderr     captured stderr (str)
        returncode process exit code (negative if terminated by signal)
        duration   wall-clock seconds

    'killed' is inferred from termination by signal (e.g. /api/kill calling
    terminate()/kill()); 'timeout' takes precedence when we hit the deadline.
    """
    start = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    if task_id:
        with RUNNING_TASKS_LOCK:
            RUNNING_TASKS[task_id] = proc

    outcome = 'completed'
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        outcome = 'timeout'
    finally:
        if task_id:
            with RUNNING_TASKS_LOCK:
                RUNNING_TASKS.pop(task_id, None)

    # A negative returncode means the process was terminated by a signal, which
    # (outside the timeout path) is how a /api/kill cancellation manifests.
    if outcome == 'completed' and proc.returncode is not None and proc.returncode < 0:
        outcome = 'killed'

    return {
        'outcome': outcome,
        'stdout': stdout or '',
        'stderr': stderr or '',
        'returncode': proc.returncode,
        'duration': time.time() - start,
    }


@app.route('/api/kill', methods=['POST'])
def api_kill():
    """Cancel an in-flight verification by its client-supplied task id."""
    data = request.get_json(silent=True) or {}
    task_id = data.get('task_id')
    if not task_id:
        return jsonify({'status': 'error', 'message': 'task_id is required'}), 400

    with RUNNING_TASKS_LOCK:
        proc = RUNNING_TASKS.get(task_id)

    if proc is None:
        return jsonify({'status': 'not_found',
                        'message': 'No running task with that id'}), 404

    try:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()  # escalate if it ignored SIGTERM
        return jsonify({'status': 'success', 'message': 'Task cancelled'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/')
def index():
    """Home page - list verified tasknets only."""
    tasknets = []

    # List all verified tasknets (folders in .tasksat/schedules/)
    if SCHEDULES_DIR.exists():
        for folder in SCHEDULES_DIR.iterdir():
            if folder.is_dir() and (folder / 'latest').exists():
                latest_dir = folder / 'latest'
                metadata_file = latest_dir / 'metadata.json'
                properties_file = latest_dir / 'properties.json'

                # Read metadata to get source path, status, and timestamp
                source_path = "unknown"
                status = "success"
                timestamp = None
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        source_path = metadata.get('source_path', 'unknown')
                        status = metadata.get('status', 'success')
                        timestamp = metadata.get('timestamp')

                # Check property status
                has_violations = False
                if properties_file.exists():
                    with open(properties_file, 'r') as f:
                        properties = json.load(f)
                        has_violations = any(p.get('status') == 'violated' for p in properties)

                tasknets.append({
                    'name': folder.name,
                    'path': source_path,
                    'has_schedule': (latest_dir / 'schedule.json').exists(),
                    'has_timeline': (latest_dir / 'timeline.json').exists(),
                    'has_violations': has_violations,
                    'status': status,  # 'success', 'unsat', 'error', or 'not_verified'
                    'timestamp': timestamp
                })

    # Sort by timestamp (most recent first), fallback to name if no timestamp
    tasknets.sort(key=lambda x: (x['timestamp'] or '0'), reverse=True)

    return render_template('index.html', tasknets=tasknets)


@app.route('/tasknet/<name>')
def tasknet_detail(name):
    """Detail page for a specific tasknet."""
    # Find the tasknet file
    tn_file = None
    for candidate in [
        TASKSAT_ROOT / f"{name}.tn",
        TESTS_DIR / 'valid' / f"{name}.tn"
    ]:
        if candidate.exists():
            tn_file = candidate
            break

    if not tn_file:
        return "TaskNet not found", 404

    # Read tasknet source with line numbers
    with open(tn_file, 'r') as f:
        source_lines = f.readlines()

    # Add line numbers (right-aligned, with padding)
    max_line_num = len(source_lines)
    line_num_width = len(str(max_line_num))
    source = ''.join(f"{i+1:>{line_num_width}}  {line}" for i, line in enumerate(source_lines))

    # Check for schedule data in new folder structure
    latest_dir = SCHEDULES_DIR / name / 'latest'
    schedule_file = latest_dir / 'schedule.json'
    timeline_file = latest_dir / 'timeline.json'
    gantt_file = latest_dir / 'gantt.png'
    timeline_viz_file = latest_dir / 'timeline.png'
    structure_file = latest_dir / 'structure.png'

    schedule_data = None
    timeline_data = None

    if schedule_file.exists():
        with open(schedule_file, 'r') as f:
            schedule_data = json.load(f)

    if timeline_file.exists():
        with open(timeline_file, 'r') as f:
            timeline_data = json.load(f)

    # Check for error traces in latest directory
    errors = []
    errors_dir = latest_dir / 'errors'
    if errors_dir.exists():
        for error_file in errors_dir.glob("*_timeline.png"):
            prop_name = error_file.stem.replace("_timeline", "")
            errors.append({
                'property': prop_name,
                'image': error_file.name,
                'schedule': f"{prop_name}_schedule.json",
                'timeline': f"{prop_name}_timeline.json"
            })

    return render_template(
        'tasknet_detail.html',
        name=name,
        source=source,
        schedule=schedule_data,
        timeline=timeline_data,
        has_gantt=gantt_file.exists(),
        has_timeline_viz=timeline_viz_file.exists(),
        has_structure=structure_file.exists(),
        errors=errors,
        advisor_sessions=_advisor_timestamps(name)
    )


@app.route('/static/schedules/<path:filename>')
def serve_schedule(filename):
    """Serve schedule visualization files."""
    return send_from_directory(SCHEDULES_DIR, filename)


def _find_tasknet_file(name):
    """Resolve a tasknet name to its source .tn path (metadata first, then dirs)."""
    metadata_file = SCHEDULES_DIR / name / 'latest' / 'metadata.json'
    if metadata_file.exists():
        try:
            with open(metadata_file, 'r') as f:
                src = Path(json.load(f).get('source_path', ''))
            if src.exists():
                return src
        except (OSError, ValueError):
            pass
    for candidate in [TASKSAT_ROOT / f"{name}.tn", TESTS_DIR / 'valid' / f"{name}.tn"]:
        if candidate.exists():
            return candidate
    return None


def _advisor_timestamps(name):
    """All advisor-run timestamps for a tasknet, newest first."""
    base = ADVISOR_DIR / name
    if not base.exists():
        return []
    return sorted((d.name for d in base.iterdir()
                   if d.is_dir() and (d / 'report.json').exists()), reverse=True)


def _find_genai_api_dir():
    """Locate a JPL genai_api install (env override, then common spots)."""
    env = os.environ.get('GENAI_API_PATH')
    cands = ([Path(env)] if env else []) + [
        Path.home() / 'Desktop' / 'genai_api', Path.home() / 'genai_api']
    for d in cands:
        if (d / 'pyproject.toml').exists():
            return d
    return None


def _refresh_gov_credentials():
    """If a JPL genai_api install is present (and no static API key is set), mint a
    fresh Bearer token and derive the gateway base URL from its config. Gov tokens
    are short-lived, so this runs before each advisor call. No-op otherwise, so the
    server still works against the public API or a pre-set ANTHROPIC_AUTH_TOKEN."""
    if os.environ.get('ANTHROPIC_API_KEY'):
        return
    d = _find_genai_api_dir()
    if not d:
        return
    try:
        tok = subprocess.run(['uv', 'run', 'genai_api', 'token'], cwd=str(d),
                             capture_output=True, text=True, timeout=60)
        token = (tok.stdout or '').strip().split('\n')[0].strip()
        if tok.returncode == 0 and token:
            os.environ['ANTHROPIC_AUTH_TOKEN'] = token
        if not os.environ.get('ANTHROPIC_BASE_URL'):
            cfg = subprocess.run(
                ['uv', 'run', 'python3', '-c',
                 'from genai_api.login.config import get_user_base_url, '
                 'get_user_subscription_id as s; print(get_user_base_url()); print(s())'],
                cwd=str(d), capture_output=True, text=True, timeout=60)
            lines = [x for x in (cfg.stdout or '').strip().split('\n') if x.strip()]
            if cfg.returncode == 0 and len(lines) >= 2:
                os.environ['ANTHROPIC_BASE_URL'] = f'{lines[-2]}/sub-id-{lines[-1]}'
    except Exception:
        pass  # fall through: the credential check / SDK reports any real problem


@app.route('/api/advise/<name>', methods=['POST'])
def api_advise(name):
    """Run the LLM advisor on a tasknet (one step, or a bounded loop).

    Mirrors api_verify: synchronous, cancellable via /api/kill (the in-flight
    verifier subprocess is registered under task_id). Body: mode, goal,
    compositional, feedback, session (timestamp to resume), max_iters, task_id.
    """
    import tasknet_advisor as advisor  # lazy: server starts even without the SDK

    data = request.get_json(silent=True) or {}
    mode = data.get('mode', 'step')
    goal = data.get('goal') or ('Reduce verification time while preserving intent; '
                                'where sound, restructure into a uniform session with '
                                '`invariant compositional { P }` for N-independence.')
    verify_flags = ['--compositional'] if data.get('compositional') else []
    feedback = data.get('feedback')
    resume_ts = data.get('session')
    task_id = data.get('task_id')
    max_iters = int(data.get('max_iters', 5))
    # Model is env-overridable so the same server works against the public API
    # (claude-opus-4-8) or a gateway that needs a prefixed id (us-gov.anthropic...).
    model = os.environ.get('ANTHROPIC_MODEL') or advisor.DEFAULT_MODEL

    # Mint a fresh gov token if a genai_api install is available (no-op otherwise).
    _refresh_gov_credentials()

    # Accept either credential style: x-api-key (ANTHROPIC_API_KEY) or a Bearer
    # token (ANTHROPIC_AUTH_TOKEN, e.g. an SSO gateway).
    if not (os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_AUTH_TOKEN')):
        return jsonify({'status': 'error',
                        'message': 'No Anthropic credential on the server '
                        '(set ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN).'}), 400

    resume_path = None
    if resume_ts:
        resume_path = ADVISOR_DIR / name / resume_ts / 'session.json'
        if not resume_path.exists():
            return jsonify({'status': 'error', 'message': 'Session not found'}), 404

    tn_file = _find_tasknet_file(name)
    if not tn_file and not resume_path:
        return jsonify({'status': 'error', 'message': 'TaskNet file not found'}), 404

    reg = {'task_id': task_id, 'running_tasks': RUNNING_TASKS,
           'running_lock': RUNNING_TASKS_LOCK}
    try:
        session = advisor.advise(
            str(tn_file) if tn_file else None, goal, mode=mode, max_iters=max_iters,
            verify_flags=verify_flags, resume=str(resume_path) if resume_path else None,
            feedback=feedback, reg=reg, model=model)
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Advisor error: {e}'}), 500

    return jsonify({'status': 'success',
                    'timestamp': session['timestamp'],
                    'report_url': f"/advisor/{name}/{session['timestamp']}"})


@app.route('/advisor/<name>')
@app.route('/advisor/<name>/<timestamp>')
def advisor_report(name, timestamp='latest'):
    """Render an advisor session (the Claude conversation) for a tasknet."""
    timestamps = _advisor_timestamps(name)
    if not timestamps:
        return "No advisor sessions for this tasknet", 404
    if timestamp == 'latest':
        timestamp = timestamps[0]

    report_file = ADVISOR_DIR / name / timestamp / 'report.json'
    report = None
    if report_file.exists():
        with open(report_file, 'r') as f:
            report = json.load(f)
    if report is None:
        return "Advisor report not found", 404

    return render_template('advisor_report.html', name=name, timestamp=timestamp,
                           report=report, timestamps=timestamps)


@app.route('/static/advisor/<path:filename>')
def serve_advisor_file(filename):
    """Serve advisor artifacts (attempt .tn files, reports)."""
    return send_from_directory(ADVISOR_DIR, filename)


@app.route('/static/report/<name>/<timestamp>/<filename>')
def serve_report_file(name, timestamp, filename):
    """Serve files from verification report directories."""
    report_dir = SCHEDULES_DIR / name / timestamp
    response = send_from_directory(report_dir, filename)
    # Prevent caching of images to ensure latest visualizations are shown
    if filename.endswith('.png'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


@app.route('/static/report/<name>/<timestamp>/errors/<filename>')
def serve_report_error_file(name, timestamp, filename):
    """Serve error trace files from verification report directories."""
    errors_dir = SCHEDULES_DIR / name / timestamp / 'errors'
    return send_from_directory(errors_dir, filename)


@app.route('/static/errors/<path:filename>')
def serve_error(filename):
    """Serve error trace files (legacy - for backward compatibility)."""
    return send_from_directory(ERRORS_DIR, filename)


@app.route('/report/<name>')
@app.route('/report/<name>/<timestamp>')
def verification_report(name, timestamp='latest'):
    """Verification report view - single page with code, schedule, and timelines."""
    # Load from timestamped folder
    report_dir = SCHEDULES_DIR / name / timestamp

    if not report_dir.exists():
        return f"Verification report not found: {name}/{timestamp}", 404

    # Load metadata
    metadata_file = report_dir / 'metadata.json'
    if not metadata_file.exists():
        return "Metadata not found", 404

    with open(metadata_file, 'r') as f:
        metadata = json.load(f)

    # Load source code
    source_path = Path(metadata['source_path'])
    if not source_path.exists():
        return f"Source file not found: {source_path}", 404

    with open(source_path, 'r') as f:
        source_lines = f.readlines()

    # Original source (for editing)
    source_original = ''.join(source_lines)

    # Source with line numbers (for display)
    max_line_num = len(source_lines)
    line_num_width = len(str(max_line_num))
    source_display = ''.join(f"{i+1:>{line_num_width}}  {line}" for i, line in enumerate(source_lines))

    # Load schedule and timeline data
    schedule_file = report_dir / 'schedule.json'
    timeline_file = report_dir / 'timeline.json'
    properties_file = report_dir / 'properties.json'
    unsat_core_file = report_dir / 'unsat_core.json'

    schedule_data = None
    timeline_data = None
    properties_data = None
    unsat_core_data = None

    if schedule_file.exists():
        with open(schedule_file, 'r') as f:
            schedule_data = json.load(f)

    if timeline_file.exists():
        with open(timeline_file, 'r') as f:
            timeline_data = json.load(f)

    if properties_file.exists():
        with open(properties_file, 'r') as f:
            properties_data = json.load(f)

    if unsat_core_file.exists():
        with open(unsat_core_file, 'r') as f:
            unsat_core_data = json.load(f)

    # Check for visualization files
    has_gantt = (report_dir / 'gantt.png').exists()
    has_timeline_viz = (report_dir / 'timeline.png').exists()
    has_structure = (report_dir / 'structure.png').exists()
    has_temporal = (report_dir / 'temporal.png').exists()

    # Check for error traces in this verification run's errors directory
    errors = []
    errors_dir = report_dir / 'errors'
    if errors_dir.exists():
        for error_file in errors_dir.glob("*_timeline.png"):
            prop_name = error_file.stem.replace("_timeline", "")
            errors.append({
                'property': prop_name,
                'image': error_file.name,
                'schedule': f"{prop_name}_schedule.json",
                'timeline': f"{prop_name}_timeline.json"
            })

    # Get list of all tasknets for prev/next navigation
    tasknets_with_schedules = []
    if TESTS_DIR.exists():
        for tn_file in sorted((TESTS_DIR / 'valid').glob('*.tn')):
            if (SCHEDULES_DIR / tn_file.stem / 'latest').exists():
                tasknets_with_schedules.append(tn_file.stem)

    # Add tasknets from root directory
    for tn_file in sorted(TASKSAT_ROOT.glob('*.tn')):
        if (SCHEDULES_DIR / tn_file.stem / 'latest').exists():
            if tn_file.stem not in tasknets_with_schedules:
                tasknets_with_schedules.append(tn_file.stem)

    # Find prev/next
    prev_tasknet = None
    next_tasknet = None
    if name in tasknets_with_schedules:
        idx = tasknets_with_schedules.index(name)
        if idx > 0:
            prev_tasknet = tasknets_with_schedules[idx - 1]
        if idx < len(tasknets_with_schedules) - 1:
            next_tasknet = tasknets_with_schedules[idx + 1]

    return render_template(
        'verification_report.html',
        name=name,
        timestamp=timestamp,
        source=source_display,
        source_original=source_original,
        schedule=schedule_data,
        timeline=timeline_data,
        properties=properties_data,
        unsat_core=unsat_core_data,
        has_gantt=has_gantt,
        has_timeline_viz=has_timeline_viz,
        has_structure=has_structure,
        has_temporal=has_temporal,
        metadata=metadata,
        prev_tasknet=prev_tasknet,
        next_tasknet=next_tasknet,
        errors=errors
    )


@app.route('/api/verify/<name>', methods=['POST'])
def api_verify(name):
    """API endpoint to run verification on a tasknet."""
    # Get mode from request (default: optimize)
    data = request.get_json() if request.is_json else {}
    mode = data.get('mode', 'optimize')
    realizability = bool(data.get('realizability', False))
    compositional = bool(data.get('compositional', False))
    unsat_core = bool(data.get('unsat_core', True))
    task_id = data.get('task_id')

    # Optional Phase-1 solve timeout (seconds). Passed to the verifier as
    # --timeout (a clean, status-recording Z3 cap); the subprocess wall-clock
    # is set a little higher as a hard backstop for any other hang.
    timeout = parse_timeout(data)

    if mode not in ['optimize', 'satisfy']:
        return jsonify({'status': 'error', 'message': 'Invalid mode. Use "optimize" or "satisfy"'}), 400

    # Find the tasknet file - first check metadata for the real path
    tn_file = None

    # Check if we have metadata with the source path
    latest_dir = SCHEDULES_DIR / name / 'latest'
    metadata_file = latest_dir / 'metadata.json'

    if metadata_file.exists():
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        source_path = Path(metadata.get('source_path', ''))
        if source_path.exists():
            tn_file = source_path

    # Fallback to searching common locations if metadata doesn't exist
    if not tn_file:
        for candidate in [
            TASKSAT_ROOT / f"{name}.tn",
            TESTS_DIR / 'valid' / f"{name}.tn"
        ]:
            if candidate.exists():
                tn_file = candidate
                break

    if not tn_file:
        return jsonify({'status': 'error', 'message': 'TaskNet file not found'}), 404

    # Run verifier with mode
    try:
        result = run_verifier(
            verifier_cmd(tn_file, mode, realizability, compositional, unsat_core,
                         timeout=timeout),
            task_id=task_id,
            timeout=verify_subprocess_timeout(timeout)
        )
        duration = result['duration']

        if result['outcome'] == 'killed':
            return jsonify({
                'status': 'cancelled',
                'message': 'Verification cancelled',
                'duration': round(duration, 2)
            }), 499

        if result['outcome'] == 'timeout':
            return jsonify({
                'status': 'timeout',
                'message': 'Verification timed out after 5 minutes'
            }), 408

        if result['returncode'] == 0:
            # Check metadata to determine the actual verification result
            latest_dir = SCHEDULES_DIR / name / 'latest'
            metadata_file = latest_dir / 'metadata.json'

            verification_status = 'success'
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                verification_status = metadata.get('status', 'success')

            return jsonify({
                'status': 'success',
                'verification_status': verification_status,
                'message': 'Verification completed',
                'output': result['stdout'],
                'duration': round(duration, 2)
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Verification failed',
                'output': result['stdout'] + '\n' + result['stderr'],
                'duration': round(duration, 2)
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error running verification: {str(e)}'
        }), 500


@app.route('/api/create', methods=['POST'])
def api_create():
    """API endpoint to create a new tasknet file and verify it."""
    try:
        data = request.get_json()
        name = data.get('name', '')
        folder = data.get('folder', '')
        source = data.get('source', '')
        mode = data.get('mode', 'optimize')
        realizability = bool(data.get('realizability', False))
        compositional = bool(data.get('compositional', False))
        unsat_core = bool(data.get('unsat_core', True))
        timeout = parse_timeout(data)
        task_id = data.get('task_id')

        if not name:
            return jsonify({'status': 'error', 'message': 'Filename is required'}), 400

        # Validate filename
        if not name.replace('_', '').replace('-', '').isalnum():
            return jsonify({'status': 'error', 'message': 'Invalid filename'}), 400

        # Determine the full path
        if folder:
            # Use specified folder
            target_dir = TASKSAT_ROOT / folder
        else:
            # Use tests/tasknet_files/valid as default
            target_dir = TASKSAT_ROOT / 'tests' / 'tasknet_files' / 'valid'

        # Create directory if it doesn't exist
        target_dir.mkdir(parents=True, exist_ok=True)

        file_path = target_dir / f"{name}.tn"

        # Check if file already exists
        if file_path.exists():
            return jsonify({'status': 'error', 'message': f'File {name}.tn already exists'}), 400

        # Write the source to file
        with open(file_path, 'w') as f:
            f.write(source)

        # Run verification
        result = run_verifier(
            verifier_cmd(file_path, mode, realizability, compositional, unsat_core,
                         timeout=timeout),
            timeout=verify_subprocess_timeout(timeout),
            task_id=task_id
        )
        duration = result['duration']

        if result['outcome'] == 'killed':
            return jsonify({
                'status': 'cancelled',
                'message': f'Created {name}.tn; verification cancelled',
                'tasknet_name': name,
                'duration': round(duration, 2)
            }), 499

        if result['outcome'] == 'timeout':
            return jsonify({'status': 'timeout', 'message': 'Verification timed out'}), 408

        if result['returncode'] == 0:
            # Check metadata to determine the actual verification result
            latest_dir = SCHEDULES_DIR / name / 'latest'
            metadata_file = latest_dir / 'metadata.json'

            verification_status = 'success'
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                verification_status = metadata.get('status', 'success')

            return jsonify({
                'status': 'success',
                'verification_status': verification_status,
                'message': f'Created and verified {name}.tn',
                'tasknet_name': name,
                'duration': round(duration, 2)
            })
        else:
            # File was created but verification failed
            return jsonify({
                'status': 'error',
                'message': 'File created but verification failed',
                'output': result['stdout'] + '\n' + result['stderr']
            })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/notes/<name>/<timestamp>', methods=['POST'])
def api_save_notes(name, timestamp):
    """API endpoint to save notes for a verification run."""
    try:
        data = request.get_json()
        notes = data.get('notes', '')

        # Update metadata.json in both timestamped folder and latest
        report_dir = SCHEDULES_DIR / name / timestamp
        latest_dir = SCHEDULES_DIR / name / 'latest'

        for dir_path in [report_dir, latest_dir]:
            metadata_file = dir_path / 'metadata.json'
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                metadata['notes'] = notes

                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2)

        return jsonify({
            'status': 'success',
            'message': 'Notes saved successfully'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to save notes: {str(e)}'
        }), 500


@app.route('/api/save-source/<name>', methods=['POST'])
def api_save_source(name):
    """API endpoint to save edited source without verification."""
    try:
        data = request.get_json()
        source = data.get('source', '')

        # Find original source file
        latest_dir = SCHEDULES_DIR / name / 'latest'
        metadata_file = latest_dir / 'metadata.json'

        if not metadata_file.exists():
            return jsonify({'status': 'error', 'message': 'Metadata not found'}), 404

        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        source_path = Path(metadata['source_path'])

        # Save the edited source back to the original file
        with open(source_path, 'w') as f:
            f.write(source)

        return jsonify({
            'status': 'success',
            'message': 'Source saved successfully'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/save-and-verify/<name>', methods=['POST'])
def api_save_and_verify(name):
    """API endpoint to save edited source and re-verify."""
    try:
        data = request.get_json()
        source = data.get('source', '')
        mode = data.get('mode', 'optimize')
        realizability = bool(data.get('realizability', False))
        compositional = bool(data.get('compositional', False))
        unsat_core = bool(data.get('unsat_core', True))
        timeout = parse_timeout(data)
        task_id = data.get('task_id')

        # Find original source file
        latest_dir = SCHEDULES_DIR / name / 'latest'
        metadata_file = latest_dir / 'metadata.json'

        if not metadata_file.exists():
            return jsonify({'status': 'error', 'message': 'Metadata not found'}), 404

        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        source_path = Path(metadata['source_path'])

        # Save the edited source back to the original file
        with open(source_path, 'w') as f:
            f.write(source)

        # Run verification
        result = run_verifier(
            verifier_cmd(source_path, mode, realizability, compositional, unsat_core,
                         timeout=timeout),
            task_id=task_id,
            timeout=verify_subprocess_timeout(timeout)
        )
        duration = result['duration']

        if result['outcome'] == 'killed':
            return jsonify({
                'status': 'cancelled',
                'message': 'Source saved; verification cancelled',
                'duration': round(duration, 2)
            }), 499

        if result['outcome'] == 'timeout':
            return jsonify({'status': 'timeout', 'message': 'Verification timed out'}), 408

        if result['returncode'] == 0:
            return jsonify({
                'status': 'success',
                'message': 'Source saved and verification completed',
                'duration': round(duration, 2)
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Verification failed',
                'output': result['stdout'] + '\n' + result['stderr']
            })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/delete-all', methods=['POST'])
def api_delete_all():
    """API endpoint to delete ALL verification reports.

    IMPORTANT: This route must be defined BEFORE /api/delete/<name>
    to prevent Flask from matching 'all' as a tasknet name.
    """
    import shutil

    if not SCHEDULES_DIR.exists():
        return jsonify({
            'status': 'success',
            'count': 0,
            'message': 'No reports to delete'
        })

    try:
        # Count how many reports exist
        count = sum(1 for folder in SCHEDULES_DIR.iterdir() if folder.is_dir())

        # Delete the entire schedules directory
        shutil.rmtree(str(SCHEDULES_DIR))

        # Recreate the empty directory
        SCHEDULES_DIR.mkdir(parents=True, exist_ok=True)

        return jsonify({
            'status': 'success',
            'count': count,
            'message': f'Deleted all {count} verification report(s)'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to delete reports: {str(e)}'
        }), 500


@app.route('/api/delete/<name>', methods=['POST'])
def api_delete(name):
    """API endpoint to delete a single verification."""
    import shutil

    # Check if verification exists
    tasknet_dir = SCHEDULES_DIR / name
    if not tasknet_dir.exists():
        return jsonify({'status': 'error', 'message': 'Verification not found'}), 404

    try:
        # Delete entire folder
        shutil.rmtree(str(tasknet_dir))
        return jsonify({
            'status': 'success',
            'message': f'Deleted verification for {name}'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to delete: {str(e)}'
        }), 500


@app.route('/api/folders')
def api_folders():
    """API endpoint to list available folders for saving tasknets."""
    folders = []

    # Common tasknet directories
    common_dirs = [
        'tests/tasknet_files/valid',
        'tests/tasknet_files/invalid',
        '.',  # Current directory
    ]

    # Check for JPL directories if they exist
    jpl_dir = TASKSAT_ROOT / 'jpl' / 'mexec'
    if jpl_dir.exists():
        common_dirs.append('jpl/mexec')

    for dir_path in common_dirs:
        full_path = TASKSAT_ROOT / dir_path
        if full_path.exists() or dir_path == '.':
            folders.append({
                'path': dir_path,
                'display': dir_path if dir_path != '.' else '. (project root)',
                'default': dir_path == 'tests/tasknet_files/valid'
            })

    # Add any additional directories that contain .tn files
    tests_dir = TASKSAT_ROOT / 'tests' / 'tasknet_files'
    if tests_dir.exists():
        for subdir in tests_dir.iterdir():
            if subdir.is_dir():
                rel_path = f'tests/tasknet_files/{subdir.name}'
                if rel_path not in [f['path'] for f in folders]:
                    folders.append({
                        'path': rel_path,
                        'display': rel_path,
                        'default': False
                    })

    return jsonify({
        'status': 'success',
        'folders': folders
    })


@app.route('/api/tasknets')
def api_tasknets():
    """API endpoint to list all verified tasknets."""
    tasknets = []

    if SCHEDULES_DIR.exists():
        for folder in SCHEDULES_DIR.iterdir():
            if folder.is_dir() and (folder / 'latest').exists():
                tasknets.append({
                    'name': folder.name,
                    'has_schedule': True
                })

    return jsonify(tasknets)


@app.route('/api/browse-directory')
def api_browse_directory():
    """API endpoint to browse directories on the filesystem."""
    import os
    from datetime import datetime

    # Get path parameter (default to project root)
    path_param = request.args.get('path', str(TASKSAT_ROOT))
    current_path = Path(path_param).resolve()

    # Security: only allow browsing within user's home directory or project
    home_dir = Path.home()
    if not (str(current_path).startswith(str(home_dir)) or str(current_path).startswith(str(TASKSAT_ROOT))):
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403

    if not current_path.exists() or not current_path.is_dir():
        return jsonify({'status': 'error', 'message': 'Directory not found'}), 404

    try:
        folders = []
        files = []

        # List directory contents
        for item in sorted(current_path.iterdir()):
            try:
                stat = item.stat()
                modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
                size = stat.st_size

                if item.is_dir():
                    # Skip hidden directories and .tasksat
                    if not item.name.startswith('.'):
                        folders.append({
                            'name': item.name,
                            'path': str(item)
                        })
                elif item.is_file():
                    # Show all files, highlight .tn files
                    files.append({
                        'name': item.name,
                        'path': str(item),
                        'is_tn': item.suffix == '.tn',
                        'size': size,
                        'modified': modified
                    })
            except (PermissionError, OSError):
                # Skip files/folders we can't access
                continue

        # Get parent directory
        parent_path = str(current_path.parent) if current_path != current_path.parent else None

        return jsonify({
            'status': 'success',
            'current_path': str(current_path),
            'parent_path': parent_path,
            'folders': folders,
            'files': files
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/add-file', methods=['POST'])
def api_add_file():
    """Add a .tn file to the home list WITHOUT running verification.

    Writes only a placeholder metadata entry pointing at the file's real path;
    no bytes are copied. Opening the resulting card reads/edits that same file
    in place, exactly like a verified tasknet.
    """
    from datetime import datetime
    try:
        data = request.get_json()
        file_path = data.get('file_path', '')

        if not file_path:
            return jsonify({'status': 'error', 'message': 'File path is required'}), 400

        file_path = Path(file_path).resolve()

        if not file_path.exists():
            return jsonify({'status': 'error', 'message': 'File not found'}), 404

        if file_path.suffix != '.tn':
            return jsonify({'status': 'error', 'message': 'File must be a .tn file'}), 400

        tasknet_name = file_path.stem
        latest_dir = SCHEDULES_DIR / tasknet_name / 'latest'

        # Don't clobber a real verification if one already exists.
        existing = latest_dir / 'metadata.json'
        if existing.exists():
            with open(existing, 'r') as f:
                if json.load(f).get('status') != 'not_verified':
                    return jsonify({
                        'status': 'exists',
                        'message': f'{tasknet_name} is already on the list',
                        'tasknet_name': tasknet_name
                    })

        latest_dir.mkdir(parents=True, exist_ok=True)
        with open(latest_dir / 'metadata.json', 'w') as f:
            json.dump({
                'source_path': str(file_path),
                'status': 'not_verified',
                'timestamp': datetime.now().isoformat(),
            }, f, indent=2)

        return jsonify({
            'status': 'success',
            'message': f'Added {tasknet_name} (not verified)',
            'tasknet_name': tasknet_name
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/verify-file', methods=['POST'])
def api_verify_file():
    """API endpoint to verify a tasknet file by path."""
    try:
        data = request.get_json()
        file_path = data.get('file_path', '')
        mode = data.get('mode', 'optimize')
        realizability = bool(data.get('realizability', False))
        compositional = bool(data.get('compositional', False))
        unsat_core = bool(data.get('unsat_core', True))
        timeout = parse_timeout(data)
        task_id = data.get('task_id')

        if not file_path:
            return jsonify({'status': 'error', 'message': 'File path is required'}), 400

        file_path = Path(file_path).resolve()

        if not file_path.exists():
            return jsonify({'status': 'error', 'message': 'File not found'}), 404

        if not file_path.suffix == '.tn':
            return jsonify({'status': 'error', 'message': 'File must be a .tn file'}), 400

        if mode not in ['optimize', 'satisfy']:
            return jsonify({'status': 'error', 'message': 'Invalid mode'}), 400

        # Run verifier on the real file (no copying)
        result = run_verifier(
            verifier_cmd(file_path, mode, realizability, compositional, unsat_core,
                         timeout=timeout),
            task_id=task_id,
            timeout=verify_subprocess_timeout(timeout)
        )
        duration = result['duration']

        if result['outcome'] == 'killed':
            return jsonify({
                'status': 'cancelled',
                'message': 'Verification cancelled',
                'duration': round(duration, 2)
            }), 499

        if result['outcome'] == 'timeout':
            return jsonify({'status': 'timeout', 'message': 'Verification timed out'}), 408

        if result['returncode'] == 0:
            tasknet_name = file_path.stem

            # Check metadata to determine the actual verification result
            latest_dir = SCHEDULES_DIR / tasknet_name / 'latest'
            metadata_file = latest_dir / 'metadata.json'

            verification_status = 'success'
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                verification_status = metadata.get('status', 'success')

            return jsonify({
                'status': 'success',
                'verification_status': verification_status,
                'message': f'Verification completed for {tasknet_name}',
                'tasknet_name': tasknet_name,
                'duration': round(duration, 2)
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Verification failed',
                'output': result['stdout'] + '\n' + result['stderr']
            })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/docs/<doc_name>')
def serve_docs(doc_name):
    """Serve documentation files as rendered markdown."""
    try:
        import markdown
        has_markdown = True
    except ImportError:
        has_markdown = False

    # Map doc names to file paths
    doc_files = {
        'tutorial': TASKSAT_ROOT / 'doc' / 'tutorial.md',
        'manual': TASKSAT_ROOT / 'doc' / 'manual.md',
        'grammar': TASKSAT_ROOT / 'src' / 'smt' / 'grammar.txt',
        'getting-started': TASKSAT_ROOT / 'doc' / 'getting-started.md',
    }

    if doc_name not in doc_files:
        return "Documentation not found", 404

    doc_path = doc_files[doc_name]

    if not doc_path.exists():
        return f"Documentation file not found: {doc_path}", 404

    # Read the file
    with open(doc_path, 'r') as f:
        content = f.read()

    # For grammar.txt, always wrap in pre/code tags
    if doc_name == 'grammar':
        html_content = f'<pre style="white-space: pre-wrap; font-family: monospace; padding: 2rem;">{content}</pre>'
        title = "TaskNet Grammar Reference"
    else:
        # Render markdown if available, otherwise show plain text
        if has_markdown:
            html_content = markdown.markdown(
                content,
                extensions=['fenced_code', 'tables', 'toc']
            )
        else:
            # Fallback: wrap in pre tag with basic styling
            html_content = f'<pre style="white-space: pre-wrap; max-width: 100%; overflow-x: auto;">{content}</pre>'
            html_content += '<div class="alert alert-warning mt-4">Note: Install the <code>markdown</code> package for better formatting: <code>pip install markdown</code></div>'

        title_map = {
            'tutorial': 'TaskSAT Tutorial',
            'manual': 'TaskSAT Manual',
            'getting-started': 'Getting Started with TaskSAT'
        }
        title = title_map.get(doc_name, 'TaskSAT Documentation')

    # Return rendered HTML with styling
    return f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 900px;
                margin: 0 auto;
                padding: 2rem;
            }}
            h1, h2, h3, h4, h5, h6 {{
                margin-top: 1.5rem;
                margin-bottom: 1rem;
                font-weight: 600;
            }}
            h1 {{ font-size: 2.5rem; border-bottom: 2px solid #0d6efd; padding-bottom: 0.5rem; }}
            h2 {{ font-size: 2rem; border-bottom: 1px solid #dee2e6; padding-bottom: 0.5rem; }}
            h3 {{ font-size: 1.5rem; }}
            code {{
                background-color: #f8f9fa;
                padding: 0.2rem 0.4rem;
                border-radius: 3px;
                font-family: "SF Mono", Monaco, "Cascadia Code", "Roboto Mono", Consolas, monospace;
                font-size: 0.9em;
                color: #e83e8c;
            }}
            pre {{
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 1rem;
                overflow-x: auto;
            }}
            pre code {{
                background-color: transparent;
                padding: 0;
                color: inherit;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 1rem 0;
            }}
            table th, table td {{
                border: 1px solid #dee2e6;
                padding: 0.5rem;
                text-align: left;
            }}
            table th {{
                background-color: #f8f9fa;
                font-weight: 600;
            }}
            a {{ color: #0d6efd; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
            .back-link {{
                position: fixed;
                top: 1rem;
                right: 1rem;
                z-index: 1000;
            }}
        </style>
    </head>
    <body>
        <a href="/" class="btn btn-primary back-link">
            <i class="bi bi-arrow-left"></i> Back to TaskSAT
        </a>
        <div class="content">
            {html_content}
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    '''


def open_browser():
    """Open browser after a short delay."""
    import time
    time.sleep(1.5)
    webbrowser.open('http://localhost:5000')


def main():
    """Start the web server."""
    import argparse
    parser = argparse.ArgumentParser(description='TaskSAT Web Interface')
    parser.add_argument('--port', type=int, default=5000, help='Port to run the server on (default: 5000)')
    args = parser.parse_args()

    print("="*80)
    print("🚀 TaskSAT Web Interface")
    print("="*80)
    print()
    print(f"📊 Starting server at http://localhost:{args.port}")
    print("📁 Root directory:", TASKSAT_ROOT)
    print("📦 Schedules directory:", SCHEDULES_DIR)
    print()
    print("Press Ctrl+C to stop the server")
    print("="*80)
    print()

    # Open browser in background thread
    def open_browser_with_port():
        """Open the UI in a browser, after giving Flask a moment to bind."""
        import time
        time.sleep(1.5)
        webbrowser.open(f'http://localhost:{args.port}')

    threading.Thread(target=open_browser_with_port, daemon=True).start()

    # Start Flask server
    app.run(debug=True, use_reloader=False, port=args.port)


if __name__ == '__main__':
    main()
