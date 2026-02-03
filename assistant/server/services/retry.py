"""Retry utilities for handling transient failures."""
import asyncio
import functools
import logging
import random
from typing import Callable, Type, Tuple, Optional

logger = logging.getLogger(__name__)

# Default retryable exceptions
RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
):
    """
    Decorator for retrying functions with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 30.0)
        exponential_base: Base for exponential backoff (default: 2.0)
        jitter: Add randomness to delay (default: True)
        retryable_exceptions: Tuple of exception types to retry on
        on_retry: Callback function(exception, attempt) called before retry

    Returns:
        Decorated function with retry logic
    """
    if retryable_exceptions is None:
        retryable_exceptions = RETRYABLE_EXCEPTIONS

    def decorator(func: Callable):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(
                        base_delay * (exponential_base ** (attempt - 1)),
                        max_delay
                    )

                    # Add jitter (0.5 to 1.5 of calculated delay)
                    if jitter:
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    if on_retry:
                        on_retry(e, attempt)

                    await asyncio.sleep(delay)

            # Should not reach here, but just in case
            raise last_exception

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise

                    delay = min(
                        base_delay * (exponential_base ** (attempt - 1)),
                        max_delay
                    )

                    if jitter:
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    if on_retry:
                        on_retry(e, attempt)

                    import time
                    time.sleep(delay)

            raise last_exception

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Pre-configured retry decorators for common use cases

def api_retry(func: Callable):
    """
    Retry decorator optimized for API calls.

    Retries on:
    - Connection errors
    - Timeout errors
    - Rate limit errors (via HTTP status codes)
    """
    # Import here to avoid circular imports and handle missing packages
    try:
        from openai import RateLimitError as OpenAIRateLimitError
        from openai import APIConnectionError as OpenAIConnectionError
        from openai import APITimeoutError as OpenAITimeoutError
    except ImportError:
        OpenAIRateLimitError = Exception
        OpenAIConnectionError = Exception
        OpenAITimeoutError = Exception

    try:
        from anthropic import RateLimitError as AnthropicRateLimitError
        from anthropic import APIConnectionError as AnthropicConnectionError
        from anthropic import APITimeoutError as AnthropicTimeoutError
    except ImportError:
        AnthropicRateLimitError = Exception
        AnthropicConnectionError = Exception
        AnthropicTimeoutError = Exception

    api_exceptions = (
        ConnectionError,
        TimeoutError,
        OSError,
        OpenAIRateLimitError,
        OpenAIConnectionError,
        OpenAITimeoutError,
        AnthropicRateLimitError,
        AnthropicConnectionError,
        AnthropicTimeoutError,
    )

    return with_retry(
        max_attempts=3,
        base_delay=1.0,
        max_delay=30.0,
        retryable_exceptions=api_exceptions,
    )(func)
