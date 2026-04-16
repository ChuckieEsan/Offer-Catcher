"""断路器装饰器模块

基于 aiobreaker 实现的断路器模式，用于防止连续失败导致的级联故障。
作为基础设施层通用组件，为所有层提供熔断保护。

工作原理：
- 连续失败达到阈值后，断路器打开（open），后续调用直接返回失败
- 超过恢复超时时间后，断路器进入半开状态（half-open），允许一次尝试
- 如果尝试成功，断路器关闭（closed）；如果失败，重新打开

Example:
    @circuit_breaker(fail_max=5, timeout_duration=30)
    def my_function():
        # 可能失败的代码
        pass
"""

import functools
import inspect
from datetime import timedelta
from typing import Callable, Optional, Type, Tuple, Any

import aiobreaker
from aiobreaker.state import CircuitOpenState

from app.infrastructure.common.logger import logger


# 全局断路器字典
_breakers: dict[str, aiobreaker.CircuitBreaker] = {}


def create_circuit_breaker(
    fail_max: int = 5,
    timeout_duration: float = 30.0,
    name: str = "default",
    exclude_exceptions: Tuple[Type[Exception], ...] = (),
) -> aiobreaker.CircuitBreaker:
    """创建或获取断路器实例

    Args:
        fail_max: 连续失败次数阈值，默认 5
        timeout_duration: 恢复超时时间（秒），默认 30
        name: 断路器名称
        exclude_exceptions: 排除的异常类型

    Returns:
        断路器实例
    """
    if name not in _breakers:
        _breakers[name] = aiobreaker.CircuitBreaker(
            fail_max=fail_max,
            timeout_duration=timedelta(seconds=timeout_duration),
            exclude=exclude_exceptions,
        )
        logger.info(
            f"Circuit breaker '{name}' created: "
            f"fail_max={fail_max}, timeout_duration={timeout_duration}s"
        )
    return _breakers[name]


def circuit_breaker(
    fail_max: int = 5,
    timeout_duration: float = 30.0,
    name: Optional[str] = None,
    exclude_exceptions: Tuple[Type[Exception], ...] = (),
    state_callback: Optional[Callable[[aiobreaker.CircuitBreaker], None]] = None,
):
    """断路器装饰器

    Args:
        fail_max: 连续失败次数阈值，默认 5
        timeout_duration: 恢复超时时间（秒），默认 30
        name: 断路器名称，默认使用函数名
        exclude_exceptions: 排除的异常类型
        state_callback: 断路器状态变更时的回调函数
    """

    def decorator(func: Callable) -> Callable:
        breaker_name = name or func.__name__

        if breaker_name not in _breakers:
            _breakers[breaker_name] = aiobreaker.CircuitBreaker(
                fail_max=fail_max,
                timeout_duration=timedelta(seconds=timeout_duration),
                exclude=exclude_exceptions,
            )

            if state_callback:
                _breakers[breaker_name].call_success = state_callback
                _breakers[breaker_name].call_failure = state_callback

            logger.info(
                f"Circuit breaker '{breaker_name}' created: "
                f"fail_max={fail_max}, timeout_duration={timeout_duration}s"
            )

        breaker = _breakers[breaker_name]

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if isinstance(breaker.state, CircuitOpenState):
                logger.warning(f"Circuit breaker '{breaker_name}' is OPEN, call rejected")
                raise CircuitBreakerOpenError(f"Circuit breaker '{breaker_name}' is open")

            try:
                result = breaker.call(func, *args, **kwargs)
                logger.debug(f"Circuit breaker '{breaker_name}' call succeeded")
                return result
            except aiobreaker.CircuitBreakerError as e:
                logger.warning(f"Circuit breaker '{breaker_name}' is open: {e}")
                raise CircuitBreakerOpenError(f"Circuit breaker '{breaker_name}' is open") from e
            except Exception as e:
                logger.error(f"Circuit breaker '{breaker_name}' call failed: {e}")
                raise

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            if isinstance(breaker.state, CircuitOpenState):
                logger.warning(f"Circuit breaker '{breaker_name}' is OPEN, call rejected")
                raise CircuitBreakerOpenError(f"Circuit breaker '{breaker_name}' is open")

            try:
                result = await breaker.call(func, *args, **kwargs)
                logger.debug(f"Circuit breaker '{breaker_name}' call succeeded")
                return result
            except aiobreaker.CircuitBreakerError as e:
                logger.warning(f"Circuit breaker '{breaker_name}' is open: {e}")
                raise CircuitBreakerOpenError(f"Circuit breaker '{breaker_name}' is open") from e
            except Exception as e:
                logger.error(f"Circuit breaker '{breaker_name}' call failed: {e}")
                raise

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


class CircuitBreakerOpenError(Exception):
    """断路器打开异常"""
    pass


def get_circuit_breaker(name: str) -> Optional[aiobreaker.CircuitBreaker]:
    """获取指定名称的断路器实例"""
    return _breakers.get(name)


def reset_circuit_breaker(name: str) -> bool:
    """重置指定名称的断路器"""
    if name in _breakers:
        _breakers[name].close()
        logger.info(f"Circuit breaker '{name}' has been reset")
        return True
    return False


def list_circuit_breakers() -> dict[str, str]:
    """列出所有断路器及其状态"""
    return {name: str(breaker.state) for name, breaker in _breakers.items()}


__all__ = [
    "create_circuit_breaker",
    "circuit_breaker",
    "CircuitBreakerOpenError",
    "get_circuit_breaker",
    "reset_circuit_breaker",
    "list_circuit_breakers",
]