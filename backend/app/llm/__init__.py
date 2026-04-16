"""LLM 工厂模块

提供 LLM 实例创建和缓存功能，自动记录 Token 消耗。

底层服务由 infrastructure/adapters 提供。
"""

from app.infrastructure.adapters.llm_adapter import (
    LLMAdapter,
    get_llm_adapter,
    create_llm,
    get_llm,
    PROVIDERS_CONFIG,
)

__all__ = ["create_llm", "get_llm", "PROVIDERS_CONFIG", "LLMAdapter", "get_llm_adapter"]