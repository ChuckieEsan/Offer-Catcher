"""LangGraph 工作流状态定义

定义 AgentState 和相关类型。
使用 Annotated reducer 实现消息自动合并。
"""

from typing import Annotated, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.models.schemas import ExtractedInterview


class SessionContext(TypedDict, total=False):
    """会话上下文

    存储当前会话的运行时状态信息。

    Attributes:
        user_id: 用户唯一标识
        company: 当前公司
        position: 当前岗位
    """
    user_id: str
    company: str
    position: str


class AgentState(TypedDict, total=False):
    """LangGraph Agent 状态

    使用 total=False 支持 partial update，节点可以只返回局部状态。

    Attributes:
        messages: 对话历史（使用 add_messages reducer 自动合并）
        intent: 当前意图：idle/ingest/query/general
        params: 提取的参数（company, position, question 等）
        extracted_interview: 导入面经时提取的数据
        pending_confirmation: 是否在等待用户确认
        confirmed_data: 用户是否已确认（用于确认节点）
        current_subgraph: 当前子图：None/ingest/query
        last_tool_result: 上次工具调用结果
        session_context: 会话上下文（company, position, user_id 等）
        error: 错误信息
    """

    # 对话历史（使用 Annotated reducer 自动合并）
    # add_messages 会将新消息追加到列表末尾，并处理消息删除
    messages: Annotated[list[BaseMessage], add_messages]

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

    # 会话上下文（运行时状态，如 company, position, user_id）
    session_context: SessionContext

    # 错误信息
    error: Optional[str]


__all__ = ["AgentState", "SessionContext"]