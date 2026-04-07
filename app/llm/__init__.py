"""LLM 工厂模块

提供 LLM 实例创建和缓存功能。
"""

from langchain_openai import ChatOpenAI

from app.config.settings import get_settings


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


def create_llm(provider: str, model_type: str = "chat", **kwargs) -> ChatOpenAI:
    """工厂函数：创建 LLM 实例

    Args:
        provider: provider 名称 (siliconflow/openai/deepseek/dashscope)
        model_type: 模型类型 ("chat" 或 "vision")
        **kwargs: 其他传递给 ChatOpenAI 的参数

    Returns:
        ChatOpenAI 实例
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

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=config["base_url"],
        **kwargs,
    )


# LLM 实例缓存
_llm_cache: dict[str, ChatOpenAI] = {}


def get_llm(provider: str, model_type: str = "chat", **kwargs) -> ChatOpenAI:
    """获取 LLM 实例（带缓存）

    对相同参数的调用返回缓存的实例，避免重复创建。

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
        _llm_cache[key] = create_llm(provider, model_type, **kwargs)

    return _llm_cache[key]


__all__ = ["create_llm", "get_llm", "PROVIDERS_CONFIG"]