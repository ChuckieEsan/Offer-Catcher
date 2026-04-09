"""通用缓存工具模块

提供缓存装饰器，支持按参数自动生成缓存键。
"""

import threading
from functools import wraps
from typing import Any, Callable, TypeVar

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
        # 排序 kwargs 保证一致性
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

        @cached
        def load_prompt(filename: str) -> str:
            return Path(filename).read_text()

    Note:
        - 缓存是进程级别的，不会跨进程共享
        - 参数会被转换为字符串作为键，复杂对象需确保 str() 结果稳定
        - 不适用于有副作用的函数
    """
    _cache: dict[str, T] = {}

    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        key = _make_key(args, kwargs)
        if key not in _cache:
            _cache[key] = func(*args, **kwargs)
        return _cache[key]

    # 添加清除缓存的方法（用于测试）
    wrapper.clear_cache = lambda: _cache.clear()  # type: ignore
    wrapper._cache = _cache  # type: ignore  # 暴露缓存供调试

    return wrapper


def singleton(func: Callable[..., T]) -> Callable[..., T]:
    """单例缓存装饰器（线程安全）

    将函数返回值缓存，后续调用直接返回缓存的实例。
    适用于无参数或总是返回相同实例的工厂函数。

    警告：此装饰器会忽略所有参数。如果需要根据参数缓存不同实例，
    请使用 @cached 装饰器。

    Features:
        - 线程安全：使用锁保护实例创建
        - 支持清除缓存：调用 wrapper.clear_cache() 可重置实例

    Example:
        @singleton
        def get_embedding_tool() -> EmbeddingTool:
            return EmbeddingTool()

        @singleton
        def get_react_agent() -> CompiledStateGraph:
            return create_agent(...)

        # 清除缓存（用于测试或重置）
        get_embedding_tool.clear_cache()
    """
    # 使用容器类来避免 nonlocal 的问题
    class Container:
        __slots__ = ('instance',)
        def __init__(self):
            self.instance: T | None = None

    _container = Container()
    _lock = threading.Lock()

    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        # 快速路径：已存在实例时直接返回（无需加锁）
        if _container.instance is not None:
            return _container.instance

        # 慢速路径：需要创建实例，加锁保护
        with _lock:
            # 双重检查：锁内再次检查，防止其他线程已创建
            if _container.instance is None:
                _container.instance = func(*args, **kwargs)
            return _container.instance

    def clear_cache() -> None:
        """清除缓存的实例"""
        with _lock:
            _container.instance = None

    wrapper.clear_cache = clear_cache
    wrapper._is_singleton = True  # type: ignore  # 标记为单例装饰器

    return wrapper


__all__ = ["cached", "singleton"]