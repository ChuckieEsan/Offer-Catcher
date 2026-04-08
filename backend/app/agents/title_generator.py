"""Title Generator Agent 模块

负责根据对话内容生成简洁、准确的会话标题。
"""

from typing import List, Optional

from app.agents.base import BaseAgent
from app.db.postgres_client import Message
from app.utils.logger import logger


class TitleGeneratorAgent(BaseAgent[str]):
    """Title Generator Agent - 会话标题生成

    分析对话内容，生成简洁的标题。
    """

    _prompt_filename = "title_generator.md"

    def __init__(self, provider: str = "dashscope") -> None:
        super().__init__(provider, llm_kwargs={"extra_body": {"enable_thinking": False}})

    def generate_title(self, messages: List[Message]) -> str:
        """生成会话标题

        Args:
            messages: 对话消息列表

        Returns:
            生成的标题（不超过 20 个字符）
        """
        logger.info(f"Generating title for {len(messages)} messages")

        # 构建对话内容
        conversation_content = self._build_conversation_content(messages)

        # 构建 Prompt
        prompt = self._build_prompt(conversation_content=conversation_content)

        # 调用 LLM
        try:
            title = self.invoke_llm(prompt)
            # 清理标题（移除多余空白、限制长度）
            title = title.strip()
            if len(title) > 20:
                title = title[:20]
            logger.info(f"Generated title: {title}")
            return title
        except Exception as e:
            logger.error(f"Title generation failed: {e}")
            return "新对话"

    def _build_conversation_content(self, messages: List[Message]) -> str:
        """构建对话内容文本

        Args:
            messages: 消息列表

        Returns:
            格式化的对话内容
        """
        lines = []
        for msg in messages:
            role_label = "用户" if msg.role == "user" else "AI"
            # 截断过长的消息（标题生成只需要关键信息）
            content = msg.content[:200] if len(msg.content) > 200 else msg.content
            lines.append(f"{role_label}: {content}")
        return "\n".join(lines)


# 全局单例
_title_generator_agent: Optional[TitleGeneratorAgent] = None


def get_title_generator_agent(provider: str = "dashscope") -> TitleGeneratorAgent:
    """获取 Title Generator Agent 单例

    Args:
        provider: LLM Provider 名称

    Returns:
        TitleGeneratorAgent 实例
    """
    global _title_generator_agent
    if _title_generator_agent is None:
        _title_generator_agent = TitleGeneratorAgent(provider=provider)
    return _title_generator_agent


__all__ = ["TitleGeneratorAgent", "get_title_generator_agent"]