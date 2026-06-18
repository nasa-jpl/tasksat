#!/usr/bin/env python3
# solve_tasknet.py
#
# For real-time progress indicators, run with:
#   python -u src/smt/tasknet_verifier.py <file>
# or:
#   PYTHONUNBUFFERED=1 python src/smt/tasknet_verifier.py <file>
#
import argparse
import os
import sys
import time
from pprint import pprint

# Set environment variable to request unbuffered mode
os.environ['PYTHONUNBUFFERED'] = '1'

from tasknet_parser import parse_tasknet_file
from tasknet_transforms import apply_transforms
from tasknet_smt import TaskNetSMT, TaskNetTL
from tasknet_wellformedness import check_wellformedness
from color_utils import error, success, warning, info, header, bold, dim, Colors

def save_failed_verification(path: str, mode: str, start_time: float, error_message: str, error_type: str = "error"):
    """Save metadata for failed verification attempts.

    Args:
        error_type: One of "syntax_error", "wellformedness_error", or "error" (default)
    """
    from pathlib import Path
    from datetime import datetime
    import json

    input_path = Path(path)
    tasknet_name = input_path.stem

    # Create timestamped folder structure
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = Path('.tasksat/schedules') / tasknet_name / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    # Also create latest symlink/folder
    latest_dir = Path('.tasksat/schedules') / tasknet_name / 'latest'
    latest_dir.mkdir(parents=True, exist_ok=True)

    end_time = time.time()

    # Reconstruct command
    import sys
    command_parts = ['python', 'src/smt/tasknet_verifier.py', path]
    if mode != 'optimize':
        command_parts.extend(['--mode', mode])
    command = ' '.join(command_parts)

    # Save metadata with error status
    metadata = {
        "source_path": str(input_path.absolute()),
        "timestamp": datetime.now().isoformat(),
        "status": error_type,
        "error_message": error_message,
        "duration_sec": round(end_time - start_time, 3),
        "command": command,
        "mode": mode
    }

    with open(run_dir / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    with open(latest_dir / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"\n📄 Failed verification saved to: {run_dir}")
    print(f"📄 Latest at: {latest_dir}")

def write_transformed_tasknet(tn, output_path: str, input_path: str):
    """Write the transformed tasknet to a file for inspection."""
    from pathlib import Path
    from tasknet_printer import print_tasknet_to_file

    # If no output path specified, use .tasksat/transformed/
    if output_path is None:
        input_file = Path(input_path)

        # Find the root .tasksat directory (avoid nesting .tasksat/.tasksat/)
        # Walk up the directory tree to find if we're already inside a .tasksat/
        current = input_file.parent
        tasksat_root = None

        for parent in [current] + list(current.parents):
            if parent.name == '.tasksat':
                tasksat_root = parent
                break

        if tasksat_root:
            # Already inside .tasksat/, use it as root
            tasksat_dir = tasksat_root / 'transformed'
        else:
            # Not inside .tasksat/, create one in the input file's directory
            tasksat_dir = input_file.parent / '.tasksat' / 'transformed'

        tasksat_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(tasksat_dir / f"{input_file.stem}_transformed.tn")

    # Determine format based on file extension
    path = Path(output_path)

    if path.suffix == '.tn':
        # Write as TaskSAT .tn syntax
        print_tasknet_to_file(tn, output_path)
        print(f"📄 Transformed tasknet written to: {output_path} (.tn format)\n")
    else:
        # Write as JSON (legacy format)
        import json

        def task_to_dict(t):
            """Convert Task to dict."""
            return {
                'id': t.id,
                'ident': t.ident,
                'kind': t.kind.value,
                'definition': t.definition,
                'priority': t.priority,
                'startrng': [t.startrng.low, t.startrng.high] if t.startrng else None,
                'endrng': [t.endrng.low, t.endrng.high] if t.endrng else None,
                'durrng': [t.durrng.low, t.durrng.high] if t.durrng else None,
                'dur': t.dur,
                'start': t.start,
                'after_instances': t.after_instances,
                'containedin_instances': t.containedin_instances,
                'after_definitions': t.after_definitions,
                'containedin_definitions': t.containedin_definitions,
            }

        output = {
            'tasknet_id': tn.id,
            'endTime': tn.endTime,
            'tasks': [task_to_dict(t) for t in tn.tasks],
        }

        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"📄 Transformed tasknet written to: {output_path} (JSON format)\n")

