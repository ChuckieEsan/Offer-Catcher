"""LangGraph 工作流组装

组装 StateGraph 并提供入口函数。
支持同步和流式输出。

工作流结构：
START → state_gate → (router / handle_confirmation)
router → (extract / query_entry / general_chat)
extract → confirm → END
handle_confirmation → (store_and_mq / extract / END)
store_and_mq → END
query_entry → react_loop → END
general_chat → END
"""

from typing import Any, AsyncGenerator

from langgraph.graph import END, StateGraph

from app.agents.graph.state import AgentState
from app.agents.graph import nodes, edges
from app.utils.logger import logger


def create_workflow() -> Any:
    """创建 LangGraph 工作流"""
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("state_gate", nodes.state_gate_node)
    workflow.add_node("router", nodes.router_node)

    # Ingest Flow 节点
    workflow.add_node("extract", nodes.extract_node)
    workflow.add_node("confirm", nodes.confirm_node)
    workflow.add_node("handle_confirmation", nodes.handle_confirmation_node)
    workflow.add_node("store_and_mq", nodes.store_and_mq_node)

    # Query Flow 节点
    workflow.add_node("query_entry", nodes.query_node)
    workflow.add_node("react_loop", nodes.react_loop_node)

    # General Chat 节点
    workflow.add_node("general_chat", nodes.chat_node)

    # 设置入口
    workflow.set_entry_point("state_gate")

    # State Gate → 条件路由
    workflow.add_conditional_edges(
        "state_gate",
        edges.state_gate,
        {
            "handle_confirmation": "handle_confirmation",
            "router": "router",
        }
    )

    # Router → 条件路由
    workflow.add_conditional_edges(
        "router",
        edges.route_by_intent,
        {
            "ingest_flow": "extract",
            "query_flow": "query_entry",
            "general_chat": "general_chat",
        }
    )

    # Extract → Confirm
    workflow.add_edge("extract", "confirm")
    workflow.add_edge("confirm", END)

    # Handle Confirmation → 条件路由
    workflow.add_conditional_edges(
        "handle_confirmation",
        edges.route_by_confirmation,
        {
            "store_and_mq": "store_and_mq",
            "extract": "extract",
        }
    )

    # Store → 结束
    workflow.add_edge("store_and_mq", END)

    # Query Entry → ReAct 循环 → 结束
    workflow.add_edge("query_entry", "react_loop")
    workflow.add_edge("react_loop", END)

    # General Chat → 结束
    workflow.add_edge("general_chat", END)

    return workflow.compile()


# 全局工作流实例
_workflow = None


def get_workflow() -> Any:
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
    """运行工作流（同步模式）"""
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


async def astream_workflow(
    messages: list,
    intent: str = None,
    params: dict = None,
    extracted_interview=None,
    pending_confirmation: bool = False,
    confirmed_data: bool = False,
    current_subgraph: str = None,
    last_tool_result: str = "",
    context: dict = None,
) -> AsyncGenerator[dict, None]:
    """运行工作流（流式模式，异步）

    基于 LangGraph astream_events，自动捕获 LLM Token 流以及节点状态更新。
    输出统一协议：
    {
        "type": "token" | "update" | "final" | "error",
        "node": str,
        "content": str,
        "state": dict | None
    }
    """
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
    final_state = None

    try:
        # 为主工作流设置一个确定的 run_name
        config = {"run_name": "MainWorkflow"}

        async for event in workflow.astream_events(initial_state, config=config, version="v2"):
            kind = event.get("event")
            name = event.get("name")

            # 1. 捕获 LLM 的流式输出 (Token)
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield {
                        "type": "token",
                        "content": chunk.content,
                        "node": name,
                    }

            # 2. 捕获节点/子图完成状态
            elif kind == "on_chain_end":
                output = event.get("data", {}).get("output")
                
                # 记录主工作流的最终输出
                if name == "MainWorkflow":
                    final_state = output
                
                # 针对非流式的节点，提取其 last_tool_result 用于状态更新显示
                elif isinstance(output, dict) and "last_tool_result" in output:
                    # 我们过滤掉内部的 LLM 节点或工具图，只对特定逻辑节点派发 update
                    if name in ["extract", "confirm", "handle_confirmation", "store_and_mq"]:
                        content = output.get("last_tool_result", "")
                        if content:
                            yield {
                                "type": "update",
                                "node": name,
                                "content": content,
                                "state": output,
                            }
    except Exception as e:
        logger.error(f"Stream workflow failed: {e}")
        yield {
            "type": "error",
            "node": "__stream__",
            "content": f"流式输出失败: {e}",
            "state": None,
        }
        return

    # 发送 final 事件
    if final_state:
        yield {
            "type": "final",
            "node": "__end__",
            "content": final_state.get("last_tool_result", ""),
            "state": final_state,
        }


__all__ = [
    "create_workflow",
    "get_workflow",
    "run_workflow",
    "astream_workflow",
    "AgentState",
]