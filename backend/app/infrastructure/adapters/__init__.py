"""基础设施层适配器

包含外部服务的适配器封装：
- EmbeddingAdapter：向量嵌入适配
- LLMAdapter：LLM 调用适配
- WebSearchAdapter：Web 搜索适配
"""

from app.infrastructure.adapters.embedding_adapter import (
    EmbeddingAdapter,
    get_embedding_adapter,
)

__all__ = [
    "EmbeddingAdapter",
    "get_embedding_adapter",
]