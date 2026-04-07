"""断路器装饰器模块

基于 aiobreaker 实现的断路器模式，用于防止连续失败导致的级联故障。

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

from app.utils.logger import logger


# 全局断路器字典，支持按名称区分不同的断路器
_breakers: dict[str, aiobreaker.CircuitBreaker] = {}


def create_circuit_breaker(
    fail_max: int = 5,
    timeout_duration: float = 30.0,
    name: str = "default",
    exclude_exceptions: Tuple[Type[Exception], ...] = (),
) -> aiobreaker.CircuitBreaker:
    """创建或获取断路器实例

    如果已存在同名断路器，则返回现有的；否则创建新的。

    Args:
        fail_max: 连续失败次数阈值，达到该值后触发熔断，默认 5
        timeout_duration: 恢复超时时间（秒），超时后尝试恢复，默认 30
        name: 断路器名称，用于区分不同的断路器
        exclude_exceptions: 排除的异常类型，这些异常不会触发断路器

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
        fail_max: 连续失败次数阈值，达到该值后触发熔断，默认 5
        timeout_duration: 恢复超时时间（秒），超时后尝试恢复，默认 30
        name: 断路器名称，用于区分不同的断路器，默认使用函数名
        exclude_exceptions: 排除的异常类型，这些异常不会触发断路器
        state_callback: 断路器状态变更时的回调函数

    Example:
        @circuit_breaker(fail_max=5, timeout_duration=30)
        def call_external_api():
            response = requests.get("https://api.example.com/data")
            response.raise_for_status()
            return response.json()
    """

    def decorator(func: Callable) -> Callable:
        # 使用函数名作为默认断路器名称
        breaker_name = name or func.__name__

        # 获取或创建断路器
        if breaker_name not in _breakers:
            _breakers[breaker_name] = aiobreaker.CircuitBreaker(
                fail_max=fail_max,
                timeout_duration=timedelta(seconds=timeout_duration),
                exclude=exclude_exceptions,
            )

            # 注册状态变更回调
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
            # 检查断路器状态
            if isinstance(breaker.state, CircuitOpenState):
                logger.warning(
                    f"Circuit breaker '{breaker_name}' is OPEN, call rejected"
                )
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{breaker_name}' is open"
                )

            try:
                # 使用断路器包装函数调用
                result = breaker.call(func, *args, **kwargs)
                logger.debug(f"Circuit breaker '{breaker_name}' call succeeded")
                return result
            except aiobreaker.CircuitBreakerError as e:
                # 断路器已打开
                logger.warning(f"Circuit breaker '{breaker_name}' is open: {e}")
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{breaker_name}' is open"
                ) from e
            except Exception as e:
                # 记录失败
                logger.error(
                    f"Circuit breaker '{breaker_name}' call failed: {e}"
                )
                raise

        # 异步版本
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            # 检查断路器状态
            if isinstance(breaker.state, CircuitOpenState):
                logger.warning(
                    f"Circuit breaker '{breaker_name}' is OPEN, call rejected"
                )
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{breaker_name}' is open"
                )

            try:
                # 使用断路器包装异步函数调用
                result = await breaker.call(func, *args, **kwargs)
                logger.debug(f"Circuit breaker '{breaker_name}' call succeeded")
                return result
            except aiobreaker.CircuitBreakerError as e:
                logger.warning(f"Circuit breaker '{breaker_name}' is open: {e}")
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{breaker_name}' is open"
                ) from e
            except Exception as e:
                logger.error(
                    f"Circuit breaker '{breaker_name}' call failed: {e}"
                )
                raise

        # 根据函数类型返回对应的包装器
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


class CircuitBreakerOpenError(Exception):
    """断路器打开异常

    当断路器处于打开状态时调用被拒绝，抛出此异常。
    """

    pass


def get_circuit_breaker(name: str) -> Optional[aiobreaker.CircuitBreaker]:
    """获取指定名称的断路器实例

    Args:
        name: 断路器名称

    Returns:
        断路器实例，如果不存在则返回 None
    """
    return _breakers.get(name)


def reset_circuit_breaker(name: str) -> bool:
    """重置指定名称的断路器

    Args:
        name: 断路器名称

    Returns:
        是否成功重置
    """
    if name in _breakers:
        _breakers[name].close()
        logger.info(f"Circuit breaker '{name}' has been reset")
        return True
    return False


def list_circuit_breakers() -> dict[str, str]:
    """列出所有断路器及其状态

    Returns:
        断路器名称到状态的映射
    """
    return {name: str(breaker.state) for name, breaker in _breakers.items()}