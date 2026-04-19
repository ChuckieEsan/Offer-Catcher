"""Scorer Agent - 答题评分 Agent

对用户提交的答案进行评分，生成反馈，并更新熟练度等级。
"""

from __future__ import annotations

import json
from typing import Optional, Any

from langchain_openai import ChatOpenAI

from app.application.agents.shared.base_agent import BaseAgent
from app.application.agents.scorer.prompts import PROMPTS_DIR
from app.domain.interview.services import calculate_new_level
from app.domain.question.repositories import QuestionRepository
from app.infrastructure.persistence.qdrant.question_repository import get_question_repository
from app.application.agents.scorer.results import ScoreResult
from app.domain.shared.enums import MasteryLevel
from app.infrastructure.common.logger import logger


class ScorerAgent(BaseAgent[ScoreResult]):
    """Scorer Agent - 答题评分与状态机

    对用户提交的答案进行评分，生成反馈，并更新熟练度等级。

    使用依赖注入：
    - llm: ChatOpenAI 实例
    - question_repo: QuestionRepository 实例
    """

    _prompt_filename = "scorer.md"
    _structured_output_schema = ScoreResult

    def __init__(
        self,
        llm: ChatOpenAI,
        question_repo: QuestionRepository,
        prompts_dir: Any = PROMPTS_DIR,
    ) -> None:
        """初始化 Scorer Agent

        Args:
            llm: LLM 实例（依赖注入）
            question_repo: Question 仓库实例（依赖注入）
            prompts_dir: Prompt 目录路径
        """
        super().__init__(llm, prompts_dir)
        self._question_repo = question_repo

    def _parse_response_fallback(
        self,
        response: str,
        question_id: str,
        question_text: str,
        standard_answer: Optional[str],
        user_answer: str,
    ) -> ScoreResult:
        """手动解析 LLM 响应（降级方案）"""
        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1

            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")

            json_str = response[json_start:json_end]
            data = json.loads(json_str)

            mastery_level_str = data.get("mastery_level", "LEVEL_0")
            try:
                mastery_level = MasteryLevel[mastery_level_str]
            except KeyError:
                mastery_level = MasteryLevel.LEVEL_0

            return ScoreResult(
                question_id=question_id,
                question_text=question_text,
                standard_answer=standard_answer,
                user_answer=user_answer,
                score=data.get("score", 0),
                mastery_level=mastery_level,
                strengths=data.get("strengths", []),
                improvements=data.get("improvements", []),
                feedback=data.get("feedback", ""),
            )

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.error(f"Response: {response}")
            raise

    async def score(
        self,
        question_id: str,
        user_answer: str,
    ) -> ScoreResult:
        """对答案进行评分

        Args:
            question_id: 题目 ID
            user_answer: 用户提交的答案

        Returns:
            ScoreResult 包含评分和反馈
        """
        logger.info(f"Scoring answer for question: {question_id}")

        question = self._question_repo.find_by_id(question_id)

        if not question:
            logger.error(f"Question not found: {question_id}")
            raise ValueError(f"Question not found: {question_id}")

        question_text = question.question_text
        standard_answer = question.answer
        current_level = question.mastery_level
        company = question.company
        position = question.position

        prompt = self._build_prompt(
            question_text=question_text,
            standard_answer=standard_answer,
            user_answer=user_answer,
            current_level=current_level.name,
            company=company,
            position=position,
        )

        result = self.invoke_structured(prompt)
        if result is not None:
            result.question_id = question_id
            result.question_text = question_text
            result.standard_answer = standard_answer
            result.user_answer = user_answer

            new_level = calculate_new_level(current_level, result.score)
            if new_level != result.mastery_level:
                logger.info(f"Level adjusted: LLM={result.mastery_level.name}, calculated={new_level.name}")
                result.mastery_level = new_level

            if result.mastery_level != current_level:
                self._question_repo.update_mastery(question_id, result.mastery_level)
                logger.info(f"Updated mastery_level: {current_level.name} -> {result.mastery_level.name}")

            logger.info(f"Scoring completed (structured): score={result.score}, level={result.mastery_level.name}")
            return result

        try:
            response = self.invoke_llm(prompt)
            result = self._parse_response_fallback(
                response,
                question_id,
                question_text,
                standard_answer,
                user_answer,
            )

            new_level = calculate_new_level(current_level, result.score)
            if new_level != result.mastery_level:
                logger.info(f"Level adjusted: LLM={result.mastery_level.name}, calculated={new_level.name}")
                result.mastery_level = new_level

            if result.mastery_level != current_level:
                self._question_repo.update_mastery(question_id, result.mastery_level)
                logger.info(f"Updated mastery_level: {current_level.name} -> {result.mastery_level.name}")

            logger.info(f"Scoring completed (fallback): score={result.score}, level={result.mastery_level.name}")
            return result
        except Exception as e:
            logger.error(f"Scoring failed: {e}")
            raise


_scorer_agent: Optional[ScorerAgent] = None


def get_scorer_agent() -> ScorerAgent:
    """获取 Scorer Agent 单例

    Note: 使用 factory.get_scorer_agent() 获取实例，
    此函数作为备用入口。

    Returns:
        ScorerAgent 实例
    """
    global _scorer_agent
    if _scorer_agent is None:
        from app.infrastructure.adapters.llm_adapter import get_llm
        from app.infrastructure.persistence.qdrant.question_repository import get_question_repository

        llm = get_llm("deepseek", "chat")
        question_repo = get_question_repository()
        _scorer_agent = ScorerAgent(llm, question_repo)
    return _scorer_agent


__all__ = [
    "ScorerAgent",
    "get_scorer_agent",
]