"""Scorer Agent 模块

负责对用户提交的答案进行打分，生成改进建议，并更新熟练度等级。
"""

from typing import Optional

from app.agents.base import BaseAgent
from app.config.settings import create_llm
from app.db.qdrant_client import get_qdrant_manager
from app.models.enums import MasteryLevel
from app.models.schemas import ScoreResult
from app.utils.logger import logger
from app.utils.agent import load_prompt, parse_json_response


def calculate_new_level(current_level: MasteryLevel, score: int) -> MasteryLevel:
    """根据分数计算新的熟练度等级

    状态机规则：
    - LEVEL_0 -> LEVEL_2: score >= 85 (优秀答案直接跳到 LEVEL_2)
    - LEVEL_0 -> LEVEL_1: score >= 60 (及格答案升级到 LEVEL_1)
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
        if score >= 85:
            return MasteryLevel.LEVEL_2
        elif score >= 60:
            return MasteryLevel.LEVEL_1
    elif current_level == MasteryLevel.LEVEL_1:
        if score >= 85:
            return MasteryLevel.LEVEL_2
    # LEVEL_2 保持不变，任何分数 < 60 也保持不变

    return current_level


class ScorerAgent(BaseAgent[ScoreResult]):
    """Scorer Agent - 答题评分与状态机

    对用户提交的答案进行评分，生成反馈，并更新熟练度等级。
    """

    _prompt_filename = "scorer.md"
    _structured_output_schema = ScoreResult

    def __init__(self, provider: str = "dashscope") -> None:
        """初始化 Scorer Agent

        Args:
            provider: LLM Provider 名称，默认 dashscope
        """
        super().__init__(provider)
        # 禁用 thinking 模式，避免与 structured output 冲突
        self._llm_kwargs = {"extra_body": {"enable_thinking": False}}
        self._qdrant_manager = get_qdrant_manager()

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

    def _parse_response_fallback(
        self,
        response: str,
        question_id: str,
        question_text: str,
        standard_answer: Optional[str],
        user_answer: str,
    ) -> ScoreResult:
        """手动解析 LLM 响应（降级方案）"""
        data = parse_json_response(
            response,
            required_fields=["score", "mastery_level"],
            default_values={
                "score": 0,
                "mastery_level": "LEVEL_0",
                "strengths": [],
                "improvements": [],
                "feedback": "",
            },
        )

        # 解析 mastery_level
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

        # 构建 Prompt
        prompt = self._build_prompt(
            question_text=question_text,
            standard_answer=standard_answer,
            user_answer=user_answer,
            current_level=current_level,
            company=company,
            position=position,
        )

        # 优先尝试使用 structured output
        result = self.invoke_structured(prompt)
        if result is not None:
            # 补充业务字段
            result.question_id = question_id
            result.question_text = question_text
            result.standard_answer = standard_answer
            result.user_answer = user_answer

            # 计算新的等级
            new_level = calculate_new_level(current_level, result.score)
            if new_level != result.mastery_level:
                logger.info(f"Level adjusted: LLM={result.mastery_level.name}, calculated={new_level.name}")
                result.mastery_level = new_level

            # 更新 Qdrant
            if result.mastery_level != current_level:
                self._qdrant_manager.update_question(
                    question_id=question_id,
                    mastery_level=result.mastery_level.value,
                )
                logger.info(f"Updated mastery_level: {current_level.name} -> {result.mastery_level.name}")

            logger.info(f"Scoring completed (structured): score={result.score}, level={result.mastery_level.name}")
            return result

        # 降级到手动解析
        try:
            response = self.invoke_llm(prompt)
            result = self._parse_response_fallback(
                response,
                question_id,
                question_text,
                standard_answer,
                user_answer,
            )

            # 计算新的等级
            new_level = calculate_new_level(current_level, result.score)
            if new_level != result.mastery_level:
                logger.info(f"Level adjusted: LLM={result.mastery_level.name}, calculated={new_level.name}")
                result.mastery_level = new_level

            # 更新 Qdrant
            if result.mastery_level != current_level:
                self._qdrant_manager.update_question(
                    question_id=question_id,
                    mastery_level=result.mastery_level.value,
                )
                logger.info(f"Updated mastery_level: {current_level.name} -> {result.mastery_level.name}")

            logger.info(f"Scoring completed (fallback): score={result.score}, level={result.mastery_level.name}")
            return result
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