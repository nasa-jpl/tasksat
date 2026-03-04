#!/usr/bin/env python3
"""
TaskNet Benchmark Runner

Runs all benchmarks in tests/tasknet_files/benchmark/ and collects:
- Scheduling result (SAT/UNSAT/TIMEOUT/ERROR)
- Timing data (validity checking, property verification, total)
- Property verification results (holds/violated/unknown)
- Mode (satisfy vs optimize)

Usage:
    python tools/run_benchmarks.py --output results/benchmark_results.json
    python tools/run_benchmarks.py --output results/benchmark_results.json --timeout 300 --mode satisfy
"""

import argparse
import csv
import json
import re
import subprocess
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class BenchmarkResult:
    """Result from running a single benchmark"""
    benchmark_name: str
    benchmark_path: str
    mode: str  # 'satisfy' or 'optimize'
    result: str  # 'SAT', 'UNSAT', 'TIMEOUT', 'ERROR'
    validity_time: Optional[float]
    property_time: Optional[float]
    total_time: float
    properties_hold: int
    properties_violated: int
    properties_unknown: int
    timeout: bool
    error_msg: Optional[str]


def parse_output(stdout: str, stderr: str) -> dict:
    """Parse verifier output to extract results and timing"""
    data = {
        'result': 'ERROR',
        'validity_time': None,
        'property_time': None,
        'total_time': None,
        'properties_hold': 0,
        'properties_violated': 0,
        'properties_unknown': 0,
        'error_msg': None
    }

    # Determine result type
    if "*** NEW SCHEDULE***" in stdout:
        data['result'] = 'SAT'
    elif "UNSAT" in stdout:
        data['result'] = 'UNSAT'
    elif stderr:
        data['result'] = 'ERROR'
        data['error_msg'] = stderr[:500]  # First 500 chars of error
        return data

    # Parse timing section
    # === Timing ===
    # Validity checking: 0.15 seconds
    # Property verification: 0.00 seconds
    # Total time: 0.27 seconds

    validity_match = re.search(r'Validity checking:\s+([\d.]+)\s+seconds', stdout)
    if validity_match:
        data['validity_time'] = float(validity_match.group(1))

    property_match = re.search(r'Property verification:\s+([\d.]+)\s+seconds', stdout)
    if property_match:
        data['property_time'] = float(property_match.group(1))

    total_match = re.search(r'Total time:\s+([\d.]+)\s+seconds', stdout)
    if total_match:
        data['total_time'] = float(total_match.group(1))

    # Parse property summary
    # Summary: 3 hold, 0 violated, 0 unknown
    summary_match = re.search(r'Summary:\s+(\d+)\s+hold,\s+(\d+)\s+violated,\s+(\d+)\s+unknown', stdout)
    if summary_match:
        data['properties_hold'] = int(summary_match.group(1))
        data['properties_violated'] = int(summary_match.group(2))
        data['properties_unknown'] = int(summary_match.group(3))

    return data


def run_benchmark(benchmark_path: Path, mode: str, timeout_sec: int = 300) -> BenchmarkResult:
    """Run a single benchmark with timeout"""
    benchmark_name = benchmark_path.stem

    cmd = [
        "python", "src/smt/tasknet_verifier.py",
        str(benchmark_path),
        "--mode", mode
    ]

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec
        )
        elapsed = time.time() - start_time

        # Parse output
        parsed = parse_output(result.stdout, result.stderr)

        return BenchmarkResult(
            benchmark_name=benchmark_name,
            benchmark_path=str(benchmark_path),
            mode=mode,
            result=parsed['result'],
            validity_time=parsed['validity_time'],
            property_time=parsed['property_time'],
            total_time=parsed['total_time'] or elapsed,
            properties_hold=parsed['properties_hold'],
            properties_violated=parsed['properties_violated'],
            properties_unknown=parsed['properties_unknown'],
            timeout=False,
            error_msg=parsed['error_msg']
        )

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        return BenchmarkResult(
            benchmark_name=benchmark_name,
            benchmark_path=str(benchmark_path),
            mode=mode,
            result="TIMEOUT",
            validity_time=None,
            property_time=None,
            total_time=elapsed,
            properties_hold=0,
            properties_violated=0,
            properties_unknown=0,
            timeout=True,
            error_msg=f"Exceeded {timeout_sec}s timeout"
        )

    except Exception as e:
        elapsed = time.time() - start_time
        return BenchmarkResult(
            benchmark_name=benchmark_name,
            benchmark_path=str(benchmark_path),
            mode=mode,
            result="ERROR",
            validity_time=None,
            property_time=None,
            total_time=elapsed,
            properties_hold=0,
            properties_violated=0,
            properties_unknown=0,
            timeout=False,
            error_msg=str(e)
        )


def find_benchmarks(benchmark_dir: Path) -> List[Path]:
    """Find all .tn files in benchmark directory"""
    if not benchmark_dir.exists():
        raise FileNotFoundError(f"Benchmark directory not found: {benchmark_dir}")

    benchmarks = sorted(benchmark_dir.glob("*.tn"))
    if not benchmarks:
        raise FileNotFoundError(f"No .tn files found in {benchmark_dir}")

    return benchmarks


