"""Chat Agent - AI 面试助手 (向后兼容)

此文件为向后兼容层，新代码应使用：
    from app.application.agents.chat import ChatAgent
    from app.application.agents.factory import get_chat_agent
"""

from app.application.agents.chat.agent import ChatAgent
from app.application.agents.chat.workflow import astream_workflow, run_workflow


def get_chat_agent(provider: str = "deepseek"):
    """向后兼容：获取 ChatAgent 实例

    Note: 新代码应使用 factory.get_chat_agent() 代替。
    """
    from app.application.agents.factory import get_chat_agent
    return get_chat_agent(provider)


__all__ = [
    "ChatAgent",
    "get_chat_agent",
    "astream_workflow",
    "run_workflow",
]