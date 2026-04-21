"""通用缓存工具模块

提供缓存装饰器，支持按参数自动生成缓存键。
作为基础设施层通用组件，为所有层提供缓存服务。
"""

import threading
from functools import wraps
from typing import Callable, TypeVar

T = TypeVar("T")


def _make_key(args: tuple, kwargs: dict) -> str:
    """自动序列化参数生成缓存键

    Args:
        args: 位置参数
        kwargs: 关键字参数

    Returns:
        缓存键字符串
    """
    parts = [str(arg) for arg in args]
    if kwargs:
        parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    return ":".join(parts)


def cached(func: Callable[..., T]) -> Callable[..., T]:
    """通用缓存装饰器

    自动根据函数参数生成缓存键，支持位置参数和关键字参数。
    对于相同参数的调用，直接返回缓存结果。

    Example:
        @cached
        def get_llm(provider: str, model_type: str = "chat") -> ChatOpenAI:
            return ChatOpenAI(...)

    Note:
        - 缓存是进程级别的，不会跨进程共享
        - 参数会被转换为字符串作为键，复杂对象需确保 str() 结果稳定
    """
    _cache: dict[str, T] = {}

    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        key = _make_key(args, kwargs)
        if key not in _cache:
            _cache[key] = func(*args, **kwargs)
        return _cache[key]

    wrapper.clear_cache = lambda: _cache.clear()  # type: ignore
    wrapper._cache = _cache  # type: ignore

    return wrapper


def singleton(func: Callable[..., T]) -> Callable[..., T]:
    """单例缓存装饰器（线程安全）

    将函数返回值缓存，后续调用直接返回缓存的实例。
    适用于无参数或总是返回相同实例的工厂函数。

    Features:
        - 线程安全：使用锁保护实例创建
        - 支持清除缓存：调用 wrapper.clear_cache() 可重置实例

    Example:
        @singleton
        def get_embedding_tool() -> EmbeddingTool:
            return EmbeddingTool()

        # 清除缓存（用于测试或重置）
        get_embedding_tool.clear_cache()
    """
    class Container:
        __slots__ = ('instance',)
        def __init__(self):
            self.instance: T | None = None

    _container = Container()
    _lock = threading.Lock()

    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        if _container.instance is not None:
            return _container.instance

        with _lock:
            if _container.instance is None:
                _container.instance = func(*args, **kwargs)
            return _container.instance

    def clear_cache() -> None:
        """清除缓存的实例"""
        with _lock:
            _container.instance = None

    wrapper.clear_cache = clear_cache  # type: ignore
    wrapper._is_singleton = True  # type: ignore

    return wrapper


__all__ = ["cached", "singleton"]