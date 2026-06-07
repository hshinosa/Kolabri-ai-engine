"""
Circuit Breaker Pattern
=======================

Implementasi Circuit Breaker untuk:
1. Mencegah cascading failures saat service down
2. Automatic recovery detection
3. Graceful degradation

Status:
- CLOSED: Normal operation (requests allowed)
- OPEN: Circuit breaker active (requests blocked)
- HALF_OPEN: Testing if service recovered

Issue: KOL-42 - High Performance Targets
"""

import asyncio
import time
from typing import Callable, Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass
from functools import wraps

from app.core.logging import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit breaker active
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5          # Failures before opening
    success_threshold: int = 3          # Successes to close from half-open
    timeout: float = 60.0               # Time before attempting recovery
    half_open_max_calls: int = 3        # Max calls in half-open state


class CircuitBreaker:
    """
    Circuit breaker untuk mencegah cascading failures.
    
    Usage:
        @circuit_breaker.protect
        async def my_function():
            # Your code here
            pass
    """
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.half_open_calls = 0
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Call function dengan circuit breaker protection.
        
        Returns:
            Function result
        
        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: Original exception dari function
        """
        async with self._lock:
            # Check state transitions
            await self._check_state_transition()
            
            if self.state == CircuitState.OPEN:
                logger.warning(
                    "circuit_breaker_open",
                    name=self.name,
                    failure_count=self.failure_count
                )
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is OPEN"
                )
            
            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' half-open limit reached"
                    )
                self.half_open_calls += 1
        
        # Execute function
        try:
            result = await func(*args, **kwargs)
            await self._record_success()
            return result
        except Exception:
            await self._record_failure()
            raise
    
    def protect(self, func: Callable) -> Callable:
        """Decorator untuk protect function dengan circuit breaker."""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await self.call(func, *args, **kwargs)
        return wrapper
    
    async def _check_state_transition(self):
        """Check dan handle state transitions."""
        if self.state == CircuitState.OPEN:
            # Check if timeout expired -> transition to half-open
            if time.time() - self.last_failure_time >= self.config.timeout:
                logger.info(
                    "circuit_breaker_half_open",
                    name=self.name,
                    open_duration=time.time() - self.last_failure_time
                )
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                self.success_count = 0
    
    async def _record_success(self):
        """Record successful call."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                
                # Check if can close circuit
                if self.success_count >= self.config.success_threshold:
                    logger.info(
                        "circuit_breaker_closed",
                        name=self.name,
                        success_count=self.success_count
                    )
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    self.half_open_calls = 0
            else:
                # Reset failure count in closed state
                self.failure_count = 0
    
    async def _record_failure(self):
        """Record failed call."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == CircuitState.HALF_OPEN:
                # Back to open
                logger.warning(
                    "circuit_breaker_open_from_half",
                    name=self.name,
                    failure_count=self.failure_count
                )
                self.state = CircuitState.OPEN
                self.half_open_calls = 0
                
            elif self.state == CircuitState.CLOSED:
                # Check if should open
                if self.failure_count >= self.config.failure_threshold:
                    logger.warning(
                        "circuit_breaker_open",
                        name=self.name,
                        failure_count=self.failure_count,
                        threshold=self.config.failure_threshold
                    )
                    self.state = CircuitState.OPEN
    
    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "half_open_calls": self.half_open_calls,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout": self.config.timeout,
            }
        }
    
    async def force_open(self):
        """Force circuit breaker to open (untuk maintenance)."""
        async with self._lock:
            self.state = CircuitState.OPEN
            self.last_failure_time = time.time()
            logger.info("circuit_breaker_forced_open", name=self.name)
    
    async def force_close(self):
        """Force circuit breaker to close (recovery)."""
        async with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.half_open_calls = 0
            logger.info("circuit_breaker_forced_closed", name=self.name)


class CircuitBreakerOpenError(Exception):
    """Exception raised saat circuit breaker is open."""
    pass


# Global circuit breakers
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, config: CircuitBreakerConfig = None) -> CircuitBreaker:
    """Get atau create circuit breaker."""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, config)
    return _circuit_breakers[name]


def get_all_circuit_breakers_status() -> Dict[str, Dict[str, Any]]:
    """Get status dari semua circuit breakers."""
    return {name: cb.get_status() for name, cb in _circuit_breakers.items()}
