"""LangGraph 工作流状态定义

定义 AgentState 和相关类型。
"""

from typing import Optional

from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict

from app.models.schemas import ExtractedInterview


class AgentState(TypedDict):
    """LangGraph Agent 状态

    Attributes:
        messages: 对话历史（整个会话）
        intent: 当前意图：idle/ingest/query/general
        params: 提取的参数（company, position, question 等）
        extracted_interview: 导入面经时提取的数据
        pending_confirmation: 是否在等待用户确认
        confirmed_data: 用户是否已确认（用于确认节点）
        current_subgraph: 当前子图：None/ingest/query
        last_tool_result: 上次工具调用结果
        context: 全局上下文（company, position 等）
    """

    # 对话历史
    messages: list[BaseMessage]

    # 意图和参数
    intent: str
    params: dict

    # 导入面经相关
    extracted_interview: Optional[ExtractedInterview]
    pending_confirmation: bool
    confirmed_data: bool

    # 子图状态
    current_subgraph: Optional[str]

    # 工具调用结果
    last_tool_result: str

    # 全局上下文
    context: dict


__all__ = ["AgentState"]