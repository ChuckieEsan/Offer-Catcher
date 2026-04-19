"""智能体定义层（兼容层）

提供旧路径的兼容导入，实际 Agent 位于 application 层。
向后兼容旧导入路径 app.agents.xxx。
"""

from app.application.agents.factory import (
    get_answer_specialist,
    get_vision_extractor,
    get_title_generator,
    get_scorer_agent,
)

from app.application.agents.answer_specialist.agent import AnswerSpecialistAgent
from app.application.agents.vision_extractor.agent import (
    VisionExtractor,
    ExtractedQuestion,
    ExtractedInterviewSchema,
)
from app.application.agents.title_generator.agent import TitleGeneratorAgent
from app.application.agents.scorer.agent import ScorerAgent

__all__ = [
    # Agent 类
    "VisionExtractor",
    "AnswerSpecialistAgent",
    "TitleGeneratorAgent",
    "ScorerAgent",
    # 获取函数
    "get_vision_extractor",
    "get_answer_specialist",
    "get_title_generator",
    "get_scorer_agent",
    # Schema
    "ExtractedQuestion",
    "ExtractedInterviewSchema",
]