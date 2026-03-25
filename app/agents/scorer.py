"""Scorer Agent 模块

负责对用户提交的答案进行打分，生成改进建议，并更新熟练度等级。
"""

import json
from pathlib import Path
from typing import Optional

from langchain_openai import ChatOpenAI

from app.config.settings import create_llm
from app.db.qdrant_client import get_qdrant_manager
from app.models.enums import MasteryLevel
from app.models.schemas import ScoreResult
from app.utils.logger import logger


# Prompt 模板路径
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "scorer.md"


def load_prompt() -> str:
    """加载 Prompt 模板"""
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    return ""


def calculate_new_level(current_level: MasteryLevel, score: int) -> MasteryLevel:
    """根据分数计算新的熟练度等级

    状态机规则：
    - LEVEL_0 -> LEVEL_1: score >= 60
    - LEVEL_1 -> LEVEL_2: score >= 85
    - LEVEL_2 保持不变
    - score < 60 保持当前等级

    Args:
        current_level: 当前熟练度等级
        score: 评分分数

    Returns:
        新的熟练度等级
    """
    if current_level == MasteryLevel.LEVEL_0:
        if score >= 60:
            return MasteryLevel.LEVEL_1
    elif current_level == MasteryLevel.LEVEL_1:
        if score >= 85:
            return MasteryLevel.LEVEL_2
    # LEVEL_2 保持不变，任何分数 < 60 也保持不变

    return current_level


class ScorerAgent:
    """Scorer Agent - 答题评分与状态机

    对用户提交的答案进行评分，生成反馈，并更新熟练度等级。
    """

    def __init__(self, provider: str = "dashscope") -> None:
        """初始化 Scorer Agent

        Args:
            provider: LLM Provider 名称，默认 dashscope
        """
        self.provider = provider
        self._llm = None
        self.prompt_template = load_prompt()
        self._qdrant_manager = get_qdrant_manager()
        logger.info(f"ScorerAgent initialized with provider: {provider}")

    @property
    def llm(self) -> ChatOpenAI:
        """获取 LLM"""
        if self._llm is None:
            self._llm = create_llm(self.provider, "chat")
        return self._llm

    def _build_prompt(
        self,
        question_text: str,
        standard_answer: Optional[str],
        user_answer: str,
        current_level: MasteryLevel,
        company: str,
        position: str,
    ) -> str:
        """构建 Prompt"""
        return self.prompt_template.format(
            question_text=question_text,
            standard_answer=standard_answer or "无标准答案",
            user_answer=user_answer,
            current_level=current_level.name,
            company=company,
            position=position,
        )

    def _parse_response(self, response: str) -> dict:
        """解析 LLM 响应"""
        try:
            # 尝试提取 JSON
            json_start = response.find("{")
            json_end = response.rfind("}") + 1

            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")

            json_str = response[json_start:json_end]
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
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

        # 获取题目信息
        question = self._qdrant_manager.get_question(question_id)

        if not question:
            logger.error(f"Question not found: {question_id}")
            raise ValueError(f"Question not found: {question_id}")

        question_text = question.question_text
        standard_answer = question.question_answer
        current_level = MasteryLevel(question.mastery_level)
        company = question.company
        position = question.position

        try:
            # 构建 Prompt
            prompt = self._build_prompt(
                question_text=question_text,
                standard_answer=standard_answer,
                user_answer=user_answer,
                current_level=current_level,
                company=company,
                position=position,
            )

            # 调用 LLM
            response = self.llm.invoke(prompt)
            result = self._parse_response(response.content)

            # 解析结果
            score = result.get("score", 0)
            mastery_level_str = result.get("mastery_level", current_level.name)

            # 将字符串转换为枚举
            try:
                mastery_level = MasteryLevel[mastery_level_str]
            except KeyError:
                mastery_level = calculate_new_level(current_level, score)

            # 计算新的等级
            new_level = calculate_new_level(current_level, score)

            # 如果 LLM 返回的等级和计算的不一致，以计算为准
            if new_level != mastery_level:
                logger.info(
                    f"Level adjusted: LLM={mastery_level.name}, calculated={new_level.name}"
                )
                mastery_level = new_level

            # 构建结果
            score_result = ScoreResult(
                question_id=question_id,
                question_text=question_text,
                standard_answer=standard_answer,
                user_answer=user_answer,
                score=score,
                mastery_level=mastery_level,
                strengths=result.get("strengths", []),
                improvements=result.get("improvements", []),
                feedback=result.get("feedback", ""),
            )

            # 更新 Qdrant 中的熟练度等级
            if mastery_level != current_level:
                self._qdrant_manager.update_question(
                    question_id=question_id,
                    mastery_level=mastery_level.value,
                )
                logger.info(
                    f"Updated mastery_level: {current_level.name} -> {mastery_level.name}"
                )

            logger.info(
                f"Scoring completed: score={score}, level={mastery_level.name}"
            )
            return score_result

        except Exception as e:
            logger.error(f"Scoring failed: {e}")
            raise


# 全局单例
_scorer_agent: Optional[ScorerAgent] = None


def get_scorer_agent(provider: str = "dashscope") -> ScorerAgent:
    """获取 Scorer Agent 单例

    Args:
        provider: LLM Provider 名称

    Returns:
        ScorerAgent 实例
    """
    global _scorer_agent
    if _scorer_agent is None:
        _scorer_agent = ScorerAgent(provider=provider)
    return _scorer_agent