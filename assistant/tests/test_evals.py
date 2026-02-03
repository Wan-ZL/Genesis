"""Tests for the eval framework."""
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from evals.framework import (
    CriteriaType,
    EvalCase,
    EvalCriterion,
    EvalResult,
    EvalRunner,
    EvalStore,
    evaluate_criterion,
)
from evals.cases import (
    BASIC_CASES,
    GREETING_EVAL,
    MATH_QUESTION_EVAL,
    SAFETY_CASES,
    contains,
    not_contains,
    regex,
)


# ============================================================================
# CRITERIA EVALUATION TESTS
# ============================================================================

class TestEvaluateCriterion:
    """Tests for evaluate_criterion function."""

    def test_contains_pass(self):
        """Contains criterion should pass when string is present."""
        criterion = EvalCriterion(CriteriaType.CONTAINS, "hello")
        passed, reason = evaluate_criterion("Hello world!", criterion)
        assert passed is True
        assert "Contains" in reason

    def test_contains_fail(self):
        """Contains criterion should fail when string is missing."""
        criterion = EvalCriterion(CriteriaType.CONTAINS, "goodbye")
        passed, reason = evaluate_criterion("Hello world!", criterion)
        assert passed is False
        assert "Missing" in reason

    def test_contains_case_insensitive(self):
        """Contains should be case-insensitive."""
        criterion = EvalCriterion(CriteriaType.CONTAINS, "HELLO")
        passed, _ = evaluate_criterion("hello world", criterion)
        assert passed is True

    def test_not_contains_pass(self):
        """Not contains should pass when string is absent."""
        criterion = EvalCriterion(CriteriaType.NOT_CONTAINS, "error")
        passed, _ = evaluate_criterion("Everything is fine!", criterion)
        assert passed is True

    def test_not_contains_fail(self):
        """Not contains should fail when string is present."""
        criterion = EvalCriterion(CriteriaType.NOT_CONTAINS, "error")
        passed, _ = evaluate_criterion("An error occurred", criterion)
        assert passed is False

    def test_regex_pass(self):
        """Regex criterion should pass on match."""
        criterion = EvalCriterion(CriteriaType.REGEX, r"\d{2}:\d{2}")
        passed, _ = evaluate_criterion("The time is 14:30", criterion)
        assert passed is True

    def test_regex_fail(self):
        """Regex criterion should fail when no match."""
        criterion = EvalCriterion(CriteriaType.REGEX, r"\d{2}:\d{2}")
        passed, _ = evaluate_criterion("No time here", criterion)
        assert passed is False

    def test_custom_pass(self):
        """Custom criterion with passing function."""
        criterion = EvalCriterion(
            CriteriaType.CUSTOM,
            lambda x: len(x) > 5,
            description="Output must be longer than 5 chars"
        )
        passed, _ = evaluate_criterion("This is long enough", criterion)
        assert passed is True

    def test_custom_fail(self):
        """Custom criterion with failing function."""
        criterion = EvalCriterion(
            CriteriaType.CUSTOM,
            lambda x: len(x) > 100,
        )
        passed, _ = evaluate_criterion("Short", criterion)
        assert passed is False

    def test_custom_error_handling(self):
        """Custom criterion should handle exceptions."""
        def bad_fn(x):
            raise ValueError("Oops")

        criterion = EvalCriterion(CriteriaType.CUSTOM, bad_fn)
        passed, reason = evaluate_criterion("test", criterion)
        assert passed is False
        assert "error" in reason.lower()


# ============================================================================
# EVAL CASE TESTS
# ============================================================================

class TestEvalCase:
    """Tests for EvalCase class."""

    def test_case_to_dict(self):
        """EvalCase should serialize to dict."""
        case = EvalCase(
            name="test_case",
            input_message="Hello",
            criteria=[contains("hi")],
            description="Test",
            tags=["basic"],
        )
        d = case.to_dict()
        assert d["name"] == "test_case"
        assert d["criteria_count"] == 1
        assert d["tags"] == ["basic"]

    def test_predefined_cases_valid(self):
        """All predefined cases should have required fields."""
        for case in BASIC_CASES + SAFETY_CASES:
            assert case.name, "Case must have name"
            assert case.input_message, "Case must have input"
            assert len(case.criteria) > 0, "Case must have criteria"


# ============================================================================
# EVAL RUNNER TESTS
# ============================================================================

