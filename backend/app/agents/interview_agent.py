"""Interview Agent - AI 模拟面试官 Agent (向后兼容)

此文件为向后兼容层，新代码应使用：
    from app.application.agents.interview import InterviewAgent
    from app.application.agents.factory import get_interview_agent
"""

from app.application.agents.interview.agent import InterviewAgent, parse_evaluation


def get_interview_manager():
    """向后兼容：获取 InterviewAgent 实例

    Note: 新代码应使用 get_interview_agent() 代替。
    """
    from app.application.agents.factory import get_interview_agent
    return get_interview_agent()


__all__ = [
    "InterviewAgent",
    "InterviewManager",  # 向后兼容别名
    "get_interview_manager",
    "parse_evaluation",
]

# 向后兼容别名
InterviewManager = InterviewAgent