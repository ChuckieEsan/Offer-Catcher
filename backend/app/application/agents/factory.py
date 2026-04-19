"""Agent 组装代码

负责组装 Agent 实例，注入依赖。
遵循 DDD 原则：组装代码允许引用 Infrastructure 层。

组装函数列表：
- get_answer_specialist: 组装 AnswerSpecialistAgent
- get_vision_extractor: 组装 VisionExtractor
- get_title_generator: 组装 TitleGeneratorAgent
- get_scorer_agent: 组装 ScorerAgent

Domain Service 接口适配器：
- get_answer_generator: 获取 AnswerGenerator 接口
- get_interview_extractor: 获取 InterviewExtractor 接口
"""

from __future__ import annotations

from typing import Optional

from app.infrastructure.adapters.llm_adapter import get_llm
from app.infrastructure.adapters.web_search_adapter import get_web_search_adapter
from app.infrastructure.adapters.ocr_adapter import get_ocr_adapter
from app.infrastructure.persistence.qdrant.question_repository import get_question_repository

from app.application.agents.answer_specialist.agent import AnswerSpecialistAgent
from app.application.agents.vision_extractor.agent import VisionExtractor
from app.application.agents.title_generator.agent import TitleGeneratorAgent
from app.application.agents.scorer.agent import ScorerAgent

from app.application.agents.answer_specialist.prompts import PROMPTS_DIR as ANSWER_PROMPTS
from app.application.agents.vision_extractor.prompts import PROMPTS_DIR as VISION_PROMPTS
from app.application.agents.title_generator.prompts import PROMPTS_DIR as TITLE_PROMPTS
from app.application.agents.scorer.prompts import PROMPTS_DIR as SCORER_PROMPTS


# ========== 单例缓存 ==========

_answer_specialist: Optional[AnswerSpecialistAgent] = None
_vision_extractor: Optional[VisionExtractor] = None
_title_generator: Optional[TitleGeneratorAgent] = None
_scorer_agent: Optional[ScorerAgent] = None


# ========== Agent 组装函数 ==========


def get_answer_specialist() -> AnswerSpecialistAgent:
    """组装 AnswerSpecialistAgent

    注入依赖：
    - LLM (deepseek chat)
    - WebSearchAdapter

    Returns:
        AnswerSpecialistAgent 实例
    """
    global _answer_specialist
    if _answer_specialist is None:
        llm = get_llm("deepseek", "chat")
        web_search_adapter = get_web_search_adapter()
        _answer_specialist = AnswerSpecialistAgent(
            llm=llm,
            web_search_adapter=web_search_adapter,
            prompts_dir=ANSWER_PROMPTS,
        )
    return _answer_specialist


def get_vision_extractor() -> VisionExtractor:
    """组装 VisionExtractor

    注入依赖：
    - LLM (deepseek chat)
    - OCRAdapter

    Returns:
        VisionExtractor 实例
    """
    global _vision_extractor
    if _vision_extractor is None:
        llm = get_llm("deepseek", "chat")
        ocr_adapter = get_ocr_adapter()
        _vision_extractor = VisionExtractor(
            llm=llm,
            ocr_adapter=ocr_adapter,
            prompts_dir=VISION_PROMPTS,
        )
    return _vision_extractor


def get_title_generator() -> TitleGeneratorAgent:
    """组装 TitleGeneratorAgent

    注入依赖：
    - LLM (deepseek chat)

    Returns:
        TitleGeneratorAgent 实例
    """
    global _title_generator
    if _title_generator is None:
        llm = get_llm("deepseek", "chat")
        _title_generator = TitleGeneratorAgent(
            llm=llm,
            prompts_dir=TITLE_PROMPTS,
        )
    return _title_generator


def get_scorer_agent() -> ScorerAgent:
    """组装 ScorerAgent

    注入依赖：
    - LLM (deepseek chat)
    - QuestionRepository

    Returns:
        ScorerAgent 实例
    """
    global _scorer_agent
    if _scorer_agent is None:
        llm = get_llm("deepseek", "chat")
        question_repo = get_question_repository()
        _scorer_agent = ScorerAgent(
            llm=llm,
            question_repo=question_repo,
            prompts_dir=SCORER_PROMPTS,
        )
    return _scorer_agent


# ========== Domain Service 接口适配器 ==========


def get_answer_generator():
    """获取 AnswerGenerator（Domain Service 接口）

    Returns AnswerSpecialistAgent 实例，满足 Protocol 约定。
    """
    return get_answer_specialist()


def get_interview_extractor():
    """获取 InterviewExtractor（Domain Service 接口）

    Returns VisionExtractor 实例，满足 Protocol 约定。
    """
    return get_vision_extractor()


__all__ = [
    # Agent 组装函数
    "get_answer_specialist",
    "get_vision_extractor",
    "get_title_generator",
    "get_scorer_agent",
    # Domain Service 接口适配器
    "get_answer_generator",
    "get_interview_extractor",
]