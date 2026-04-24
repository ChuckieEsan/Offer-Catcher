"""LangChain Monkey Patches

修复 LangChain 与特定 Provider 的兼容性问题。

此模块必须在任何 LangChain 模块导入之前被导入。
"""

from app.infrastructure.common.logger import logger


def apply_deepseek_reasoning_patch() -> None:
    """Monkey Patch: 修复 DeepSeek reasoning_content 传递问题

    DeepSeek Thinking Mode 要求：当 tool call 发生时，assistant 消息的
    reasoning_content 必须在后续请求中传回 API，否则返回 400 错误。

    LangChain 的 _convert_message_to_dict 函数会忽略 additional_kwargs["reasoning_content"],
    导致 DeepSeek API 报错。此 patch 在消息转换时保留 reasoning_content 字段。

    参考：https://api-docs.deepseek.com/guides/thinking_mode#tool-calls
    """
    try:
        import langchain_openai.chat_models.base as base
        from langchain_core.messages import AIMessage

        _original_convert = base._convert_message_to_dict

        def _patched_convert_message_to_dict(message, api="chat/completions"):
            """Patched version that preserves reasoning_content for DeepSeek"""
            message_dict = _original_convert(message, api)

            # DeepSeek: 将 reasoning_content 从 additional_kwargs 提升到顶层
            if isinstance(message, AIMessage):
                reasoning_content = message.additional_kwargs.get("reasoning_content")
                if reasoning_content and message_dict.get("role") == "assistant":
                    message_dict["reasoning_content"] = reasoning_content

            return message_dict

        base._convert_message_to_dict = _patched_convert_message_to_dict
        logger.info("[Patch] DeepSeek reasoning_content patch applied successfully")

    except ImportError:
        logger.warning("[Patch] langchain_openai not available, skipping patch")
    except Exception as e:
        logger.error(f"[Patch] Failed to apply reasoning_content patch: {e}")


# 模块加载时立即应用 patch
apply_deepseek_reasoning_patch()


__all__ = ["apply_deepseek_reasoning_patch"]