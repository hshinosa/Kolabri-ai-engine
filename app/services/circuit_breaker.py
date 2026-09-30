"""
Circuit Breaker Service
=======================
Implements circuit breaker pattern for preventing cascade failures
and improving system resilience.

Reference: https://martinfowler.com/bliki/CircuitBreaker.html
"""

from enum import Enum
from datetime import datetime
from typing import Optional, Callable, Any, Dict
import asyncio

from app.core.logging import get_logger
from app.core.config import settings

logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation, requests allowed
    OPEN = "open"          # Failing, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerError(Exception):
    """Base exception for circuit breaker."""
    pass


class CircuitBreakerOpenError(CircuitBreakerError):
    """Raised when circuit breaker is open and rejecting requests."""
    pass


class CircuitBreaker:
    """
    Circuit breaker implementation for service resilience.
    
    States:
    - CLOSED: Normal operation. Failures are counted.
    - OPEN: Circuit tripped. All requests fail immediately.
    - HALF_OPEN: Testing if service recovered. One request allowed.
    
    Transitions:
    - CLOSED → OPEN: When failure count reaches threshold
    - OPEN → HALF_OPEN: After recovery timeout
    - HALF_OPEN → CLOSED: After success count reaches threshold
    - HALF_OPEN → OPEN: On any failure
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,      # Failures before opening
        recovery_timeout: int = 60,       # Seconds before half-open
        success_threshold: int = 3,       # Successes before closing
        name: str = "default"
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting reset
            success_threshold: Number of successes before closing circuit
            name: Circuit breaker name for logging
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.name = name
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._lock = asyncio.Lock()
        
        # Metrics
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.rejected_calls = 0
        
        logger.info(
            "circuit_breaker_initialized",
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            success_threshold=success_threshold
        )
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state
    
    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (rejecting requests)."""
        return self._state == CircuitState.OPEN
    
    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing)."""
        return self._state == CircuitState.HALF_OPEN
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result from func
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: Any exception from func
        """
        self.total_calls += 1
        
        async with self._lock:
            # Check if circuit is open
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                else:
                    self.rejected_calls += 1
                    logger.warning(
                        "circuit_breaker_rejected",
                        name=self.name,
                        state=self._state.value
                    )
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is OPEN"
                    )
        
        try:
            # Execute function
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
            
        except Exception as e:
            await self._on_failure()
            # Re-raise with circuit breaker context
            if not isinstance(e, CircuitBreakerError):
                logger.error(
                    "circuit_breaker_call_failed",
                    name=self.name,
                    error=str(e)
                )
            raise
    
    async def _on_success(self):
        """Handle successful call."""
        async with self._lock:
            self.successful_calls += 1
            
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._transition_to_closed()
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0
    
    async def _on_failure(self):
        """Handle failed call."""
        async with self._lock:
            self.failed_calls += 1
            self._failure_count += 1
            self._last_failure_time = datetime.now()
            
            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open state opens the circuit
                self._transition_to_open(reason="failure_in_half_open")
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._transition_to_open(reason="threshold_reached")
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self._last_failure_time is None:
            return True
        
        time_since_failure = (datetime.now() - self._last_failure_time).total_seconds()
        return time_since_failure >= self.recovery_timeout
    
    def _transition_to_closed(self):
        """Transition to CLOSED state."""
        old_state = self._state
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        
        logger.info(
            "circuit_breaker_state_change",
            name=self.name,
            from_state=old_state.value,
            to_state="closed",
            reason="success_threshold_reached"
        )
    
    def _transition_to_open(self, reason: str):
        """Transition to OPEN state."""
        old_state = self._state
        self._state = CircuitState.OPEN
        self._success_count = 0
        
        logger.warning(
            "circuit_breaker_state_change",
            name=self.name,
            from_state=old_state.value,
            to_state="open",
            reason=reason,
            failure_count=self._failure_count
        )
    
    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state."""
        old_state = self._state
        self._state = CircuitState.HALF_OPEN
        self._success_count = 0
        
        logger.info(
            "circuit_breaker_state_change",
            name=self.name,
            from_state=old_state.value,
            to_state="half_open",
            reason="recovery_timeout_elapsed"
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get circuit breaker metrics."""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "rejected_calls": self.rejected_calls,
            "success_rate": self.successful_calls / self.total_calls if self.total_calls > 0 else 0
        }
    
    def reset(self):
        """Manually reset circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        
        logger.info("circuit_breaker_manually_reset", name=self.name)


# Singleton instance for LLM service
_llm_circuit_breaker: Optional[CircuitBreaker] = None

def get_llm_circuit_breaker() -> CircuitBreaker:
    """Get LLM circuit breaker singleton."""
    global _llm_circuit_breaker
    if _llm_circuit_breaker is None:
        _llm_circuit_breaker = CircuitBreaker(
            failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
            success_threshold=settings.CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
            name="llm_service"
        )
    return _llm_circuit_breaker
