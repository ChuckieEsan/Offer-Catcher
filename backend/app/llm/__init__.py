"""LLM 工厂模块

提供 LLM 实例创建和缓存功能，自动记录 Token 消耗。
"""

import time
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler

from app.config.settings import get_settings
from app.utils.logger import logger


# Provider 基础配置
PROVIDERS_CONFIG = {
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "models": {
            "chat": "deepseek-chat",
            "vision": "Qwen/Qwen3-VL-8B-Instruct",
        }
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "models": {
            "chat": "gpt-4o",
            "vision": "gpt-4o",
        }
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "models": {
            "chat": "deepseek-chat",
        }
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": {
            "chat": "qwen3.6-plus",
            "vision": "qwen3.6-plus",
        }
    },
}


class TokenUsageCallback(BaseCallbackHandler):
    """LangChain 回调处理器，自动记录 Token 消耗

    集成 OpenTelemetry，将 Token 使用情况记录到 Metrics。
    """

    def __init__(self, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model
        self._start_time: float = 0.0

    def on_llm_start(self, serialized, prompts, **kwargs) -> None:
        """LLM 调用开始，记录时间"""
        self._start_time = time.perf_counter()

    def on_llm_end(self, response, **kwargs) -> None:
        """LLM 调用结束，记录 Token 消耗"""
        duration_ms = (time.perf_counter() - self._start_time) * 1000

        # 提取 usage 信息
        input_tokens = 0
        output_tokens = 0

        # 从 response.llm_output 中提取
        if hasattr(response, 'llm_output') and response.llm_output:
            usage = response.llm_output.get('token_usage', {})
            input_tokens = usage.get('prompt_tokens', 0)
            output_tokens = usage.get('completion_tokens', 0)

        # 从 response.generations 中提取（某些 provider）
        if input_tokens == 0 and hasattr(response, 'generations'):
            for gen in response.generations:
                if hasattr(gen[0], 'generation_info') and gen[0].generation_info:
                    usage = gen[0].generation_info.get('token_usage', {})
                    input_tokens = usage.get('prompt_tokens', 0)
                    output_tokens = usage.get('completion_tokens', 0)

        # 如果仍有 token 信息，记录到 telemetry
        if input_tokens > 0 or output_tokens > 0:
            try:
                from app.utils.telemetry import record_llm_tokens
                record_llm_tokens(
                    provider=self.provider,
                    model=self.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                )
            except ImportError:
                logger.debug("Telemetry not available, skipping token recording")

        logger.debug(
            f"LLM call: provider={self.provider}, model={self.model}, "
            f"tokens={input_tokens}/{output_tokens}, duration={duration_ms:.2f}ms"
        )


def create_llm(provider: str, model_type: str = "chat", **kwargs) -> ChatOpenAI:
    """工厂函数：创建 LLM 实例

    Args:
        provider: provider 名称 (siliconflow/openai/deepseek/dashscope)
        model_type: 模型类型 ("chat" 或 "vision")
        **kwargs: 其他传递给 ChatOpenAI 的参数

    Returns:
        ChatOpenAI 实例

    Note:
        默认启用 streaming=True 以支持流式输出。
    """
    settings = get_settings()

    if provider not in PROVIDERS_CONFIG:
        raise ValueError(f"Unknown provider: {provider}")

    config = PROVIDERS_CONFIG[provider]
    model = config["models"].get(model_type)
    if not model:
        raise ValueError(f"Provider {provider} does not support model type: {model_type}")

    # 获取 API Key
    api_key = getattr(settings, f"{provider}_api_key", None)
    if not api_key:
        raise ValueError(f"API key not configured for provider: {provider}")

    # 默认启用流式输出（除非用户显式禁用）
    streaming = kwargs.pop("streaming", True)

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=config["base_url"],
        streaming=streaming,
        **kwargs,
    )


# LLM 实例缓存
_llm_cache: dict[str, ChatOpenAI] = {}


def get_llm(provider: str, model_type: str = "chat", **kwargs) -> ChatOpenAI:
    """获取 LLM 实例（带缓存和自动 Token 记录）

    对相同参数的调用返回缓存的实例，避免重复创建。
    自动添加 TokenUsageCallback 记录 Token 消耗。

    Args:
        provider: provider 名称 (dashscope/openai/deepseek/siliconflow)
        model_type: 模型类型 ("chat" 或 "vision")
        **kwargs: 其他传递给 ChatOpenAI 的参数

    Returns:
        ChatOpenAI 实例

    Note:
        如果传入额外的 kwargs 参数，会创建新的实例并缓存。
    """
    # 生成缓存键
    key_parts = [provider, model_type]
    if kwargs:
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    key = ":".join(key_parts)

    if key not in _llm_cache:
        llm = create_llm(provider, model_type, **kwargs)
        # 添加 Token 使用回调（仅当 telemetry 可用时）
        model_name = PROVIDERS_CONFIG[provider]["models"].get(model_type, "unknown")
        callback = TokenUsageCallback(provider=provider, model=model_name)

        # 合入现有的 callbacks
        existing_callbacks = kwargs.get('callbacks', [])
        if existing_callbacks:
            llm.callbacks = list(existing_callbacks) + [callback]
        else:
            llm.callbacks = [callback]

        _llm_cache[key] = llm

    return _llm_cache[key]


__all__ = ["create_llm", "get_llm", "PROVIDERS_CONFIG"]