class TestEvalRunner:
    """Tests for EvalRunner class."""

    def test_run_case_all_pass(self):
        """Runner should return pass when all criteria pass."""
        def mock_llm(msg):
            return "Hello! The answer is 105."

        runner = EvalRunner(mock_llm, model_name="test-model")
        case = EvalCase(
            name="test",
            input_message="Hi, what is 15*7?",
            criteria=[contains("hello"), contains("105")],
        )
        result = runner.run_case(case)

        assert result.passed is True
        assert result.score == 1.0
        assert result.model == "test-model"
        assert len(result.criteria_results) == 2

    def test_run_case_partial_pass(self):
        """Runner should return partial score when some criteria fail."""
        def mock_llm(msg):
            return "The answer is 42."

        runner = EvalRunner(mock_llm)
        case = EvalCase(
            name="test",
            input_message="Test",
            criteria=[
                contains("answer"),  # pass
                contains("correct"),  # fail
            ],
        )
        result = runner.run_case(case)

        assert result.passed is False  # Not all passed
        assert result.score == 0.5  # 1/2 criteria passed

    def test_run_case_with_weights(self):
        """Runner should respect criterion weights."""
        def mock_llm(msg):
            return "Hello"

        runner = EvalRunner(mock_llm)
        case = EvalCase(
            name="test",
            input_message="Test",
            criteria=[
                EvalCriterion(CriteriaType.CONTAINS, "hello", weight=3.0),  # pass
                EvalCriterion(CriteriaType.CONTAINS, "goodbye", weight=1.0),  # fail
            ],
        )
        result = runner.run_case(case)

        assert result.score == 0.75  # 3/(3+1) = 0.75

    def test_run_case_tracks_latency(self):
        """Runner should track response latency."""
        def slow_llm(msg):
            import time
            time.sleep(0.05)  # 50ms
            return "Response"

        runner = EvalRunner(slow_llm)
        case = EvalCase(name="test", input_message="Test", criteria=[contains("response")])
        result = runner.run_case(case)

        assert result.latency_ms >= 50  # At least 50ms

    def test_run_case_handles_llm_error(self):
        """Runner should handle LLM errors gracefully."""
        def error_llm(msg):
            raise RuntimeError("API failed")

        runner = EvalRunner(error_llm)
        case = EvalCase(name="test", input_message="Test", criteria=[contains("hello")])
        result = runner.run_case(case)

        assert result.passed is False
        assert "ERROR" in result.actual_output

    def test_run_multiple_cases(self):
        """Runner should run multiple cases."""
        def mock_llm(msg):
            return "Hello, the time is 12:30"

        runner = EvalRunner(mock_llm)
        results = runner.run_cases([GREETING_EVAL, MATH_QUESTION_EVAL])

        assert len(results) == 2
        # Greeting should pass, math should fail (no 105)
        assert results[0].passed is True  # Has "hello"


# ============================================================================
# EVAL STORE TESTS
# ============================================================================

class TestEvalStore:
    """Tests for EvalStore persistence."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test_evals.db"

    def test_store_creation(self, temp_db):
        """Store should create database and tables."""
        store = EvalStore(temp_db)
        assert temp_db.exists()

        # Check table exists
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='eval_results'"
            )
            assert cursor.fetchone() is not None

    def test_save_and_retrieve_result(self, temp_db):
        """Store should save and retrieve results."""
        store = EvalStore(temp_db)

        result = EvalResult(
            case_name="test_case",
            passed=True,
            score=1.0,
            actual_output="Hello world",
            criteria_results=[{"type": "contains", "passed": True}],
            model="gpt-4",
            latency_ms=150.0,
        )

        row_id = store.save_result(result, run_id="run-001")
        assert row_id > 0

        rows = store.get_results(case_name="test_case")
        assert len(rows) == 1
        assert rows[0]["case_name"] == "test_case"
        assert rows[0]["passed"] == 1
        assert rows[0]["run_id"] == "run-001"

    def test_save_multiple_results(self, temp_db):
        """Store should save multiple results."""
        store = EvalStore(temp_db)

        results = [
            EvalResult("case1", True, 1.0, "out1", []),
            EvalResult("case2", False, 0.5, "out2", []),
        ]

        ids = store.save_results(results, run_id="run-002")
        assert len(ids) == 2

        rows = store.get_results(run_id="run-002")
        assert len(rows) == 2

    def test_pass_rate_calculation(self, temp_db):
        """Store should calculate pass rate correctly."""
        store = EvalStore(temp_db)

        # Save 3 passes and 1 fail
        for passed in [True, True, True, False]:
            store.save_result(EvalResult("test", passed, 1.0 if passed else 0.0, "", []))

        rate = store.get_pass_rate(case_name="test", last_n=4)
        assert rate == 0.75  # 3/4

    def test_pass_rate_empty(self, temp_db):
        """Pass rate should be 0 for no results."""
        store = EvalStore(temp_db)
        rate = store.get_pass_rate(case_name="nonexistent")
        assert rate == 0.0


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""

    def test_contains_helper(self):
        """contains() should create correct criterion."""
        c = contains("test", weight=2.0, desc="Test desc")
        assert c.type == CriteriaType.CONTAINS
        assert c.value == "test"
        assert c.weight == 2.0
        assert c.description == "Test desc"

    def test_not_contains_helper(self):
        """not_contains() should create correct criterion."""
        c = not_contains("error")
        assert c.type == CriteriaType.NOT_CONTAINS
        assert c.value == "error"

    def test_regex_helper(self):
        """regex() should create correct criterion."""
        c = regex(r"\d+")
        assert c.type == CriteriaType.REGEX
        assert c.value == r"\d+"
