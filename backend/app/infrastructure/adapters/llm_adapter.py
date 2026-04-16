"""LLM 适配器

封装 LangChain LLM 调用，提供统一的 LLM 服务接口。
作为基础设施层适配器，为应用层和领域层提供 LLM 服务。

支持多个 Provider：
- deepseek: DeepSeek V3
- openai: GPT-4o
- siliconflow: DeepSeek/Qwen
- dashscope: Qwen
"""

import time
from typing import Optional, Union

from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from langchain_core.callbacks import BaseCallbackHandler

from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger


# Provider 配置
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
        },
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": {
            "chat": "qwen3.5-35b-a3b",
            "vision": "qwen3.5-35b-a3b",
        }
    },
}


class TokenUsageCallback(BaseCallbackHandler):
    """LangChain 回调处理器，自动记录 Token 消耗"""

    def __init__(self, provider: str, model: str) -> None:
        self._provider = provider
        self._model = model
        self._start_time: float = 0.0

    def on_llm_start(self, serialized, prompts, **kwargs) -> None:
        """LLM 调用开始"""
        self._start_time = time.perf_counter()

    def on_llm_end(self, response, **kwargs) -> None:
        """LLM 调用结束，记录 Token 消耗"""
        duration_ms = (time.perf_counter() - self._start_time) * 1000

        input_tokens = 0
        output_tokens = 0

        if hasattr(response, 'llm_output') and response.llm_output:
            usage = response.llm_output.get('token_usage', {})
            input_tokens = usage.get('prompt_tokens', 0)
            output_tokens = usage.get('completion_tokens', 0)

        if input_tokens == 0 and hasattr(response, 'generations'):
            for gen in response.generations:
                if hasattr(gen[0], 'generation_info') and gen[0].generation_info:
                    usage = gen[0].generation_info.get('token_usage', {})
                    input_tokens = usage.get('prompt_tokens', 0)
                    output_tokens = usage.get('completion_tokens', 0)

        if input_tokens > 0 or output_tokens > 0:
            try:
                from app.utils.telemetry import record_llm_tokens
                record_llm_tokens(
                    provider=self._provider,
                    model=self._model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                )
            except ImportError:
                logger.debug("Telemetry not available, skipping token recording")

        logger.debug(
            f"LLM call: provider={self._provider}, model={self._model}, "
            f"tokens={input_tokens}/{output_tokens}, duration={duration_ms:.2f}ms"
        )


class LLMAdapter:
    """LLM 适配器

    封装 LangChain LLM 调用，提供统一的 LLM 服务接口。
    支持多 Provider、Token 消耗记录、缓存等特性。

    设计原则：
    - 封装外部 LLM API
    - 支持 Token 消耗监控
    - 支持缓存避免重复创建
    """

    def __init__(self) -> None:
        """初始化适配器"""
        self._cache: dict[str, Union[ChatOpenAI, ChatDeepSeek]] = {}
        logger.info("LLMAdapter initialized")

    def create(
        self,
        provider: str,
        model_type: str = "chat",
        **kwargs,
    ) -> Union[ChatOpenAI, ChatDeepSeek]:
        """创建 LLM 实例

        Args:
            provider: provider 名称 (siliconflow/openai/deepseek/dashscope)
            model_type: 模型类型 ("chat" 或 "vision")
            **kwargs: 其他参数

        Returns:
            LLM 实例
        """
        settings = get_settings()

        if provider not in PROVIDERS_CONFIG:
            raise ValueError(f"Unknown provider: {provider}")

        config = PROVIDERS_CONFIG[provider]
        model = config["models"].get(model_type)
        if not model:
            raise ValueError(f"Provider {provider} does not support model type: {model_type}")

        api_key = getattr(settings, f"{provider}_api_key", None)
        if not api_key:
            raise ValueError(f"API key not configured for provider: {provider}")

        streaming = kwargs.pop("streaming", True)

        # DeepSeek 特殊处理
        if provider == "deepseek":
            thinking_enabled = kwargs.pop("thinking_enabled", False)
            if thinking_enabled:
                extra_body = kwargs.pop("extra_body", {})
                extra_body["thinking"] = {"type": "enabled"}
                kwargs["extra_body"] = extra_body
                logger.info("DeepSeek thinking mode enabled")

            return ChatDeepSeek(
                model=model,
                api_key=api_key,
                streaming=streaming,
                **kwargs,
            )

        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=config["base_url"],
            streaming=streaming,
            **kwargs,
        )

    def get(
        self,
        provider: str,
        model_type: str = "chat",
        **kwargs,
    ) -> Union[ChatOpenAI, ChatDeepSeek]:
        """获取 LLM 实例（带缓存和 Token 记录）

        Args:
            provider: provider 名称
            model_type: 模型类型
            **kwargs: 其他参数

        Returns:
            LLM 实例
        """
        key_parts = [provider, model_type]
        if kwargs:
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        key = ":".join(key_parts)

        if key not in self._cache:
            llm = self.create(provider, model_type, **kwargs)
            model_name = PROVIDERS_CONFIG[provider]["models"].get(model_type, "unknown")
            callback = TokenUsageCallback(provider=provider, model=model_name)

            existing_callbacks = kwargs.get('callbacks', [])
            if existing_callbacks:
                llm.callbacks = list(existing_callbacks) + [callback]
            else:
                llm.callbacks = [callback]

            self._cache[key] = llm

        return self._cache[key]

    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()
        logger.info("LLM cache cleared")


# 单例获取函数
_llm_adapter: Optional[LLMAdapter] = None


def get_llm_adapter() -> LLMAdapter:
    """获取 LLM 适配器单例

    Returns:
        LLMAdapter 实例
    """
    global _llm_adapter
    if _llm_adapter is None:
        _llm_adapter = LLMAdapter()
    return _llm_adapter


# 向后兼容的接口（供现有代码使用）
def create_llm(provider: str, model_type: str = "chat", **kwargs) -> Union[ChatOpenAI, ChatDeepSeek]:
    """创建 LLM 实例（向后兼容接口）

    Args:
        provider: provider 名称
        model_type: 模型类型
        **kwargs: 其他参数

    Returns:
        LLM 实例
    """
    return get_llm_adapter().create(provider, model_type, **kwargs)


def get_llm(provider: str, model_type: str = "chat", **kwargs) -> Union[ChatOpenAI, ChatDeepSeek]:
    """获取 LLM 实例（向后兼容接口）

    Args:
        provider: provider 名称
        model_type: 模型类型
        **kwargs: 其他参数

    Returns:
        LLM 实例
    """
    return get_llm_adapter().get(provider, model_type, **kwargs)


__all__ = [
    "LLMAdapter",
    "get_llm_adapter",
    "create_llm",
    "get_llm",
    "PROVIDERS_CONFIG",
]