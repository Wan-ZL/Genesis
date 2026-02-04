"""
Benchmark Framework for Regression Detection

Provides utilities for storing benchmark results and detecting performance regressions.
Results are stored in assistant/memory/benchmarks/ as JSON files.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict


# Default threshold for regression detection (20%)
REGRESSION_THRESHOLD_PERCENT = 20.0


@dataclass
class BenchmarkResult:
    """A single benchmark measurement."""
    name: str
    mean_ms: float  # Mean execution time in milliseconds
    stddev_ms: float  # Standard deviation in milliseconds
    min_ms: float
    max_ms: float
    rounds: int  # Number of iterations
    timestamp: str
    git_commit: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BenchmarkResult":
        return cls(**data)


@dataclass
class RegressionReport:
    """Report of a potential performance regression."""
    benchmark_name: str
    baseline_mean_ms: float
    current_mean_ms: float
    percent_change: float
    is_regression: bool
    threshold_percent: float


class BenchmarkStore:
    """Stores and retrieves benchmark results for regression detection."""

    def __init__(self, storage_dir: Optional[Path] = None):
        if storage_dir is None:
            # Default to assistant/memory/benchmarks/
            storage_dir = Path(__file__).parent.parent / "memory" / "benchmarks"
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Baseline file stores the "golden" baseline performance
        self.baseline_file = self.storage_dir / "baseline.json"
        # History file stores all benchmark runs
        self.history_file = self.storage_dir / "history.json"

    def _get_git_commit(self) -> Optional[str]:
        """Get current git commit hash."""
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent.parent
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def save_results(self, results: list[BenchmarkResult]) -> None:
        """Save benchmark results to history."""
        history = self._load_history()

        run_entry = {
            "timestamp": datetime.now().isoformat(),
            "git_commit": self._get_git_commit(),
            "results": [r.to_dict() for r in results]
        }

        history.append(run_entry)

        # Keep only last 100 runs
        if len(history) > 100:
            history = history[-100:]

        with open(self.history_file, "w") as f:
            json.dump(history, f, indent=2)

    def _load_history(self) -> list:
        """Load benchmark history."""
        if self.history_file.exists():
            with open(self.history_file) as f:
                return json.load(f)
        return []

    def set_baseline(self, results: list[BenchmarkResult]) -> None:
        """Set current results as the baseline."""
        baseline = {
            "timestamp": datetime.now().isoformat(),
            "git_commit": self._get_git_commit(),
            "results": {r.name: r.to_dict() for r in results}
        }

        with open(self.baseline_file, "w") as f:
            json.dump(baseline, f, indent=2)

    def get_baseline(self) -> Optional[dict[str, BenchmarkResult]]:
        """Get baseline results."""
        if not self.baseline_file.exists():
            return None

        with open(self.baseline_file) as f:
            data = json.load(f)

        return {
            name: BenchmarkResult.from_dict(result)
            for name, result in data["results"].items()
        }

    def check_regressions(
        self,
        current_results: list[BenchmarkResult],
        threshold_percent: float = REGRESSION_THRESHOLD_PERCENT
    ) -> list[RegressionReport]:
        """
        Check for performance regressions against baseline.

        Returns a list of RegressionReport objects for each benchmark.
        A regression is flagged if the current mean is more than threshold_percent
        slower than the baseline.
        """
        baseline = self.get_baseline()
        if not baseline:
            return []

        reports = []
        for result in current_results:
            if result.name not in baseline:
                continue

            baseline_result = baseline[result.name]

            # Calculate percent change (positive = slower = regression)
            if baseline_result.mean_ms > 0:
                percent_change = (
                    (result.mean_ms - baseline_result.mean_ms)
                    / baseline_result.mean_ms
                ) * 100
            else:
                percent_change = 0.0

            is_regression = percent_change > threshold_percent

            reports.append(RegressionReport(
                benchmark_name=result.name,
                baseline_mean_ms=baseline_result.mean_ms,
                current_mean_ms=result.mean_ms,
                percent_change=percent_change,
                is_regression=is_regression,
                threshold_percent=threshold_percent
            ))

        return reports

    def get_latest_results(self) -> Optional[list[BenchmarkResult]]:
        """Get the most recent benchmark results."""
        history = self._load_history()
        if not history:
            return None

        latest = history[-1]
        return [BenchmarkResult.from_dict(r) for r in latest["results"]]


def format_regression_report(reports: list[RegressionReport]) -> str:
    """Format regression reports for human-readable output."""
    if not reports:
        return "No baseline to compare against. Run with --save-baseline to set one."

    lines = ["Performance Regression Report", "=" * 40]

    regressions = [r for r in reports if r.is_regression]
    improvements = [r for r in reports if r.percent_change < -10]  # 10% faster
    stable = [r for r in reports if not r.is_regression and r.percent_change >= -10]

    if regressions:
        lines.append(f"\n[REGRESSIONS] ({len(regressions)} found)")
        for r in regressions:
            lines.append(
                f"  - {r.benchmark_name}: {r.baseline_mean_ms:.3f}ms -> "
                f"{r.current_mean_ms:.3f}ms ({r.percent_change:+.1f}%)"
            )

    if improvements:
        lines.append(f"\n[IMPROVEMENTS] ({len(improvements)} found)")
        for r in improvements:
            lines.append(
                f"  + {r.benchmark_name}: {r.baseline_mean_ms:.3f}ms -> "
                f"{r.current_mean_ms:.3f}ms ({r.percent_change:+.1f}%)"
            )

    if stable:
        lines.append(f"\n[STABLE] ({len(stable)} benchmarks)")
        for r in stable:
            lines.append(
                f"  = {r.benchmark_name}: {r.current_mean_ms:.3f}ms ({r.percent_change:+.1f}%)"
            )

    return "\n".join(lines)
