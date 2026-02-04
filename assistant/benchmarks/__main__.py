"""
CLI runner for benchmarks.

Usage:
    # Run all benchmarks
    python -m benchmarks

    # Run with baseline comparison
    python -m benchmarks --compare

    # Save results as new baseline
    python -m benchmarks --save-baseline

    # Run specific benchmark file
    python -m benchmarks --file test_bench_memory.py

    # Show historical results
    python -m benchmarks --history
"""

import argparse
import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime

from .framework import (
    BenchmarkStore,
    BenchmarkResult,
    format_regression_report,
    REGRESSION_THRESHOLD_PERCENT,
)


def parse_benchmark_json(json_output: str) -> list[BenchmarkResult]:
    """Parse pytest-benchmark JSON output into BenchmarkResult objects."""
    try:
        data = json.loads(json_output)
        results = []

        for bench in data.get("benchmarks", []):
            # Convert seconds to milliseconds
            mean_ms = bench["stats"]["mean"] * 1000
            stddev_ms = bench["stats"]["stddev"] * 1000
            min_ms = bench["stats"]["min"] * 1000
            max_ms = bench["stats"]["max"] * 1000

            results.append(BenchmarkResult(
                name=bench["name"],
                mean_ms=mean_ms,
                stddev_ms=stddev_ms,
                min_ms=min_ms,
                max_ms=max_ms,
                rounds=bench["stats"]["rounds"],
                timestamp=datetime.now().isoformat()
            ))

        return results
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Warning: Could not parse benchmark output: {e}")
        return []


def run_benchmarks(file_filter: str = None, json_output: bool = True) -> tuple[int, list[BenchmarkResult]]:
    """Run pytest benchmarks and return results."""
    benchmarks_dir = Path(__file__).parent

    cmd = [
        sys.executable, "-m", "pytest",
        "--benchmark-only",
        "--benchmark-disable-gc",
        "-v"
    ]

    if json_output:
        # Write JSON to temp file
        json_file = benchmarks_dir.parent / "memory" / "benchmarks" / "latest.json"
        json_file.parent.mkdir(parents=True, exist_ok=True)
        cmd.extend(["--benchmark-json", str(json_file)])

    if file_filter:
        cmd.append(str(benchmarks_dir / file_filter))
    else:
        cmd.append(str(benchmarks_dir))

    print(f"Running: {' '.join(cmd)}")
    print("-" * 60)

    result = subprocess.run(cmd, cwd=benchmarks_dir.parent)

    results = []
    if json_output and json_file.exists():
        with open(json_file) as f:
            results = parse_benchmark_json(f.read())

    return result.returncode, results


def main():
    parser = argparse.ArgumentParser(description="Run performance benchmarks")
    parser.add_argument("--file", "-f", help="Run specific benchmark file")
    parser.add_argument("--compare", "-c", action="store_true",
                        help="Compare results against baseline")
    parser.add_argument("--save-baseline", "-s", action="store_true",
                        help="Save current results as baseline")
    parser.add_argument("--history", "-H", action="store_true",
                        help="Show benchmark history")
    parser.add_argument("--threshold", "-t", type=float,
                        default=REGRESSION_THRESHOLD_PERCENT,
                        help=f"Regression threshold percentage (default: {REGRESSION_THRESHOLD_PERCENT})")
    parser.add_argument("--ci", action="store_true",
                        help="CI mode: fail if regressions detected")

    args = parser.parse_args()

    store = BenchmarkStore()

    if args.history:
        history = store._load_history()
        if not history:
            print("No benchmark history found.")
            return 0

        print("Benchmark History")
        print("=" * 60)
        for i, run in enumerate(history[-10:]):  # Last 10 runs
            print(f"\n[{run['timestamp']}] Commit: {run.get('git_commit', 'unknown')}")
            for result in run["results"][:5]:  # First 5 results
                print(f"  {result['name']}: {result['mean_ms']:.3f}ms")
        return 0

    # Run benchmarks
    returncode, results = run_benchmarks(args.file)

    if not results:
        print("\nNo benchmark results collected.")
        return returncode

    # Save to history
    store.save_results(results)

    # Save as baseline if requested
    if args.save_baseline:
        store.set_baseline(results)
        print(f"\nBaseline saved with {len(results)} benchmarks.")

    # Compare against baseline if requested
    if args.compare or args.ci:
        reports = store.check_regressions(results, args.threshold)
        print("\n" + format_regression_report(reports))

        # In CI mode, fail if regressions found
        if args.ci:
            regressions = [r for r in reports if r.is_regression]
            if regressions:
                print(f"\n{len(regressions)} REGRESSIONS DETECTED!")
                return 1

    return returncode


if __name__ == "__main__":
    sys.exit(main())
