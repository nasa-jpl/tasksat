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
from io import StringIO

# Set environment variable to request unbuffered mode
os.environ['PYTHONUNBUFFERED'] = '1'

from tasknet_parser import parse_tasknet_file
from tasknet_transforms import apply_transforms
from tasknet_smt import TaskNetSMT, TaskNetTL
from tasknet_wellformedness import check_wellformedness
from color_utils import error, success, warning, info, header, bold, dim, Colors


class TeeOutput:
    """Capture output while still displaying it to the terminal."""
    def __init__(self):
        self.terminal = sys.stdout
        self.log = StringIO()

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()

    def getvalue(self):
        return self.log.getvalue()


# Global variable to capture console output
_console_output = None


def save_console_output(run_dir, latest_dir):
    """Save captured console output to both timestamped and latest directories."""
    global _console_output
    if _console_output:
        output_text = _console_output.getvalue()
        with open(run_dir / 'console_output.txt', 'w') as f:
            f.write(output_text)
        with open(latest_dir / 'console_output.txt', 'w') as f:
            f.write(output_text)

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

    # Save console output
    save_console_output(run_dir, latest_dir)

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

def main(path: str, mode: str = 'optimize', transform_only: bool = False,
         realizability: bool = False, realizability_max_iters: int = 50,
         realizability_budget: float = 60.0,
         compositional: bool = False, compositional_max_iters: int = 50,
         compositional_budget: float = 60.0):
    print('\n\n\n\n\n\n\n' + header('*** NEW SCHEDULE***') + '\n')

    start_time = time.time()

    try:
        tn = parse_tasknet_file(path)
    except Exception as e:
        # Save parse error
        save_failed_verification(path, mode, start_time, f"Parse error: {str(e)}", error_type="syntax_error")
        print(error(f"❌ SYNTAX ERROR: {e}"))
        return

    # Keep a DEEP COPY of the pre-transform AST for the static structure
    # visualization: mutex/sequence survive only before desugaring, and
    # apply_transforms mutates task/timeline/formula objects in place (auto-
    # instances, __*_active timelines, desugared formulas), so a plain reference
    # would not preserve the original spec.
    import copy
    tn_pre_transform = copy.deepcopy(tn)

    # Apply AST transformations (desugar derived constructs). The returned flag
    # signals a structural rewrite (auto-instantiation OR session flattening) —
    # it gates whether the transformed inspection file is written, not verification.
    try:
        tn, structural_rewrite_occurred = apply_transforms(tn)
    except Exception as e:
        import traceback
        error_details = f"Transform error: {str(e)}\n\n{traceback.format_exc()}"
        print(error(f"❌ TRANSFORM ERROR: {e}"))
        print(traceback.format_exc())  # Print to stdout (captured by TeeOutput)
        save_failed_verification(path, mode, start_time, error_details, error_type="error")
        return

    # Automatically write transformed tasknet if a structural rewrite occurred
    # (auto-instantiation or session flattening)
    if structural_rewrite_occurred:
        try:
            write_transformed_tasknet(tn, None, path)
        except Exception as e:
            import traceback
            error_details = f"Error writing transformed tasknet: {str(e)}\n\n{traceback.format_exc()}"
            print(error(f"❌ ERROR WRITING TRANSFORMED TASKNET: {e}"))
            print(traceback.format_exc())  # Print to stdout (captured by TeeOutput)
            save_failed_verification(path, mode, start_time, error_details, error_type="error")
            return

    # Exit early if only transforming
    if transform_only:
        if not structural_rewrite_occurred:
            print(info("No structural rewrite (auto-instantiation or session flattening) occurred. No transformed file written."))
        print(success("✓ Transformation complete. Exiting without verification."))
        return

    # Check well-formedness before solving
    if not check_wellformedness(tn):
        # Save wellformedness error
        save_failed_verification(path, mode, start_time, "Wellformedness check failed", error_type="wellformedness_error")
        print(error("\n❌ WELLFORMEDNESS CHECK FAILED"))
        return  # Errors already printed by checker

    # Snapshot the transformed tasknet before encoding. SMT encoding mutates
    # task ranges (fills unconstrained start/end with MAX_INT and drops taskdefs),
    # so the temporal range visualization must use this pre-encoding copy to show
    # the real specification bounds.
    import copy
    tn_pre_encoding = copy.deepcopy(tn)

    use_optimization = (mode == 'optimize')

    try:
        enc = TaskNetTL(tn, error_trace=True, use_optimization=use_optimization)
    except Exception as e:
        import traceback
        error_details = f"SMT encoding error: {str(e)}\n\n{traceback.format_exc()}"
        print(error(f"❌ SMT ENCODING ERROR: {e}"))
        print(traceback.format_exc())  # Print to stdout (captured by TeeOutput)
        save_failed_verification(path, mode, start_time, error_details, error_type="error")
        return

    # Phase 1: Validity checking
    validity_start = time.time()
    try:
        m, unsat_core_data = enc.solve()
    except Exception as e:
        import traceback
        error_details = f"Solver error: {str(e)}\n\n{traceback.format_exc()}"
        print(error(f"❌ SOLVER ERROR: {e}"))
        print(traceback.format_exc())  # Print to stdout (captured by TeeOutput)
        save_failed_verification(path, mode, start_time, error_details, error_type="error")
        return
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

        # Save console output
        save_console_output(run_dir, latest_dir)

        print(dim(f"\n📄 UNSAT result saved to: {run_dir}"))
        print(dim(f"📄 Latest at: {latest_dir}"))
        return

    enc.pretty_print(m)

    # Phase 2: Property verification
    property_start = time.time()
    property_results, violations = enc.check_temporal_properties()
    property_end = time.time()

    # Phase 3 (opt-in): Realizability check (forall initial state exists schedule)
    realizability_result = None
    if realizability:
        from tasknet_realizability import check_realizability
        print(header("\nChecking realizability (forall initial state exists schedule):"))
        realizability_result = check_realizability(
            tn, max_iters=realizability_max_iters, budget_sec=realizability_budget)

        if realizability_result['status'] == 'holds':
            print(success(f"  → HOLDS ✓ ({realizability_result['note']})"))
        elif realizability_result['status'] == 'violated':
            print(error("  → VIOLATED!"))
            print("  Initial state with no valid schedule:")
            for tl, val in (realizability_result['counterexample_initial_state'] or {}).items():
                print(f"    {tl} = {val}")
        else:
            print(warning(f"  → UNKNOWN ⚠ ({realizability_result['note']})"))

        # Ship it with the property results (console summary above; JSON below).
        # The (possibly large) unsat core is saved to its own file instead.
        property_results.append({
            k: v for k, v in realizability_result.items() if k != 'unsat_core'})

    # Phase 3.5 (opt-in): Compositional inductive-invariant sequencing check.
    # Fires when --compositional is passed OR the spec declares
    # `invariant compositional { ... }`. Uses the PRE-transform AST (session
    # children + invariant block intact).
    compositional_result = None
    if compositional or getattr(tn_pre_transform, 'compositional', False):
        from tasknet_compositional import check_compositional
        print(header("\nChecking compositional invariant {P}S{P} => forall N {P}S^N{P}:"))
        compositional_result = check_compositional(
            tn_pre_transform, apply_transforms,
            max_iters=compositional_max_iters, budget_sec=compositional_budget)

        cr = compositional_result
        detail = f"AA safety={cr.get('aa')}, AE realizability-under-P={cr.get('ae')}"
        if cr['status'] == 'holds':
            print(success(f"  → HOLDS ✓ ({detail})"))
            print(dim(f"    {cr['note']}"))
        elif cr['status'] == 'violated':
            print(error(f"  → VIOLATED! ({detail})"))
            print(f"    {cr['note']}")
            if cr.get('counterexample_initial_state'):
                print("  Initial state (satisfies P) with no P-preserving schedule:")
                for tl, val in cr['counterexample_initial_state'].items():
                    print(f"    {tl} = {val}")
        else:
            print(warning(f"  → UNKNOWN ⚠ ({cr['note']})"))

        property_results.append({
            k: v for k, v in compositional_result.items() if k != 'unsat_core'})

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

    # Print success message if no violations (including realizability + compositional)
    compositional_violated = (compositional_result is not None
                              and compositional_result['status'] == 'violated')
    if not violations and not (realizability_result is not None
                               and realizability_result['status'] == 'violated') \
            and not compositional_violated:
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

    # Determine status based on violations (a violated realizability check
    # counts, even though it produces no error trace)
    realizability_violated = (realizability_result is not None
                              and realizability_result['status'] == 'violated')
    status = "violated" if (violations or realizability_violated
                            or compositional_violated) else "success"

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
    if realizability_result is not None:
        metadata["realizability"] = realizability_result['status']
        metadata["realizability_check_sec"] = realizability_result['duration_sec']
    if compositional_result is not None:
        metadata["compositional"] = compositional_result['status']
        metadata["compositional_check_sec"] = compositional_result['duration_sec']
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

    # Save the realizability counterexample's unsat core (why nothing is
    # schedulable from that initial state)
    if realizability_result is not None and realizability_result.get('unsat_core'):
        for d in (run_dir, latest_dir):
            with open(d / "realizability_unsat_core.json", 'w') as f:
                json.dump(realizability_result['unsat_core'], f, indent=2)
        print(dim(f"📄 Realizability unsat core saved to: {run_dir}/realizability_unsat_core.json"))

    # Save the compositional AE counterexample's unsat core (why a P-state admits
    # no P-preserving schedule)
    if compositional_result is not None and compositional_result.get('unsat_core'):
        for d in (run_dir, latest_dir):
            with open(d / "compositional_unsat_core.json", 'w') as f:
                json.dump(compositional_result['unsat_core'], f, indent=2)
        print(dim(f"📄 Compositional unsat core saved to: {run_dir}/compositional_unsat_core.json"))

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
        create_gantt_from_schedule(schedule, str(gantt_path), f"Schedule: {tn.id}", tasknet=tn)
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

    # Generate static tasknet structure visualization (uses the pre-transform AST
    # so mutex/sequence edges are visible; rendered via Graphviz, not matplotlib).
    # Produces two images: <base>_relations.png and <base>_timelines.png.
    try:
        from tasknet_structure_viz import create_structure_visualization
        structure_base = run_dir / "structure.png"
        created = create_structure_visualization(tn_pre_transform, str(structure_base))
        if created:
            import shutil
            for src_png in created:
                shutil.copy(src_png, str(latest_dir / Path(src_png).name))
            print(f"🗺️  Structure diagrams saved to: {run_dir}")
    except ImportError:
        print("⚠️  Structure diagram skipped (tasknet_structure_viz unavailable)")

    # Generate temporal range visualization (shows time constraints horizontally)
    try:
        from tasknet_temporal_viz import create_temporal_range_visualization
        temporal_path = run_dir / "temporal.png"
        temporal_created = create_temporal_range_visualization(tn_pre_encoding, str(temporal_path))
        if temporal_created:
            import shutil
            shutil.copy(str(temporal_path), str(latest_dir / "temporal.png"))
            print(f"📊 Temporal range visualization saved to: {run_dir}")
    except ImportError:
        print("⚠️  Temporal range visualization skipped (matplotlib not installed)")

    # Save console output
    save_console_output(run_dir, latest_dir)

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
    parser.add_argument('--realizability', action='store_true',
                        help='After finding a valid schedule, also check that EVERY initial state admitted by the spec has some valid schedule (forall init exists schedule)')
    parser.add_argument('--realizability-max-iters', type=int, default=50,
                        help='Maximum CEGIS iterations for the realizability check (default: 50)')
    parser.add_argument('--realizability-budget', type=float, default=60.0,
                        help='Wall-clock budget in seconds for the realizability check (default: 60)')
    parser.add_argument('--compositional', action='store_true',
                        help='Check the inductive-invariant sequencing property {P}S{P} => forall N {P}S^N{P}: project one session and verify AA safety + AE realizability-under-P for the invariant P (also triggered by `invariant compositional {...}` in the spec)')
    parser.add_argument('--compositional-max-iters', type=int, default=50,
                        help='Maximum CEGIS iterations for the compositional AE check (default: 50)')
    parser.add_argument('--compositional-budget', type=float, default=60.0,
                        help='Wall-clock budget in seconds for the compositional AE check (default: 60)')
    args = parser.parse_args()

    # Capture console output
    _console_output = TeeOutput()
    old_stdout = sys.stdout
    sys.stdout = _console_output

    try:
        main(args.tasknet_file, args.mode, args.transform_only,
             realizability=args.realizability,
             realizability_max_iters=args.realizability_max_iters,
             realizability_budget=args.realizability_budget,
             compositional=args.compositional,
             compositional_max_iters=args.compositional_max_iters,
             compositional_budget=args.compositional_budget)
    finally:
        sys.stdout = old_stdout


