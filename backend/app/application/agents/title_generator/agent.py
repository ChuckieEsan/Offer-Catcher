"""Title Generator Agent - 会话标题生成 Agent

分析对话内容，生成简洁的标题。
"""

from __future__ import annotations

from typing import List, Optional

from langchain_openai import ChatOpenAI

from app.application.agents.shared.base_agent import BaseAgent
from app.application.agents.title_generator.prompts import PROMPTS_DIR
from app.infrastructure.common.logger import logger


class TitleGeneratorAgent(BaseAgent[str]):
    """Title Generator Agent - 会话标题生成

    分析对话内容，生成简洁的标题。

    使用依赖注入：
    - llm: ChatOpenAI 实例
    """

    _prompt_filename = "title_generator.md"
    _structured_output_schema = None

    def __init__(
        self,
        llm: ChatOpenAI,
        prompts_dir: Any = PROMPTS_DIR,
    ) -> None:
        """初始化 Title Generator

        Args:
            llm: LLM 实例（依赖注入）
            prompts_dir: Prompt 目录路径
        """
        super().__init__(llm, prompts_dir)

    def generate_title(self, messages: List) -> str:
        """生成会话标题

        Args:
            messages: 对话消息列表（支持 Domain Message 实体或 dict）

        Returns:
            生成的标题（不超过 20 个字符）
        """
        logger.info(f"Generating title for {len(messages)} messages")

        conversation_content = self._build_conversation_content(messages)

        prompt = self._build_prompt(conversation_content=conversation_content)

        try:
            title = self.invoke_llm(prompt)
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
            messages: 消息列表（支持 Domain Message 实体和 dict）

        Returns:
            格式化的对话内容
        """
        lines = []
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role", "")
                content = msg.get("content", "")
            else:
                role = msg.role.value if hasattr(msg.role, "value") else msg.role
                content = msg.content

            role_label = "用户" if role == "user" else "AI"
            content = content[:200] if len(content) > 200 else content
            lines.append(f"{role_label}: {content}")
        return "\n".join(lines)


_title_generator: Optional[TitleGeneratorAgent] = None


def get_title_generator() -> TitleGeneratorAgent:
    """获取 Title Generator 单例

    Note: 使用 factory.get_title_generator() 获取实例，
    此函数作为备用入口。

    Returns:
        TitleGeneratorAgent 实例
    """
    global _title_generator
    if _title_generator is None:
        from app.infrastructure.adapters.llm_adapter import get_llm

        llm = get_llm("deepseek", "chat")
        _title_generator = TitleGeneratorAgent(llm)
    return _title_generator


__all__ = [
    "TitleGeneratorAgent",
    "get_title_generator",
]