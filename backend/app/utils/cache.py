"""通用缓存工具模块

提供缓存装饰器，支持按参数自动生成缓存键。
"""

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
    """单例缓存装饰器

    将函数返回值缓存，忽略所有参数。
    适用于无参数或总是返回相同实例的工厂函数。

    Example:
        @singleton
        def get_embedding_tool() -> EmbeddingTool:
            return EmbeddingTool()

        @singleton
        def get_react_agent() -> CompiledStateGraph:
            return create_agent(...)
    """
    _instance: T | None = None

    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        nonlocal _instance
        if _instance is None:
            _instance = func(*args, **kwargs)
        return _instance

    wrapper.clear_cache = lambda: globals().update(_instance=None)  # type: ignore

    return wrapper


__all__ = ["cached", "singleton"]