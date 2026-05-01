from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import circuit_breaker
from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    get_all_circuit_breakers_status,
    get_circuit_breaker,
)


@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    circuit_breaker._circuit_breakers.clear()
    yield
    circuit_breaker._circuit_breakers.clear()


@pytest.mark.asyncio
async def test_call_returns_result_when_closed():
    breaker = CircuitBreaker("svc")
    func = AsyncMock(return_value="ok")

    result = await breaker.call(func, 1, key="value")

    assert result == "ok"
    func.assert_awaited_once_with(1, key="value")
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


@pytest.mark.asyncio
async def test_call_records_failures_and_opens_after_threshold():
    breaker = CircuitBreaker("svc", CircuitBreakerConfig(failure_threshold=2))
    func = AsyncMock(side_effect=RuntimeError("fail"))

    with pytest.raises(RuntimeError):
        await breaker.call(func)
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 1

    with pytest.raises(RuntimeError):
        await breaker.call(func)
    assert breaker.state == CircuitState.OPEN
    assert breaker.failure_count == 2


@pytest.mark.asyncio
async def test_call_raises_open_error_when_circuit_is_open():
    breaker = CircuitBreaker("svc")
    breaker.state = CircuitState.OPEN

    with patch.object(breaker, "_check_state_transition", new=AsyncMock()), pytest.raises(
        CircuitBreakerOpenError,
        match="OPEN",
    ):
        await breaker.call(AsyncMock())


@pytest.mark.asyncio
async def test_open_transitions_to_half_open_after_timeout():
    config = CircuitBreakerConfig(timeout=5)
    breaker = CircuitBreaker("svc", config)
    breaker.state = CircuitState.OPEN
    breaker.last_failure_time = 10.0

    with patch("app.core.circuit_breaker.time.time", return_value=20.0):
        await breaker._check_state_transition()

    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker.half_open_calls == 0
    assert breaker.success_count == 0


@pytest.mark.asyncio
async def test_open_stays_open_before_timeout_expires():
    config = CircuitBreakerConfig(timeout=15)
    breaker = CircuitBreaker("svc", config)
    breaker.state = CircuitState.OPEN
    breaker.last_failure_time = 10.0

    with patch("app.core.circuit_breaker.time.time", return_value=20.0):
        await breaker._check_state_transition()

    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_half_open_call_limit_blocks_extra_calls():
    config = CircuitBreakerConfig(half_open_max_calls=1)
    breaker = CircuitBreaker("svc", config)
    breaker.state = CircuitState.HALF_OPEN
    breaker.half_open_calls = 1

    with patch.object(breaker, "_check_state_transition", new=AsyncMock()), pytest.raises(
        CircuitBreakerOpenError,
        match="half-open limit reached",
    ):
        await breaker.call(AsyncMock())


@pytest.mark.asyncio
async def test_half_open_successes_close_circuit():
    config = CircuitBreakerConfig(success_threshold=2)
    breaker = CircuitBreaker("svc", config)
    breaker.state = CircuitState.HALF_OPEN
    breaker.failure_count = 3

    await breaker._record_success()
    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker.success_count == 1

    await breaker._record_success()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0
    assert breaker.success_count == 0
    assert breaker.half_open_calls == 0


@pytest.mark.asyncio
async def test_success_in_closed_state_resets_failure_count():
    breaker = CircuitBreaker("svc")
    breaker.failure_count = 4

    await breaker._record_success()

    assert breaker.failure_count == 0
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_failure_in_half_open_reopens_circuit():
    breaker = CircuitBreaker("svc")
    breaker.state = CircuitState.HALF_OPEN
    breaker.half_open_calls = 1

    with patch("app.core.circuit_breaker.time.time", return_value=123.0):
        await breaker._record_failure()

    assert breaker.state == CircuitState.OPEN
    assert breaker.failure_count == 1
    assert breaker.last_failure_time == 123.0
    assert breaker.half_open_calls == 0


@pytest.mark.asyncio
async def test_protect_decorator_routes_through_call():
    breaker = CircuitBreaker("svc")

    @breaker.protect
    async def protected(value):
        return value * 2

    result = await protected(5)

    assert result == 10


def test_get_status_returns_state_and_config():
    config = CircuitBreakerConfig(failure_threshold=7, success_threshold=4, timeout=12)
    breaker = CircuitBreaker("svc", config)
    breaker.state = CircuitState.HALF_OPEN
    breaker.failure_count = 2
    breaker.success_count = 1
    breaker.last_failure_time = 99.0
    breaker.half_open_calls = 1

    status = breaker.get_status()

    assert status["name"] == "svc"
    assert status["state"] == "half_open"
    assert status["failure_count"] == 2
    assert status["config"]["failure_threshold"] == 7
    assert status["config"]["success_threshold"] == 4
    assert status["config"]["timeout"] == 12


@pytest.mark.asyncio
async def test_force_open_sets_open_state_and_timestamp():
    breaker = CircuitBreaker("svc")

    with patch("app.core.circuit_breaker.time.time", return_value=555.0):
        await breaker.force_open()

    assert breaker.state == CircuitState.OPEN
    assert breaker.last_failure_time == 555.0


@pytest.mark.asyncio
async def test_force_close_resets_state_counters():
    breaker = CircuitBreaker("svc")
    breaker.state = CircuitState.OPEN
    breaker.failure_count = 5
    breaker.success_count = 2
    breaker.half_open_calls = 1

    await breaker.force_close()

    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0
    assert breaker.success_count == 0
    assert breaker.half_open_calls == 0


def test_get_circuit_breaker_returns_singleton_per_name():
    config = CircuitBreakerConfig(failure_threshold=2)

    first = get_circuit_breaker("svc", config)
    second = get_circuit_breaker("svc")

    assert first is second
    assert second.config.failure_threshold == 2


def test_get_all_circuit_breakers_status_returns_all_entries():
    first = get_circuit_breaker("svc-a")
    second = get_circuit_breaker("svc-b")
    first.state = CircuitState.OPEN
    second.state = CircuitState.HALF_OPEN

    statuses = get_all_circuit_breakers_status()

    assert set(statuses.keys()) == {"svc-a", "svc-b"}
    assert statuses["svc-a"]["state"] == "open"
    assert statuses["svc-b"]["state"] == "half_open"
