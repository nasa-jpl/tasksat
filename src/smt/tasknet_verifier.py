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

def write_transformed_tasknet(tn, output_path: str):
    """Write the transformed tasknet to a file for inspection."""
    import json
    from pathlib import Path

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

    print(f"📄 Transformed tasknet written to: {output_path}\n")

def main(path: str, mode: str = 'optimize', write_transformed: str = None):
    print('\n\n\n\n\n\n\n*** NEW SCHEDULE***\n')

    start_time = time.time()

    tn = parse_tasknet_file(path)

    # Apply AST transformations (desugar derived constructs)
    tn = apply_transforms(tn)

    # Optionally write transformed tasknet
    if write_transformed:
        write_transformed_tasknet(tn, write_transformed)

    # Check well-formedness before solving
    if not check_wellformedness(tn):
        return  # Errors already printed by checker

    use_optimization = (mode == 'optimize')
    enc = TaskNetTL(tn, error_trace=True, use_optimization=use_optimization)

    # Phase 1: Validity checking
    validity_start = time.time()
    m = enc.solve()
    validity_end = time.time()

    if m is None:
        print("UNSAT: No valid schedule found!")
        print(f"\n=== Timing ===")
        print(f"Validity checking: {validity_end - validity_start:.2f} seconds")
        print(f"Total time: {validity_end - start_time:.2f} seconds")
        return

    enc.pretty_print(m)

    # Phase 2: Property verification
    property_start = time.time()
    enc.check_temporal_properties()
    property_end = time.time()

    end_time = time.time()

    print(f"\n=== Timing ===")
    print(f"Validity checking: {validity_end - validity_start:.2f} seconds")
    print(f"Property verification: {property_end - property_start:.2f} seconds")

    # Add average time per property if properties exist
    num_properties = len(tn.properties) if hasattr(tn, 'properties') and tn.properties else 0
    if num_properties > 0:
        avg_time_per_property = (property_end - property_start) / num_properties
        print(f"Average per property: {avg_time_per_property:.2f} seconds ({num_properties} properties)")

    print(f"Total time: {end_time - start_time:.2f} seconds")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TaskNet Scheduler and Verifier')
    parser.add_argument('tasknet_file', help='Path to .tn file')
    parser.add_argument('--mode', choices=['optimize', 'satisfy'], default='optimize',
                        help='Mode for main schedule generation: optimize (use Optimize solver for best schedule) or satisfy (use Solver for any valid schedule). Property verification always uses Solver for faster counterexample finding.')
    parser.add_argument('--write-transformed', metavar='FILE',
                        help='Write transformed tasknet (after auto-instantiation) to JSON file for inspection')
    args = parser.parse_args()
    main(args.tasknet_file, args.mode, args.write_transformed)


