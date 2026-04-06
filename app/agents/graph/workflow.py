"""LangGraph 工作流组装

组装 StateGraph 并提供入口函数。
支持同步和流式输出。
"""

from typing import Generator, Optional, Any

from langgraph.graph import END, StateGraph

from app.agents.graph.state import AgentState
from app.agents.graph import nodes, edges


def create_workflow() -> StateGraph:
    """创建 LangGraph 工作流

    工作流结构：
    START → router → (ingest_flow / query_flow / general_chat) → END

    其中 ingest_flow 子图：
    extract → confirm → handle_confirmation → (store_and_mq / extract)

    其中 query_flow 子图：
    query_node → react_loop_node → END
    """
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("router", nodes.router_node)

    # Ingest Flow 节点
    workflow.add_node("extract", nodes.extract_node)
    workflow.add_node("confirm", nodes.confirm_node)
    workflow.add_node("handle_confirmation", nodes.handle_confirmation_node)
    workflow.add_node("store_and_mq", nodes.store_and_mq_node)

    # Query Flow 节点
    workflow.add_node("query_flow", nodes.query_node)
    workflow.add_node("react_loop", nodes.react_loop_node)

    # General Chat 节点
    workflow.add_node("general_chat", nodes.chat_node)

    # 设置边
    workflow.set_entry_point("router")

    # Router → 条件路由
    workflow.add_conditional_edges(
        "router",
        edges.route_by_intent,
        {
            "ingest_flow": "extract",
            "query_flow": "query_flow",
            "general_chat": "general_chat",
            "handle_confirmation": "handle_confirmation",  # 处理确认回复
        }
    )

    # Ingest Flow 内部边
    workflow.add_conditional_edges(
        "extract",
        edges.route_from_ingest,
        {
            "confirm": "confirm",
        }
    )

    # Confirm → 等待用户确认（回到 router 处理用户回复）

    # Handle Confirmation → 条件路由
    workflow.add_conditional_edges(
        "handle_confirmation",
        edges.route_by_confirmation,
        {
            "store_and_mq": "store_and_mq",
            "extract": "extract",
        }
    )

    # Store → 结束子图
    workflow.add_edge("store_and_mq", END)

    # Query Flow → ReAct 循环 → 结束
    workflow.add_edge("query_flow", "react_loop")
    workflow.add_edge("react_loop", END)

    # General Chat → 结束
    workflow.add_edge("general_chat", END)

    return workflow.compile()


# 全局工作流实例
_workflow = None


def get_workflow() -> StateGraph:
    """获取工作流实例（单例）"""
    global _workflow
    if _workflow is None:
        _workflow = create_workflow()
    return _workflow


def run_workflow(
    messages: list,
    intent: str = None,
    params: dict = None,
    extracted_interview=None,
    pending_confirmation: bool = False,
    confirmed_data: bool = False,
    current_subgraph: str = None,
    last_tool_result: str = "",
    context: dict = None,
) -> dict:
    """运行工作流（同步模式）

    Args:
        messages: 对话历史
        intent: 当前意图
        params: 提取的参数
        extracted_interview: 提取的面经数据
        pending_confirmation: 是否在等待确认
        confirmed_data: 用户是否已确认
        current_subgraph: 当前子图
        last_tool_result: 上次工具结果
        context: 全局上下文

    Returns:
        最终状态
    """
    # 初始化状态
    initial_state: AgentState = {
        "messages": messages,
        "intent": intent or "idle",
        "params": params or {},
        "extracted_interview": extracted_interview,
        "pending_confirmation": pending_confirmation,
        "confirmed_data": confirmed_data,
        "current_subgraph": current_subgraph,
        "last_tool_result": last_tool_result,
        "context": context or {},
    }

    workflow = get_workflow()
    result = workflow.invoke(initial_state)

    return result


def stream_workflow(
    messages: list,
    intent: str = None,
    params: dict = None,
    extracted_interview=None,
    pending_confirmation: bool = False,
    confirmed_data: bool = False,
    current_subgraph: str = None,
    last_tool_result: str = "",
    context: dict = None,
) -> Generator[dict, None, None]:
    """运行工作流（流式模式）

    Args:
        messages: 对话历史
        intent: 当前意图
        params: 提取的参数
        extracted_interview: 提取的面经数据
        pending_confirmation: 是否在等待确认
        confirmed_data: 用户是否已确认
        current_subgraph: 当前子图
        last_tool_result: 上次工具结果
        context: 全局上下文

    Yields:
        每个节点的输出字典，包含 node_name 和 output
    """
    # 初始化状态
    initial_state: AgentState = {
        "messages": messages,
        "intent": intent or "idle",
        "params": params or {},
        "extracted_interview": extracted_interview,
        "pending_confirmation": pending_confirmation,
        "confirmed_data": confirmed_data,
        "current_subgraph": current_subgraph,
        "last_tool_result": last_tool_result,
        "context": context or {},
    }

    workflow = get_workflow()

    # 使用 stream 模式
    for event in workflow.stream(initial_state, stream_mode="updates"):
        # event 是 {node_name: output} 的字典
        for node_name, output in event.items():
            yield {
                "node": node_name,
                "output": output,
            }


__all__ = [
    "create_workflow",
    "get_workflow",
    "run_workflow",
    "stream_workflow",
    "AgentState",
]