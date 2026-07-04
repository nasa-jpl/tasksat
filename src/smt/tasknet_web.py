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
import webbrowser
import threading

app = Flask(__name__)

# Configure paths
TASKSAT_ROOT = Path(__file__).parent.parent.parent
SCHEDULES_DIR = TASKSAT_ROOT / '.tasksat' / 'schedules'
ERRORS_DIR = TASKSAT_ROOT / '.tasksat' / 'errors'
TESTS_DIR = TASKSAT_ROOT / 'tests' / 'tasknet_files'


def verifier_cmd(tn_path, mode, realizability=False):
    """Build the tasknet_verifier.py command line."""
    cmd = ['python', str(TASKSAT_ROOT / 'src' / 'smt' / 'tasknet_verifier.py'),
           str(tn_path), '--mode', mode]
    if realizability:
        cmd.append('--realizability')
    return cmd


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
                    'status': status,  # 'success', 'unsat', or 'error'
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
        errors=errors
    )


@app.route('/static/schedules/<path:filename>')
def serve_schedule(filename):
    """Serve schedule visualization files."""
    return send_from_directory(SCHEDULES_DIR, filename)


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
        metadata=metadata,
        prev_tasknet=prev_tasknet,
        next_tasknet=next_tasknet,
        errors=errors
    )


@app.route('/api/verify/<name>', methods=['POST'])
def api_verify(name):
    """API endpoint to run verification on a tasknet."""
    import subprocess
    import time

    # Get mode from request (default: optimize)
    data = request.get_json() if request.is_json else {}
    mode = data.get('mode', 'optimize')
    realizability = bool(data.get('realizability', False))

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
    start_time = time.time()
    try:
        result = subprocess.run(
            verifier_cmd(tn_file, mode, realizability),
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        duration = time.time() - start_time

        if result.returncode == 0:
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
                'output': result.stdout,
                'duration': round(duration, 2)
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Verification failed',
                'output': result.stdout + '\n' + result.stderr,
                'duration': round(duration, 2)
            })
    except subprocess.TimeoutExpired:
        return jsonify({
            'status': 'timeout',
            'message': 'Verification timed out after 5 minutes'
        }), 408
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error running verification: {str(e)}'
        }), 500


@app.route('/api/create', methods=['POST'])
def api_create():
    """API endpoint to create a new tasknet file and verify it."""
    import subprocess
    import time

    try:
        data = request.get_json()
        name = data.get('name', '')
        folder = data.get('folder', '')
        source = data.get('source', '')
        mode = data.get('mode', 'optimize')
        realizability = bool(data.get('realizability', False))

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
        start_time = time.time()
        result = subprocess.run(
            verifier_cmd(file_path, mode, realizability),
            capture_output=True,
            text=True,
            timeout=300
        )
        duration = time.time() - start_time

        if result.returncode == 0:
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
                'output': result.stdout + '\n' + result.stderr
            })
    except subprocess.TimeoutExpired:
        return jsonify({'status': 'timeout', 'message': 'Verification timed out'}), 408
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/upload', methods=['POST'])
def api_upload():
    """API endpoint to upload and verify a tasknet file."""
    import subprocess
    import time
    import tempfile
    import os

    # Check if file was uploaded
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No file selected'}), 400

    if not file.filename.endswith('.tn'):
        return jsonify({'status': 'error', 'message': 'File must be a .tn file'}), 400

    # Get mode from form data (default: optimize)
    mode = request.form.get('mode', 'optimize')
    realizability = request.form.get('realizability', 'false').lower() == 'true'
    if mode not in ['optimize', 'satisfy']:
        return jsonify({'status': 'error', 'message': 'Invalid mode'}), 400

    # Save uploaded file to .tasksat/uploads/
    uploads_dir = TASKSAT_ROOT / '.tasksat' / 'uploads'
    uploads_dir.mkdir(parents=True, exist_ok=True)

    upload_path = uploads_dir / file.filename
    file.save(str(upload_path))

    try:
        # Run verifier
        start_time = time.time()
        result = subprocess.run(
            verifier_cmd(upload_path, mode, realizability),
            capture_output=True,
            text=True,
            timeout=300
        )
        duration = time.time() - start_time

        if result.returncode == 0:
            # Extract tasknet name from output (or use filename)
            tasknet_name = Path(file.filename).stem

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
                'output': result.stdout + '\n' + result.stderr
            })
    except subprocess.TimeoutExpired:
        return jsonify({'status': 'timeout', 'message': 'Verification timed out'}), 408
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
    import subprocess
    import time

    try:
        data = request.get_json()
        source = data.get('source', '')
        mode = data.get('mode', 'optimize')
        realizability = bool(data.get('realizability', False))

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
        start_time = time.time()
        result = subprocess.run(
            verifier_cmd(source_path, mode, realizability),
            capture_output=True,
            text=True,
            timeout=300
        )
        duration = time.time() - start_time

        if result.returncode == 0:
            return jsonify({
                'status': 'success',
                'message': 'Source saved and verification completed',
                'duration': round(duration, 2)
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Verification failed',
                'output': result.stdout + '\n' + result.stderr
            })
    except subprocess.TimeoutExpired:
        return jsonify({'status': 'timeout', 'message': 'Verification timed out'}), 408
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


@app.route('/api/verify-file', methods=['POST'])
def api_verify_file():
    """API endpoint to verify a tasknet file by path."""
    import subprocess
    import time

    try:
        data = request.get_json()
        file_path = data.get('file_path', '')
        mode = data.get('mode', 'optimize')
        realizability = bool(data.get('realizability', False))

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
        start_time = time.time()
        result = subprocess.run(
            verifier_cmd(file_path, mode, realizability),
            capture_output=True,
            text=True,
            timeout=300
        )
        duration = time.time() - start_time

        if result.returncode == 0:
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
                'output': result.stdout + '\n' + result.stderr
            })
    except subprocess.TimeoutExpired:
        return jsonify({'status': 'timeout', 'message': 'Verification timed out'}), 408
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
        import time
        time.sleep(1.5)
        webbrowser.open(f'http://localhost:{args.port}')

    threading.Thread(target=open_browser_with_port, daemon=True).start()

    # Start Flask server
    app.run(debug=True, use_reloader=False, port=args.port)


if __name__ == '__main__':
    main()
