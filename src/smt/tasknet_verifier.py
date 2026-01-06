# solve_tasknet.py
import argparse
from pprint import pprint
from tasknet_parser import parse_tasknet_file
from tasknet_smt import TaskNetSMT, TaskNetTL
from tasknet_wellformedness import check_wellformedness

def main(path: str, mode: str = 'optimize'):
    print('\n\n\n\n\n\n\n*** NEW SCHEDULE***\n')
    tn = parse_tasknet_file(path)

    # Check well-formedness before solving
    if not check_wellformedness(tn):
        return  # Errors already printed by checker

    use_optimization = (mode == 'optimize')
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
    parser.add_argument('--mode', choices=['optimize', 'satisfy'], default='optimize',
                        help='Mode: optimize (use Optimize solver) or satisfy (use Solver for any valid schedule)')
    args = parser.parse_args()
    main(args.tasknet_file, args.mode)