def write_results(results: List[BenchmarkResult], output_path: Path):
    """Write results to JSON and CSV"""
    # Prepare data
    timestamp = datetime.now().isoformat()

    # Write JSON
    json_data = {
        "run_timestamp": timestamp,
        "total_benchmarks": len(results),
        "benchmarks": [asdict(r) for r in results]
    }

    json_path = output_path
    with open(json_path, 'w') as f:
        json.dump(json_data, f, indent=2)

    print(f"Results written to {json_path}")

    # Write CSV
    csv_path = json_path.with_suffix('.csv')
    with open(csv_path, 'w', newline='') as f:
        if results:
            writer = csv.DictWriter(f, fieldnames=asdict(results[0]).keys())
            writer.writeheader()
            for result in results:
                writer.writerow(asdict(result))

    print(f"Results written to {csv_path}")


def print_summary(results: List[BenchmarkResult]):
    """Print summary statistics"""
    total = len(results)
    sat = sum(1 for r in results if r.result == 'SAT')
    unsat = sum(1 for r in results if r.result == 'UNSAT')
    timeout = sum(1 for r in results if r.result == 'TIMEOUT')
    error = sum(1 for r in results if r.result == 'ERROR')

    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Total benchmarks: {total}")
    print(f"  SAT:     {sat:3d} ({sat/total*100:5.1f}%)")
    print(f"  UNSAT:   {unsat:3d} ({unsat/total*100:5.1f}%)")
    print(f"  TIMEOUT: {timeout:3d} ({timeout/total*100:5.1f}%)")
    print(f"  ERROR:   {error:3d} ({error/total*100:5.1f}%)")

    # Average times for successful runs
    successful = [r for r in results if r.result in ['SAT', 'UNSAT'] and r.total_time]
    if successful:
        avg_time = sum(r.total_time for r in successful) / len(successful)
        print(f"\nAverage time (successful): {avg_time:.2f}s")

    # Show timeouts
    if timeout > 0:
        print(f"\nBenchmarks that timed out:")
        for r in results:
            if r.result == 'TIMEOUT':
                print(f"  - {r.benchmark_name} ({r.mode} mode)")

    # Show errors
    if error > 0:
        print(f"\nBenchmarks with errors:")
        for r in results:
            if r.result == 'ERROR':
                print(f"  - {r.benchmark_name} ({r.mode} mode)")
                if r.error_msg:
                    print(f"    {r.error_msg[:100]}")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='Run TaskNet benchmarks and collect results',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all benchmarks with 5-minute timeout
  python tools/run_benchmarks.py --output results/benchmark_results.json

  # Run only satisfy mode with shorter timeout
  python tools/run_benchmarks.py --output results/results.json --mode satisfy --timeout 60

  # Run specific benchmark directory
  python tools/run_benchmarks.py --output results/results.json --benchmark-dir tests/tasknet_files/stress
        """
    )

    parser.add_argument('--output', '-o', type=str, required=True,
                       help='Output file path (JSON)')
    parser.add_argument('--timeout', type=int, default=300,
                       help='Timeout per benchmark in seconds (default: 300)')
    parser.add_argument('--mode', choices=['both', 'satisfy', 'optimize'],
                       default='both',
                       help='Which mode(s) to test (default: both)')
    parser.add_argument('--benchmark-dir', type=str,
                       default='tests/tasknet_files/benchmark',
                       help='Directory containing benchmarks (default: tests/tasknet_files/benchmark)')

    args = parser.parse_args()

    # Setup
    benchmark_dir = Path(args.benchmark_dir)
    output_path = Path(args.output)

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Find benchmarks
    print(f"Finding benchmarks in {benchmark_dir}...")
    benchmarks = find_benchmarks(benchmark_dir)
    print(f"Found {len(benchmarks)} benchmark(s)")

    # Determine modes to run
    modes = ['satisfy', 'optimize'] if args.mode == 'both' else [args.mode]

    total_runs = len(benchmarks) * len(modes)
    print(f"Running {total_runs} total runs ({len(benchmarks)} benchmarks × {len(modes)} mode(s))")
    print(f"Timeout: {args.timeout}s per benchmark")
    print()

    # Run benchmarks
    results = []
    start_time = time.time()

    for idx, bench_path in enumerate(benchmarks, 1):
        for mode in modes:
            run_num = (idx - 1) * len(modes) + modes.index(mode) + 1
            print(f"[{run_num}/{total_runs}] Running {bench_path.name} ({mode} mode)...", flush=True)

            result = run_benchmark(bench_path, mode, timeout_sec=args.timeout)
            results.append(result)

            # Print result
            status_icon = {
                'SAT': '✓',
                'UNSAT': '✓',
                'TIMEOUT': '⏱',
                'ERROR': '✗'
            }.get(result.result, '?')

            time_str = f"{result.total_time:.2f}s" if result.total_time else "N/A"
            print(f"  {status_icon} {result.result} in {time_str}")

            # Show property stats if any
            if result.properties_hold + result.properties_violated + result.properties_unknown > 0:
                print(f"    Properties: {result.properties_hold} hold, "
                      f"{result.properties_violated} violated, "
                      f"{result.properties_unknown} unknown")

    total_elapsed = time.time() - start_time
    print(f"\nTotal execution time: {total_elapsed:.1f}s ({total_elapsed/60:.1f} minutes)")

    # Write results
    print()
    write_results(results, output_path)

    # Print summary
    print_summary(results)


if __name__ == '__main__':
    main()
