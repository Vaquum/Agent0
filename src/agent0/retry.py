"""Retry utilities for Agent0."""

import asyncio
import logging
import time
from typing import Any, Callable

log = logging.getLogger(__name__)


async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> Any:
    """Retry an async function with exponential backoff.

    Args:
        func: Async callable to retry
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds between retries
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            last_error = e
            delay = base_delay * (2 ** attempt)
            log.warning('Attempt %d failed: %s, retrying in %ds', attempt, e, delay)
            await asyncio.sleep(delay)
    raise last_error


def parse_rate_limit_headers(headers: dict) -> dict:
    """Parse GitHub rate limit headers.

    Returns dict with remaining, limit, and reset timestamp.
    """
    def _int_or_none(val: str | None) -> int | None:
        return int(val) if val is not None else None

    return {
        'remaining': _int_or_none(headers.get('X-RateLimit-Remaining')),
        'limit': _int_or_none(headers.get('X-RateLimit-Limit')),
        'reset': _int_or_none(headers.get('X-RateLimit-Reset')),
    }


class CircuitBreaker:
    """Simple circuit breaker for external service calls."""

    def __init__(self, failure_threshold: int = 5, recovery_time: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failures = 0
        self.last_failure_time = None
        self.state = 'closed'  # closed = healthy, open = broken

    def record_failure(self) -> None:
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = 'open'

    def record_success(self) -> None:
        self.failures = 0
        self.state = 'closed'

    def can_proceed(self) -> bool:
        if self.state == 'closed':
            return True
        # Bug: no half-open state — once open, checks time but never transitions back
        elapsed = time.time() - self.last_failure_time
        if elapsed > self.recovery_time:
            return True
        return False