def main(path: str, mode: str = 'optimize', transform_only: bool = False):
    print('\n\n\n\n\n\n\n' + header('*** NEW SCHEDULE***') + '\n')

    start_time = time.time()

    try:
        tn = parse_tasknet_file(path)
    except Exception as e:
        # Save parse error
        save_failed_verification(path, mode, start_time, f"Parse error: {str(e)}", error_type="syntax_error")
        print(error(f"❌ SYNTAX ERROR: {e}"))
        return

    # Apply AST transformations (desugar derived constructs)
    tn, auto_instantiation_occurred = apply_transforms(tn)

    # Automatically write transformed tasknet if auto-instantiation occurred
    if auto_instantiation_occurred:
        write_transformed_tasknet(tn, None, path)

    # Exit early if only transforming
    if transform_only:
        if not auto_instantiation_occurred:
            print(info("No auto-instantiation occurred. No transformed file written."))
        print(success("✓ Transformation complete. Exiting without verification."))
        return

    # Check well-formedness before solving
    if not check_wellformedness(tn):
        # Save wellformedness error
        save_failed_verification(path, mode, start_time, "Wellformedness check failed", error_type="wellformedness_error")
        print(error("\n❌ WELLFORMEDNESS CHECK FAILED"))
        return  # Errors already printed by checker

    use_optimization = (mode == 'optimize')
    enc = TaskNetTL(tn, error_trace=True, use_optimization=use_optimization)

    # Phase 1: Validity checking
    validity_start = time.time()
    m, unsat_core_data = enc.solve()
    validity_end = time.time()

    if m is None:
        print(warning("\n⚠️  UNSAT: No valid schedule found!"))
        print(f"\n{bold('=== Timing ===')}")
        print(f"Validity checking: {validity_end - validity_start:.2f} seconds")
        print(f"Total time: {validity_end - start_time:.2f} seconds")

        # Save UNSAT result for web UI
        from pathlib import Path
        from datetime import datetime
        import json

        input_path = Path(path)
        tasknet_name = input_path.stem

        # Create timestamped folder structure
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        run_dir = Path('.tasksat/schedules') / tasknet_name / timestamp
        run_dir.mkdir(parents=True, exist_ok=True)

        # Also create latest symlink/folder
        latest_dir = Path('.tasksat/schedules') / tasknet_name / 'latest'
        latest_dir.mkdir(parents=True, exist_ok=True)

        # Reconstruct command
        import sys
        command_parts = ['python', 'src/smt/tasknet_verifier.py', path]
        if mode != 'optimize':
            command_parts.extend(['--mode', mode])
        command = ' '.join(command_parts)

        # Save metadata
        metadata = {
            "source_path": str(input_path.absolute()),
            "timestamp": datetime.now().isoformat(),
            "status": "unsat",
            "duration_sec": round(validity_end - start_time, 3),
            "validity_check_sec": round(validity_end - validity_start, 3),
            "command": command,
            "mode": mode
        }

        with open(run_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
        with open(latest_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)

        # Save UNSAT core analysis if available
        if unsat_core_data:
            with open(run_dir / "unsat_core.json", 'w') as f:
                json.dump(unsat_core_data, f, indent=2)
            with open(latest_dir / "unsat_core.json", 'w') as f:
                json.dump(unsat_core_data, f, indent=2)
            print(dim(f"📄 UNSAT core analysis saved to: {run_dir}/unsat_core.json"))

        print(dim(f"\n📄 UNSAT result saved to: {run_dir}"))
        print(dim(f"📄 Latest at: {latest_dir}"))
        return

    enc.pretty_print(m)

    # Phase 2: Property verification
    property_start = time.time()
    property_results, violations = enc.check_temporal_properties()
    property_end = time.time()

    end_time = time.time()

    print(f"\n{bold('=== Timing ===')}")
    print(f"Validity checking: {validity_end - validity_start:.2f} seconds")
    print(f"Property verification: {property_end - property_start:.2f} seconds")

    # Add average time per property if properties exist
    num_properties = len(tn.properties) if hasattr(tn, 'properties') and tn.properties else 0
    if num_properties > 0:
        avg_time_per_property = (property_end - property_start) / num_properties
        print(f"Average per property: {avg_time_per_property:.2f} seconds ({num_properties} properties)")

    print(f"Total time: {end_time - start_time:.2f} seconds")

    # Print success message if no violations
    if not violations:
        print(success("\n✓ All constraints and properties satisfied!") if num_properties > 0 else success("\n✓ Valid schedule found!"))

    # Export schedule as JSON and generate visualizations
    from pathlib import Path
    from datetime import datetime
    import json
    import os

    input_path = Path(path)
    tasknet_name = input_path.stem

    # Create timestamped folder structure
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = Path('.tasksat/schedules') / tasknet_name / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    # Also create latest symlink/folder
    latest_dir = Path('.tasksat/schedules') / tasknet_name / 'latest'
    latest_dir.mkdir(parents=True, exist_ok=True)

    schedule = enc.extract_schedule(m)
    evolution = enc.extract_timeline_evolution(m)

    # Save metadata
    import sys
    # Reconstruct the command that was run
    command_parts = ['python', 'src/smt/tasknet_verifier.py', path]
    if mode != 'optimize':
        command_parts.extend(['--mode', mode])
    command = ' '.join(command_parts)

    # Determine status based on violations
    status = "violated" if violations else "success"

    metadata = {
        "source_path": str(input_path.absolute()),
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "duration_sec": round(end_time - start_time, 3),
        "validity_check_sec": round(validity_end - validity_start, 3),
        "property_verification_sec": round(property_end - property_start, 3),
        "command": command,
        "mode": mode,
        "num_violations": len(violations) if violations else 0
    }
    metadata_path = run_dir / "metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    # Copy metadata to latest/
    with open(latest_dir / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)

    # Save property verification results
    if property_results:
        properties_path = run_dir / "properties.json"
        with open(properties_path, 'w') as f:
            json.dump(property_results, f, indent=2)
        with open(latest_dir / "properties.json", 'w') as f:
            json.dump(property_results, f, indent=2)
        print(f"📋 Property verification results saved to: {properties_path}")

    # Save schedule as JSON
    json_path = run_dir / "schedule.json"
    with open(json_path, 'w') as f:
        json.dump(schedule, f, indent=2)
    with open(latest_dir / "schedule.json", 'w') as f:
        json.dump(schedule, f, indent=2)

    # Save timeline evolution as JSON
    evolution_json_path = run_dir / "timeline.json"
    with open(evolution_json_path, 'w') as f:
        json.dump(evolution, f, indent=2)
    with open(latest_dir / "timeline.json", 'w') as f:
        json.dump(evolution, f, indent=2)

    # Generate Gantt chart
    try:
        from tasknet_gantt import create_gantt_from_schedule
        gantt_path = run_dir / "gantt.png"
        create_gantt_from_schedule(schedule, str(gantt_path), f"Schedule: {tn.id}")
        # Copy to latest/
        import shutil
        shutil.copy(str(gantt_path), str(latest_dir / "gantt.png"))
        print(f"\n📊 Gantt chart saved to: {gantt_path}")
    except ImportError:
        print("⚠️  Gantt chart generation skipped (matplotlib not installed)")

    # Generate timeline evolution visualization
    try:
        from tasknet_timeline_viz import create_timeline_evolution_plot
        timeline_path = run_dir / "timeline.png"
        create_timeline_evolution_plot(schedule, evolution, str(timeline_path), f"Schedule: {tn.id}", tasknet=tn)
        # Copy to latest/
        import shutil
        shutil.copy(str(timeline_path), str(latest_dir / "timeline.png"))
        print(f"📈 Timeline evolution saved to: {timeline_path}")
    except ImportError:
        print("⚠️  Timeline evolution chart skipped (matplotlib not installed)")

    print(f"📄 Verification results saved to: {run_dir}")
    print(f"📄 Latest results at: {latest_dir}")

    # Generate error trace visualizations for violated properties
    if violations:
        print(f"\n🔴 Generating {len(violations)} error trace visualization(s)...")
        # Store errors under this verification run's directory
        errors_dir = run_dir / 'errors'
        errors_dir.mkdir(parents=True, exist_ok=True)

        # Also create errors dir in latest/
        latest_errors_dir = latest_dir / 'errors'
        latest_errors_dir.mkdir(parents=True, exist_ok=True)

        for violation in violations:
            prop_name = violation['property_name']
            model = violation['model']
            error_enc = violation['encoder']
            violation_zones = violation.get('violation_zones', [])

            # Find the property to get its formula (using proper pretty printer)
            prop_formula_str = None
            if hasattr(tn, 'properties') and tn.properties:
                for prop in tn.properties:
                    if prop.name == prop_name:
                        from tasknet_printer import TaskNetPrinter
                        printer = TaskNetPrinter()
                        prop_formula_str = printer.print_tl_formula(prop.formula)
                        break

            # Extract error trace data
            error_schedule = error_enc.extract_schedule(model)
            error_evolution = error_enc.extract_timeline_evolution(model)

            # Save error schedule and timeline data (no tasknet name prefix needed)
            error_schedule_path = errors_dir / f"{prop_name}_schedule.json"
            error_timeline_path = errors_dir / f"{prop_name}_timeline.json"

            with open(error_schedule_path, 'w') as f:
                json.dump(error_schedule, f, indent=2)
            with open(error_timeline_path, 'w') as f:
                json.dump(error_evolution, f, indent=2)

            # Copy to latest/
            with open(latest_errors_dir / f"{prop_name}_schedule.json", 'w') as f:
                json.dump(error_schedule, f, indent=2)
            with open(latest_errors_dir / f"{prop_name}_timeline.json", 'w') as f:
                json.dump(error_evolution, f, indent=2)

            # Generate error trace visualization
            try:
                from tasknet_timeline_viz import create_timeline_evolution_plot
                error_viz_path = errors_dir / f"{prop_name}_timeline.png"

                # Create title with property name and formula
                if prop_formula_str:
                    title = f"Error Trace: {prop_name}\n{prop_formula_str}"
                else:
                    title = f"Error Trace: {prop_name}"

                create_timeline_evolution_plot(
                    error_schedule,
                    error_evolution,
                    str(error_viz_path),
                    title=title,
                    violation_zones=violation_zones,
                    tasknet=tn
                )
                # Copy to latest/
                import shutil
                shutil.copy(str(error_viz_path), str(latest_errors_dir / f"{prop_name}_timeline.png"))

                print(f"  📉 Error trace for '{prop_name}' saved to: {error_viz_path}")
                if violation_zones:
                    print(f"      Violation detected at zones: {violation_zones}")
            except ImportError:
                print(f"  ⚠️  Error trace visualization skipped (matplotlib not installed)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TaskNet Scheduler and Verifier')
    parser.add_argument('tasknet_file', help='Path to .tn file')
    parser.add_argument('--mode', choices=['optimize', 'satisfy'], default='optimize',
                        help='Mode for main schedule generation: optimize (use Optimize solver for best schedule) or satisfy (use Solver for any valid schedule). Property verification always uses Solver for faster counterexample finding.')
    parser.add_argument('--transform-only', action='store_true',
                        help='Only write transformed tasknet (if auto-instantiation occurs) and exit without verification')
    args = parser.parse_args()

    main(args.tasknet_file, args.mode, args.transform_only)


