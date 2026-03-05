"""Tests for retry utilities."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from agent0.retry import CircuitBreaker, parse_rate_limit_headers, retry_with_backoff


class TestRetryWithBackoff:

    @pytest.mark.asyncio
    async def test_succeeds_first_try(self):
        func = AsyncMock(return_value='ok')
        result = await retry_with_backoff(func, max_retries=3)
        assert result == 'ok'
        assert func.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        func = AsyncMock(side_effect=[ValueError('fail'), 'ok'])
        result = await retry_with_backoff(func, max_retries=3, base_delay=0.01)
        assert result == 'ok'
        assert func.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_exhaustion(self):
        func = AsyncMock(side_effect=ValueError('always fails'))
        with pytest.raises(ValueError, match='always fails'):
            await retry_with_backoff(func, max_retries=2, base_delay=0.01)
        assert func.call_count == 2

    def test_max_retries_zero_raises(self):
        with pytest.raises(ValueError, match='max_retries must be >= 1'):
            asyncio.get_event_loop().run_until_complete(
                retry_with_backoff(AsyncMock(), max_retries=0)
            )


class TestParseRateLimitHeaders:

    def test_parses_valid_headers(self):
        headers = {
            'X-RateLimit-Remaining': '4999',
            'X-RateLimit-Limit': '5000',
            'X-RateLimit-Reset': '1700000000',
        }
        result = parse_rate_limit_headers(headers)
        assert result['remaining'] == 4999
        assert result['limit'] == 5000
        assert result['reset'] == 1700000000

    def test_missing_headers_return_none(self):
        result = parse_rate_limit_headers({})
        assert result['remaining'] is None
        assert result['limit'] is None
        assert result['reset'] is None


class TestCircuitBreaker:

    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.can_proceed() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_time=60)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == 'open'
        assert cb.can_proceed() is False

    def test_half_open_after_recovery(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_time=0)
        cb.record_failure()
        assert cb.state == 'open'
        # recovery_time=0 means immediately eligible
        time.sleep(0.01)
        assert cb.can_proceed() is True
        assert cb.state == 'half-open'
        # Second call in half-open should be blocked
        assert cb.can_proceed() is False

    def test_success_closes_from_half_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_time=0)
        cb.record_failure()
        time.sleep(0.01)
        cb.can_proceed()  # transitions to half-open
        cb.record_success()
        assert cb.state == 'closed'
        assert cb.can_proceed() is True
