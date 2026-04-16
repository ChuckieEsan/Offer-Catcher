"""断路器装饰器模块

底层服务由 infrastructure/common/circuit_breaker 提供。
此模块仅提供向后兼容的导入转发。
"""

from aiobreaker.state import CircuitOpenState, CircuitClosedState, CircuitHalfOpenState

from app.infrastructure.common.circuit_breaker import (
    circuit_breaker,
    CircuitBreakerOpenError,
    create_circuit_breaker,
    get_circuit_breaker,
    reset_circuit_breaker,
    list_circuit_breakers,
)

__all__ = [
    "circuit_breaker",
    "CircuitBreakerOpenError",
    "create_circuit_breaker",
    "get_circuit_breaker",
    "reset_circuit_breaker",
    "list_circuit_breakers",
    # aiobreaker states
    "CircuitOpenState",
    "CircuitClosedState",
    "CircuitHalfOpenState",
]