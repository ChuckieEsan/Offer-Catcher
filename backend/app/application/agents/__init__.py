"""Application Agents - Agent 实现

Agent 作为 Application 层组件，通过依赖注入实现 Domain 与 Infrastructure 的解耦。

目录结构：
- answer_specialist: 答案生成 Agent
- vision_extractor: 面经提取 Agent
- title_generator: 标题生成 Agent
- scorer: 评分 Agent
- interview: 面试 Agent
- shared: 共享组件（BaseAgent、共享 tools）
"""

from app.application.agents.factory import (
    get_answer_specialist,
    get_vision_extractor,
    get_title_generator,
    get_scorer_agent,
)

__all__ = [
    "get_answer_specialist",
    "get_vision_extractor",
    "get_title_generator",
    "get_scorer_agent",
]