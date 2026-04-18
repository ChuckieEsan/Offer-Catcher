"""Title Generator Agent 模块

负责根据对话内容生成简洁、准确的会话标题。
"""

from typing import List

from app.agents.base import BaseAgent
from app.infrastructure.common.logger import logger
from app.infrastructure.common.cache import singleton


class TitleGeneratorAgent(BaseAgent[str]):
    """Title Generator Agent - 会话标题生成

    分析对话内容，生成简洁的标题。
    """

    _prompt_filename = "title_generator.md"

    def __init__(self, provider: str = "deepseek") -> None:
        super().__init__(provider)

    def generate_title(self, messages: List) -> str:
        """生成会话标题

        Args:
            messages: 对话消息列表（支持 Domain Message 实体或 dict）

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

    def _build_conversation_content(self, messages: List) -> str:
        """构建对话内容文本

        Args:
            messages: 消息列表（支持 Domain Message 实体或 dict）

        Returns:
            格式化的对话内容
        """
        lines = []
        for msg in messages:
            # 支持 Domain Message 实体和 dict
            if isinstance(msg, dict):
                role = msg.get("role", "")
                content = msg.get("content", "")
            else:
                # Domain Message 实体
                role = msg.role.value if hasattr(msg.role, "value") else msg.role
                content = msg.content

            role_label = "用户" if role == "user" else "AI"
            # 截断过长的消息（标题生成只需要关键信息）
            content = content[:200] if len(content) > 200 else content
            lines.append(f"{role_label}: {content}")
        return "\n".join(lines)


@singleton
def get_title_generator_agent(provider: str = "deepseek") -> TitleGeneratorAgent:
    """获取 Title Generator Agent 单例

    Args:
        provider: LLM Provider 名称（首次调用后忽略）

    Returns:
        TitleGeneratorAgent 实例
    """
    return TitleGeneratorAgent(provider=provider)


__all__ = ["TitleGeneratorAgent", "get_title_generator_agent"]