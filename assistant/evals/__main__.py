#!/usr/bin/env python3
"""CLI runner for evals: python -m evals [options]"""
import argparse
import sys
import uuid
from datetime import datetime
from typing import Callable, List, Optional

from .framework import EvalCase, EvalResult, EvalRunner, EvalStore
from .cases import ALL_CASES, BASIC_CASES, SAFETY_CASES, TOOL_CASES


def create_server_llm_fn(base_url: str = "http://127.0.0.1:8080") -> Callable[[str], str]:
    """Create LLM function that calls the assistant server API."""
    import httpx

    def llm_fn(message: str) -> str:
        response = httpx.post(
            f"{base_url}/api/chat",
            json={"message": message},
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()["response"]

    return llm_fn


def get_cases_by_filter(
    tags: Optional[List[str]] = None,
    names: Optional[List[str]] = None,
    preset: Optional[str] = None,
) -> List[EvalCase]:
    """Filter cases by tags, names, or preset."""
    if preset:
        presets = {
            "all": ALL_CASES,
            "basic": BASIC_CASES,
            "safety": SAFETY_CASES,
            "tools": TOOL_CASES,
        }
        return presets.get(preset, ALL_CASES)

    if names:
        return [c for c in ALL_CASES if c.name in names]

    if tags:
        return [c for c in ALL_CASES if any(t in c.tags for t in tags)]

    return ALL_CASES


def print_results(results: List[EvalResult], verbose: bool = False) -> tuple[int, int]:
    """Print eval results. Returns (passed, total)."""
    passed = 0
    total = len(results)

    for result in results:
        status = "\033[32mPASS\033[0m" if result.passed else "\033[31mFAIL\033[0m"
        print(f"[{status}] {result.case_name} (score: {result.score:.2f}, latency: {result.latency_ms:.0f}ms)")

        if verbose or not result.passed:
            for cr in result.criteria_results:
                cr_status = "\033[32m✓\033[0m" if cr["passed"] else "\033[31m✗\033[0m"
                print(f"      {cr_status} {cr['reason']}")
            if verbose and result.actual_output:
                output_preview = result.actual_output[:200]
                if len(result.actual_output) > 200:
                    output_preview += "..."
                print(f"      Output: {output_preview}")

        if result.passed:
            passed += 1

    return passed, total


def print_summary(passed: int, total: int):
    """Print summary line."""
    color = "\033[32m" if passed == total else "\033[31m"
    print(f"\n{color}Results: {passed}/{total} passed ({100*passed/total if total else 0:.0f}%)\033[0m")


def list_cases():
    """List all available eval cases."""
    print("Available eval cases:")
    print("-" * 60)
    for case in ALL_CASES:
        tags_str = ", ".join(case.tags) if case.tags else "none"
        print(f"  {case.name}")
        print(f"    Tags: {tags_str}")
        print(f"    {case.description}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Run AI assistant evals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m evals --list              # List all available cases
  python -m evals                     # Run all cases
  python -m evals --preset basic      # Run basic cases only
  python -m evals --tags safety       # Run cases with 'safety' tag
  python -m evals --case basic_greeting math_basic  # Run specific cases
  python -m evals --verbose           # Show detailed output
  python -m evals --save              # Save results to database
"""
    )

    parser.add_argument("--list", "-l", action="store_true",
                        help="List available eval cases")
    parser.add_argument("--preset", "-p", choices=["all", "basic", "safety", "tools"],
                        help="Run preset group of cases")
    parser.add_argument("--tags", "-t", nargs="+",
                        help="Filter by tags (runs cases with any matching tag)")
    parser.add_argument("--case", "-c", nargs="+", dest="cases",
                        help="Run specific cases by name")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed output for all cases")
    parser.add_argument("--save", "-s", action="store_true",
                        help="Save results to eval database")
    parser.add_argument("--url", default="http://127.0.0.1:8080",
                        help="Assistant server URL (default: http://127.0.0.1:8080)")
    parser.add_argument("--run-id",
                        help="Custom run ID for grouping results (auto-generated if not provided)")

    args = parser.parse_args()

    if args.list:
        list_cases()
        return 0

    # Get cases to run
    cases = get_cases_by_filter(
        tags=args.tags,
        names=args.cases,
        preset=args.preset,
    )

    if not cases:
        print("No matching eval cases found.")
        return 1

    # Create LLM function
    print(f"Connecting to assistant at {args.url}...")
    try:
        llm_fn = create_server_llm_fn(args.url)
        # Quick connectivity check
        import httpx
        httpx.get(f"{args.url}/api/health", timeout=5.0).raise_for_status()
    except Exception as e:
        print(f"\033[31mError: Could not connect to assistant server: {e}\033[0m")
        print("Make sure the assistant is running: python -m server.main")
        return 1

    print(f"Running {len(cases)} eval case(s)...\n")

    # Run evals
    runner = EvalRunner(llm_fn, model_name="assistant-api")
    results = runner.run_cases(cases)

    # Print results
    passed, total = print_results(results, verbose=args.verbose)
    print_summary(passed, total)

    # Save results if requested
    if args.save:
        run_id = args.run_id or f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        store = EvalStore()
        store.save_results(results, run_id=run_id)
        print(f"\nResults saved to database (run_id: {run_id})")

    # Return exit code based on results
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
