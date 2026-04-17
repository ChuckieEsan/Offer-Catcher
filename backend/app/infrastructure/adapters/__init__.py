"""基础设施层适配器

包含外部服务的适配器封装：
- EmbeddingAdapter：向量嵌入适配
- RerankerAdapter：重排适配
- WebSearchAdapter：Web 搜索适配
- OCRAdapter：OCR 识别适配
- XfyunASRAdapter：讯飞语音识别适配
- LLMAdapter：LLM 调用适配
- CacheAdapter：缓存适配（Redis）
"""

from app.infrastructure.adapters.embedding_adapter import (
    EmbeddingAdapter,
    get_embedding_adapter,
)
from app.infrastructure.adapters.reranker_adapter import (
    RerankerAdapter,
    get_reranker_adapter,
)
from app.infrastructure.adapters.web_search_adapter import (
    WebSearchAdapter,
    WebSearchResult,
    get_web_search_adapter,
)
from app.infrastructure.adapters.ocr_adapter import (
    OCRAdapter,
    get_ocr_adapter,
)
from app.infrastructure.adapters.asr_adapter import (
    ASRResult,
    XfyunASRAdapter,
    get_xfyun_asr_adapter,
)
from app.infrastructure.adapters.llm_adapter import (
    LLMAdapter,
    get_llm_adapter,
    create_llm,
    get_llm,
    PROVIDERS_CONFIG,
)
from app.infrastructure.adapters.cache_adapter import (
    CacheAdapter,
    get_cache_adapter,
)

__all__ = [
    "EmbeddingAdapter",
    "get_embedding_adapter",
    "RerankerAdapter",
    "get_reranker_adapter",
    "WebSearchAdapter",
    "WebSearchResult",
    "get_web_search_adapter",
    "OCRAdapter",
    "get_ocr_adapter",
    "ASRResult",
    "XfyunASRAdapter",
    "get_xfyun_asr_adapter",
    "LLMAdapter",
    "get_llm_adapter",
    "create_llm",
    "get_llm",
    "PROVIDERS_CONFIG",
    "CacheAdapter",
    "get_cache_adapter",
]