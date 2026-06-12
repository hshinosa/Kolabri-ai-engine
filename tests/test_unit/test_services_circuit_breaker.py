"""Tests for app/services/circuit_breaker.py"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta

from app.services.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerError,
    CircuitBreakerOpenError,
)


@pytest.fixture
def cb():
    return CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=5,
        success_threshold=2,
        name="test_cb"
    )


class TestCircuitBreakerInit:
    def test_initial_state_closed(self, cb):
        assert cb.state == CircuitState.CLOSED
        assert cb.is_closed is True
        assert cb.is_open is False
        assert cb.is_half_open is False
    
    def test_initial_metrics_zero(self, cb):
        assert cb.total_calls == 0
        assert cb.successful_calls == 0
        assert cb.failed_calls == 0
        assert cb.rejected_calls == 0
    
    def test_custom_thresholds(self):
        cb = CircuitBreaker(failure_threshold=10, recovery_timeout=30, success_threshold=5)
        assert cb.failure_threshold == 10
        assert cb.recovery_timeout == 30
        assert cb.success_threshold == 5


class TestCircuitBreakerClosedState:
    @pytest.mark.asyncio
    async def test_successful_call(self, cb):
        func = AsyncMock(return_value="result")
        result = await cb.call(func)
        
        assert result == "result"
        assert cb.total_calls == 1
        assert cb.successful_calls == 1
        assert cb.is_closed is True
    
    @pytest.mark.asyncio
    async def test_failure_increments_count(self, cb):
        func = AsyncMock(side_effect=ValueError("fail"))
        
        with pytest.raises(ValueError):
            await cb.call(func)
        
        assert cb.failed_calls == 1
        assert cb._failure_count == 1
        assert cb.is_closed is True
    
    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self, cb):
        fail_func = AsyncMock(side_effect=ValueError("fail"))
        ok_func = AsyncMock(return_value="ok")
        
        with pytest.raises(ValueError):
            await cb.call(fail_func)
        with pytest.raises(ValueError):
            await cb.call(fail_func)
        
        assert cb._failure_count == 2
        
        await cb.call(ok_func)
        assert cb._failure_count == 0
    
    @pytest.mark.asyncio
    async def test_threshold_reached_opens_circuit(self, cb):
        func = AsyncMock(side_effect=RuntimeError("down"))
        
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(func)
        
        assert cb.is_open is True
        assert cb._failure_count == 3


class TestCircuitBreakerOpenState:
    @pytest.mark.asyncio
    async def test_rejects_calls_when_open(self, cb):
        func = AsyncMock(side_effect=RuntimeError("down"))
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(func)
        
        assert cb.is_open is True
        
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(AsyncMock())
        
        assert cb.rejected_calls == 1
    
    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(self, cb):
        func = AsyncMock(side_effect=RuntimeError("down"))
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(func)
        
        assert cb.is_open is True
        
        cb._last_failure_time = datetime.now() - timedelta(seconds=10)
        
        ok_func = AsyncMock(return_value="recovered")
        result = await cb.call(ok_func)
        
        assert result == "recovered"


class TestCircuitBreakerHalfOpenState:
    @pytest.mark.asyncio
    async def test_success_in_half_open_increments(self, cb):
        cb._state = CircuitState.HALF_OPEN
        cb._success_count = 0
        
        func = AsyncMock(return_value="ok")
        await cb.call(func)
        
        assert cb._success_count == 1
    
    @pytest.mark.asyncio
    async def test_success_threshold_closes_circuit(self, cb):
        cb._state = CircuitState.HALF_OPEN
        cb._success_count = 0
        
        func = AsyncMock(return_value="ok")
        await cb.call(func)
        await cb.call(func)
        
        assert cb.is_closed is True
        assert cb._failure_count == 0
        assert cb._success_count == 0
    
    @pytest.mark.asyncio
    async def test_failure_in_half_open_reopens(self, cb):
        cb._state = CircuitState.HALF_OPEN
        cb._success_count = 1
        
        func = AsyncMock(side_effect=RuntimeError("still down"))
        with pytest.raises(RuntimeError):
            await cb.call(func)
        
        assert cb.is_open is True


class TestCircuitBreakerMetrics:
    @pytest.mark.asyncio
    async def test_get_metrics(self, cb):
        func = AsyncMock(return_value="ok")
        await cb.call(func)
        
        metrics = cb.get_metrics()
        assert metrics["name"] == "test_cb"
        assert metrics["state"] == "closed"
        assert metrics["total_calls"] == 1
        assert metrics["successful_calls"] == 1
        assert metrics["failed_calls"] == 0
        assert metrics["rejected_calls"] == 0
        assert metrics["success_rate"] == 1.0
    
    @pytest.mark.asyncio
    async def test_success_rate_zero_calls(self, cb):
        metrics = cb.get_metrics()
        assert metrics["success_rate"] == 0


class TestCircuitBreakerReset:
    @pytest.mark.asyncio
    async def test_manual_reset(self, cb):
        func = AsyncMock(side_effect=RuntimeError("down"))
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(func)
        
        assert cb.is_open is True
        
        cb.reset()
        
        assert cb.is_closed is True
        assert cb._failure_count == 0
        assert cb._success_count == 0
        assert cb._last_failure_time is None


class TestCircuitBreakerShouldAttemptReset:
    def test_no_last_failure(self, cb):
        cb._last_failure_time = None
        assert cb._should_attempt_reset() is True
    
    def test_timeout_not_elapsed(self, cb):
        cb._last_failure_time = datetime.now()
        assert cb._should_attempt_reset() is False
    
    def test_timeout_elapsed(self, cb):
        cb._last_failure_time = datetime.now() - timedelta(seconds=10)
        assert cb._should_attempt_reset() is True


    def test_should_attempt_reset_false_within_timeout(self, cb):
        from datetime import datetime, timedelta

        cb._last_failure_time = datetime.now() - timedelta(seconds=1)
        cb.recovery_timeout = 300
        assert cb._should_attempt_reset() is False


class TestCircuitBreakerOpenStateBranches:
    @pytest.mark.asyncio
    async def test_on_success_when_open_skips_closed_reset(self, cb):
        from app.services.circuit_breaker import CircuitState

        cb._state = CircuitState.OPEN
        cb._failure_count = 3
        await cb._on_success()
        assert cb._failure_count == 3

    @pytest.mark.asyncio
    async def test_on_failure_when_open_skips_closed_threshold(self, cb):
        from app.services.circuit_breaker import CircuitState

        cb._state = CircuitState.OPEN
        await cb._on_failure()
        assert cb._state == CircuitState.OPEN


class TestGetLLMCircuitBreaker:
    def test_singleton(self):
        import app.services.circuit_breaker as module
        module._llm_circuit_breaker = None
        
        cb1 = module.get_llm_circuit_breaker()
        cb2 = module.get_llm_circuit_breaker()
        assert cb1 is cb2
        assert cb1.name == "llm_service"
        
        module._llm_circuit_breaker = None
