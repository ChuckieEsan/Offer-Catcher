"""Answer Specialist Agent - 答案生成 Agent

使用 Web Search 搜索资料，生成标准答案。
消费 RabbitMQ 消息，生成答案后存储到 Qdrant。
"""

from __future__ import annotations

from typing import Optional

from langchain_openai import ChatOpenAI

from app.application.agents.shared.base_agent import BaseAgent
from app.application.agents.answer_specialist.prompts import PROMPTS_DIR
from app.infrastructure.adapters.web_search_adapter import WebSearchAdapter, get_web_search_adapter
from app.infrastructure.common.logger import logger
from app.models import QuestionItem


class AnswerSpecialistAgent(BaseAgent[str]):
    """Answer Specialist - 使用 Web Search 生成答案

    消费 RabbitMQ 消息，使用 Web Search Adapter 搜索资料，
    然后调用 LLM 生成标准答案。

    使用依赖注入：
    - llm: ChatOpenAI 实例
    - web_search_adapter: WebSearchAdapter 实例
    """

    _prompt_filename = "answer_specialist.md"
    _structured_output_schema = None

    def __init__(
        self,
        llm: ChatOpenAI,
        web_search_adapter: WebSearchAdapter,
        prompts_dir: Any = PROMPTS_DIR,
    ) -> None:
        """初始化 Answer Specialist

        Args:
            llm: LLM 实例（依赖注入）
            web_search_adapter: Web Search Adapter 实例（依赖注入）
            prompts_dir: Prompt 目录路径
        """
        super().__init__(llm, prompts_dir)
        self._web_search_adapter = web_search_adapter

    @property
    def web_search_adapter(self) -> WebSearchAdapter:
        """获取 Web Search Adapter"""
        return self._web_search_adapter

    def generate_answer(self, question: QuestionItem) -> str:
        """生成答案

        Args:
            question: QuestionItem 对象

        Returns:
            生成的标准答案
        """
        logger.info(f"Generating answer for: {question.question_text[:50]}...")

        try:
            context = self._web_search_adapter.search_for_context(
                question=question.question_text,
                company=question.company,
                position=question.position,
            )
            logger.info(f"Search completed, context length: {len(context)}")
        except Exception as e:
            logger.warning(f"Web search failed: {e}, using empty context")
            context = "搜索失败，基于知识生成答案。"

        prompt = self._build_prompt(
            company=question.company,
            position=question.position,
            question=question.question_text,
            core_entities=", ".join(question.core_entities) if question.core_entities else "无",
            context=context,
        )

        try:
            answer = self.invoke_llm(prompt)
            logger.info(f"Answer generated, length: {len(answer)}")
            return answer
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise


_answer_specialist: Optional[AnswerSpecialistAgent] = None


def get_answer_specialist() -> AnswerSpecialistAgent:
    """获取 Answer Specialist 单例

    Note: 使用 factory.get_answer_specialist() 获取实例，
    此函数作为备用入口。

    Returns:
        AnswerSpecialistAgent 实例
    """
    global _answer_specialist
    if _answer_specialist is None:
        from app.infrastructure.adapters.llm_adapter import get_llm
        from app.infrastructure.adapters.web_search_adapter import get_web_search_adapter

        llm = get_llm("deepseek", "chat")
        web_search_adapter = get_web_search_adapter()
        _answer_specialist = AnswerSpecialistAgent(llm, web_search_adapter)
    return _answer_specialist


__all__ = [
    "AnswerSpecialistAgent",
    "get_answer_specialist",
]