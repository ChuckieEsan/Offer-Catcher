"""Answer Specialist Agent

从 RabbitMQ 消费任务，使用 Web Search Tool 搜索资料并生成答案。
"""

from typing import Optional

from app.agents.base import BaseAgent
from app.models.schemas import QuestionItem
from app.tools.web_search_tool import WebSearchTool, get_web_search_tool
from app.utils.logger import logger


class AnswerSpecialistAgent(BaseAgent):
    """Answer Specialist - 使用 Web Search 生成答案

    消费 RabbitMQ 消息，使用 Web Search Tool 搜索资料，
    然后调用 LLM 生成标准答案。
    """

    _prompt_filename = "answer_specialist.md"
    _structured_output_schema = None  # 不使用 structured output

    def __init__(self, provider: str = "dashscope"):
        """初始化 Answer Specialist

        Args:
            provider: LLM Provider 名称，默认 dashscope
        """
        super().__init__(provider)
        self._web_search: Optional[WebSearchTool] = None

    @property
    def web_search(self) -> WebSearchTool:
        """获取 Web Search 工具"""
        if self._web_search is None:
            self._web_search = get_web_search_tool(max_results=5)
        return self._web_search

    def _build_prompt(
        self,
        question: QuestionItem,
        context: str,
    ) -> str:
        """构建 Prompt"""
        return self.prompt_template.format(
            company=question.company,
            position=question.position,
            question=question.question_text,
            core_entities=", ".join(question.core_entities) if question.core_entities else "无",
            context=context,
        )

    def generate_answer(self, question: QuestionItem) -> str:
        """生成答案

        Args:
            question: QuestionItem 对象

        Returns:
            生成的标准答案
        """
        logger.info(f"Generating answer for: {question.question_text[:50]}...")

        # 1. 使用 Web Search 搜索相关资料
        try:
            context = self.web_search.search_for_answer(
                question=question.question_text,
                company=question.company,
                position=question.position,
            )
            logger.info(f"Search completed, context length: {len(context)}")
        except Exception as e:
            logger.warning(f"Web search failed: {e}, using empty context")
            context = "搜索失败，基于知识生成答案。"

        # 2. 构建 Prompt
        prompt = self._build_prompt(question, context)

        # 3. 调用 LLM 生成答案
        try:
            answer = self.invoke_llm(prompt)
            logger.info(f"Answer generated, length: {len(answer)}")
            return answer
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise


# 全局单例
_answer_specialist: Optional[AnswerSpecialistAgent] = None


def get_answer_specialist(provider: str = "dashscope") -> AnswerSpecialistAgent:
    """获取 Answer Specialist 单例"""
    global _answer_specialist
    if _answer_specialist is None:
        _answer_specialist = AnswerSpecialistAgent(provider=provider)
    return _answer_specialist