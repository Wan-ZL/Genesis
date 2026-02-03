"""Core eval framework for testing LLM behavior."""
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, List, Dict, Optional, Union

# Default database path
DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "evals.db"


class CriteriaType(Enum):
    """Types of evaluation criteria."""
    CONTAINS = "contains"  # Output must contain string
    NOT_CONTAINS = "not_contains"  # Output must not contain string
    REGEX = "regex"  # Output must match regex
    CUSTOM = "custom"  # Custom function evaluates output


@dataclass
class EvalCriterion:
    """Single criterion for evaluating output."""
    type: CriteriaType
    value: Union[str, Callable[[str], bool]]
    weight: float = 1.0
    description: str = ""


@dataclass
class EvalCase:
    """An evaluation case with input and expected criteria."""
    name: str
    input_message: str
    criteria: List[EvalCriterion]
    description: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "name": self.name,
            "input_message": self.input_message,
            "description": self.description,
            "tags": self.tags,
            "criteria_count": len(self.criteria),
        }


@dataclass
class EvalResult:
    """Result of running an eval case."""
    case_name: str
    passed: bool
    score: float  # 0.0 to 1.0
    actual_output: str
    criteria_results: List[Dict[str, Any]]  # Per-criterion results
    timestamp: datetime = field(default_factory=datetime.now)
    model: str = ""
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "case_name": self.case_name,
            "passed": self.passed,
            "score": self.score,
            "actual_output": self.actual_output,
            "criteria_results": json.dumps(self.criteria_results),
            "timestamp": self.timestamp.isoformat(),
            "model": self.model,
            "latency_ms": self.latency_ms,
        }


def evaluate_criterion(output: str, criterion: EvalCriterion) -> tuple[bool, str]:
    """Evaluate a single criterion against output.

    Returns (passed, reason).
    """
    output_lower = output.lower()

    if criterion.type == CriteriaType.CONTAINS:
        value_lower = criterion.value.lower() if isinstance(criterion.value, str) else ""
        passed = value_lower in output_lower
        reason = f"Contains '{criterion.value}'" if passed else f"Missing '{criterion.value}'"
        return passed, reason

    elif criterion.type == CriteriaType.NOT_CONTAINS:
        value_lower = criterion.value.lower() if isinstance(criterion.value, str) else ""
        passed = value_lower not in output_lower
        reason = f"Does not contain '{criterion.value}'" if passed else f"Unexpectedly contains '{criterion.value}'"
        return passed, reason

    elif criterion.type == CriteriaType.REGEX:
        if isinstance(criterion.value, str):
            pattern = re.compile(criterion.value, re.IGNORECASE | re.DOTALL)
            passed = pattern.search(output) is not None
            reason = f"Matches regex" if passed else f"Does not match regex '{criterion.value}'"
            return passed, reason
        return False, "Invalid regex value"

    elif criterion.type == CriteriaType.CUSTOM:
        if callable(criterion.value):
            try:
                passed = criterion.value(output)
                reason = criterion.description if criterion.description else ("Custom check passed" if passed else "Custom check failed")
                return passed, reason
            except Exception as e:
                return False, f"Custom check error: {e}"
        return False, "Invalid custom function"

    return False, f"Unknown criteria type: {criterion.type}"


class EvalRunner:
    """Runs eval cases against an LLM."""

    def __init__(self, llm_fn: Callable[[str], str], model_name: str = ""):
        """Initialize with LLM function.

        Args:
            llm_fn: Function that takes input message and returns output
            model_name: Name of the model being evaluated
        """
        self.llm_fn = llm_fn
        self.model_name = model_name

    def run_case(self, case: EvalCase) -> EvalResult:
        """Run a single eval case."""
        import time

        start = time.time()
        try:
            output = self.llm_fn(case.input_message)
        except Exception as e:
            output = f"ERROR: {e}"
        latency_ms = (time.time() - start) * 1000

        criteria_results = []
        total_weight = 0.0
        weighted_score = 0.0

        for criterion in case.criteria:
            passed, reason = evaluate_criterion(output, criterion)
            criteria_results.append({
                "type": criterion.type.value,
                "passed": passed,
                "reason": reason,
                "weight": criterion.weight,
            })
            total_weight += criterion.weight
            if passed:
                weighted_score += criterion.weight

        score = weighted_score / total_weight if total_weight > 0 else 0.0
        passed = score >= 1.0  # All criteria must pass for overall pass

        return EvalResult(
            case_name=case.name,
            passed=passed,
            score=score,
            actual_output=output,
            criteria_results=criteria_results,
            model=self.model_name,
            latency_ms=latency_ms,
        )

    def run_cases(self, cases: List[EvalCase]) -> List[EvalResult]:
        """Run multiple eval cases."""
        return [self.run_case(case) for case in cases]


class EvalStore:
    """Stores eval results in SQLite for tracking over time."""

    def __init__(self, db_path: Union[Path, str, None] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS eval_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_name TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    score REAL NOT NULL,
                    actual_output TEXT,
                    criteria_results TEXT,
                    timestamp TEXT NOT NULL,
                    model TEXT,
                    latency_ms REAL,
                    run_id TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_case_name ON eval_results(case_name)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON eval_results(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_run_id ON eval_results(run_id)
            """)
            conn.commit()

    def save_result(self, result: EvalResult, run_id: str = "") -> int:
        """Save a single result. Returns row ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO eval_results
                (case_name, passed, score, actual_output, criteria_results, timestamp, model, latency_ms, run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.case_name,
                1 if result.passed else 0,
                result.score,
                result.actual_output,
                json.dumps(result.criteria_results),
                result.timestamp.isoformat(),
                result.model,
                result.latency_ms,
                run_id,
            ))
            conn.commit()
            return cursor.lastrowid or 0

    def save_results(self, results: List[EvalResult], run_id: str = "") -> List[int]:
        """Save multiple results. Returns row IDs."""
        return [self.save_result(r, run_id) for r in results]

    def get_results(
        self,
        case_name: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query stored results."""
        query = "SELECT * FROM eval_results WHERE 1=1"
        params: List[Any] = []

        if case_name:
            query += " AND case_name = ?"
            params.append(case_name)
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_pass_rate(self, case_name: Optional[str] = None, last_n: int = 10) -> float:
        """Get pass rate for last N runs."""
        query = "SELECT passed FROM eval_results WHERE 1=1"
        params: List[Any] = []

        if case_name:
            query += " AND case_name = ?"
            params.append(case_name)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(last_n)

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            if not rows:
                return 0.0
            return sum(r[0] for r in rows) / len(rows)
