"""Tests for retry utilities."""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import time

from server.services.retry import with_retry, api_retry


class TestWithRetry:
    """Tests for with_retry decorator."""

    @pytest.mark.asyncio
    async def test_async_success_no_retry(self):
        """Successful async function should not retry."""
        call_count = 0

        @with_retry(max_attempts=3)
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_func()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_retry_on_connection_error(self):
        """Should retry on ConnectionError."""
        call_count = 0

        @with_retry(max_attempts=3, base_delay=0.01)
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            return "success"

        result = await flaky_func()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_max_attempts_exhausted(self):
        """Should raise after max attempts exhausted."""
        call_count = 0

        @with_retry(max_attempts=3, base_delay=0.01)
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Always fails")

        with pytest.raises(ConnectionError):
            await always_fails()
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_non_retryable_exception(self):
        """Non-retryable exceptions should not trigger retry."""
        call_count = 0

        @with_retry(max_attempts=3, retryable_exceptions=(ConnectionError,))
        async def raises_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not retryable")

        with pytest.raises(ValueError):
            await raises_value_error()
        assert call_count == 1  # No retry

    def test_sync_success_no_retry(self):
        """Successful sync function should not retry."""
        call_count = 0

        @with_retry(max_attempts=3)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_func()
        assert result == "success"
        assert call_count == 1

    def test_sync_retry_on_timeout(self):
        """Should retry on TimeoutError."""
        call_count = 0

        @with_retry(max_attempts=3, base_delay=0.01)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("Timed out")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Verify exponential backoff delays."""
        delays = []
        call_count = 0

        @with_retry(
            max_attempts=4,
            base_delay=0.1,
            exponential_base=2.0,
            jitter=False  # Disable jitter for predictable timing
        )
        async def always_fails():
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                delays.append(time.time())
            raise ConnectionError("Network error")

        start = time.time()
        delays.insert(0, start)

        with pytest.raises(ConnectionError):
            await always_fails()

        # Check delays increase exponentially (roughly)
        # Expected: 0.1, 0.2, 0.4
        if len(delays) >= 3:
            actual_delays = [delays[i+1] - delays[i] for i in range(len(delays)-1)]
            # Allow some tolerance
            assert actual_delays[0] >= 0.05  # ~0.1
            assert actual_delays[1] >= 0.1   # ~0.2
            assert actual_delays[2] >= 0.2   # ~0.4

    @pytest.mark.asyncio
    async def test_on_retry_callback(self):
        """Test on_retry callback is called."""
        callback_calls = []

        def on_retry(exc, attempt):
            callback_calls.append((str(exc), attempt))

        @with_retry(max_attempts=3, base_delay=0.01, on_retry=on_retry)
        async def flaky_func():
            if len(callback_calls) < 2:
                raise ConnectionError("Network error")
            return "success"

        result = await flaky_func()
        assert result == "success"
        assert len(callback_calls) == 2
        assert callback_calls[0][1] == 1  # First attempt
        assert callback_calls[1][1] == 2  # Second attempt

    @pytest.mark.asyncio
    async def test_max_delay_cap(self):
        """Verify delay is capped at max_delay."""
        call_count = 0

        @with_retry(
            max_attempts=5,
            base_delay=1.0,
            max_delay=0.1,  # Very short max
            exponential_base=10.0,  # Would cause large delays without cap
            jitter=False
        )
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Network error")

        start = time.time()
        with pytest.raises(ConnectionError):
            await always_fails()
        elapsed = time.time() - start

        # Should complete relatively quickly due to max_delay cap
        # 4 delays of max 0.1s each = 0.4s max
        assert elapsed < 1.0


class TestApiRetry:
    """Tests for api_retry decorator."""

    @pytest.mark.asyncio
    async def test_api_retry_success(self):
        """api_retry should work for successful calls."""
        @api_retry
        async def api_call():
            return {"status": "ok"}

        result = await api_call()
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_api_retry_connection_error(self):
        """api_retry should retry on ConnectionError."""
        call_count = 0

        @api_retry
        async def flaky_api():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Network issue")
            return {"status": "ok"}

        # Patch asyncio.sleep to avoid actual delays
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await flaky_api()

        assert result == {"status": "ok"}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_api_retry_timeout_error(self):
        """api_retry should retry on TimeoutError."""
        call_count = 0

        @api_retry
        async def slow_api():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("Request timed out")
            return {"status": "ok"}

        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await slow_api()

        assert result == {"status": "ok"}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_api_retry_preserves_function_metadata(self):
        """api_retry should preserve function name and docstring."""
        @api_retry
        async def my_api_function():
            """This is my API function."""
            return True

        assert my_api_function.__name__ == "my_api_function"
        assert "This is my API function" in my_api_function.__doc__


class TestRetryWithMockedAPIs:
    """Integration tests with mocked API client errors."""

    @pytest.mark.asyncio
    async def test_openai_rate_limit_retry(self):
        """Should retry on OpenAI rate limit errors."""
        try:
            from openai import RateLimitError
        except ImportError:
            pytest.skip("openai not installed")

        call_count = 0

        @api_retry
        async def call_openai():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                # Create a mock response for RateLimitError
                raise RateLimitError(
                    message="Rate limit exceeded",
                    response=Mock(status_code=429),
                    body={"error": {"message": "Rate limit exceeded"}}
                )
            return "success"

        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await call_openai()

        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_anthropic_rate_limit_retry(self):
        """Should retry on Anthropic rate limit errors."""
        try:
            from anthropic import RateLimitError
        except ImportError:
            pytest.skip("anthropic not installed")

        call_count = 0

        @api_retry
        async def call_anthropic():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RateLimitError(
                    message="Rate limit exceeded",
                    response=Mock(status_code=429),
                    body={"error": {"message": "Rate limit exceeded"}}
                )
            return "success"

        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await call_anthropic()

        assert result == "success"
        assert call_count == 2
