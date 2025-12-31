# solve_tasknet.py
import argparse
from pprint import pprint
from tasknet_parser import parse_tasknet_file
from tasknet_smt import TaskNetSMT, TaskNetTL

def main(path: str, mode: str = 'plan'):
    print('\n\n\n\n\n\n\n*** NEW SCHEDULE***\n')
    tn = parse_tasknet_file(path)
    use_optimization = (mode == 'plan')
    enc = TaskNetTL(tn, error_trace=True, use_optimization=use_optimization)
    m = enc.solve()
    if m is None:
        print("UNSAT: No valid schedule found!")
        return
    enc.pretty_print(m)
    enc.check_temporal_properties()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TaskNet Scheduler and Verifier')
    parser.add_argument('tasknet_file', help='Path to .tn file')
    parser.add_argument('--mode', choices=['plan', 'verify'], default='plan',
                        help='Mode: plan (optimize schedule) or verify (any valid schedule)')
    args = parser.parse_args()
    main(args.tasknet_file, args.mode)


