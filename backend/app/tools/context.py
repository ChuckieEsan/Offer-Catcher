"""运行时上下文定义

定义 Agent 运行时的上下文数据结构，用于 ToolRuntime 注入。
"""

from dataclasses import dataclass


@dataclass
class UserContext:
    """用户运行时上下文

    通过 ToolRuntime.context 注入到工具中，
    用于传递 user_id 等不可变配置。

    Attributes:
        user_id: 用户唯一标识
    """
    user_id: str


__all__ = ["UserContext"]