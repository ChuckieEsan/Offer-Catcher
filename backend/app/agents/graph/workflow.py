"""LangGraph 工作流组装

组装 StateGraph 并提供入口函数。
支持异步流式输出和 PostgreSQL 持久化。

工作流结构：
START → state_gate → (router / handle_confirmation)
router → (extract / react_loop)
extract → confirm → END
handle_confirmation → (store_and_mq / extract / END)
store_and_mq → END
react_loop → END
"""

from typing import AsyncGenerator, Optional

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.agents.graph.state import AgentState
from app.agents.graph import nodes, edges
from app.utils.logger import logger
from app.models.schemas import ExtractedInterview


def create_workflow(checkpointer: Optional[AsyncPostgresSaver] = None) -> CompiledStateGraph:
    """创建 LangGraph 工作流

    Args:
        checkpointer: 异步 PostgreSQL checkpointer（可选）
                     如果传入，将启用状态持久化

    Returns:
        CompiledStateGraph 实例
    """
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("state_gate", nodes.state_gate_node)
    workflow.add_node("router", nodes.router_node)

    # Ingest Flow 节点
    workflow.add_node("extract", nodes.extract_node)
    workflow.add_node("confirm", nodes.confirm_node)
    workflow.add_node("handle_confirmation", nodes.handle_confirmation_node)
    workflow.add_node("store_and_mq", nodes.store_and_mq_node)

    # ReAct Loop 节点
    workflow.add_node("react_loop", nodes.react_loop_node)

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
            "react_flow": "react_loop",
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

    # ReAct Loop → 结束
    workflow.add_edge("react_loop", END)

    return workflow.compile(checkpointer=checkpointer)


async def run_workflow(
    messages: list[BaseMessage],
    thread_id: Optional[str] = None,
    **kwargs
) -> AgentState:
    """运行工作流（异步模式，带持久化）

    简化版本：只需要传入 messages 和 thread_id。
    其他状态（intent, params, context 等）由 Checkpointer 自动恢复。

    Args:
        messages: 当前消息（通常只有一条用户消息）
        thread_id: 会话 ID（用于持久化）
        **kwargs: 可选的状态覆盖（通常不需要）

    Returns:
        最终状态
    """
    from app.db.checkpointer import get_checkpointer

    # 构建 initial_state，只传入 messages
    # 其他字段不传，由 Checkpointer 恢复
    initial_state: AgentState = {
        "messages": messages,
    }

    # 如果有额外的状态覆盖（通常不需要）
    for key in ["intent", "params", "extracted_interview", "pending_confirmation",
                "confirmed_data", "current_subgraph", "last_tool_result", "context"]:
        if key in kwargs and kwargs[key] is not None:
            initial_state[key] = kwargs[key]  # type: ignore

    config: RunnableConfig = {
        "configurable": {
            "thread_id": thread_id or "default",
        }
    }

    async with get_checkpointer() as checkpointer:
        workflow = create_workflow(checkpointer=checkpointer)
        result = await workflow.ainvoke(initial_state, config=config)

    return result


async def astream_workflow(
    messages: list[BaseMessage],
    thread_id: Optional[str] = None,
    **kwargs
) -> AsyncGenerator[dict, None]:
    """运行工作流（流式模式，异步）

    简化版本：只需要传入 messages 和 thread_id。
    其他状态由 Checkpointer 自动恢复。

    基于 LangGraph astream_events，自动捕获 LLM Token 流以及节点状态更新。
    输出统一协议：
    {
        "type": "token" | "update" | "final" | "error",
        "node": str,
        "content": str,
        "state": dict | None
    }

    Args:
        messages: 当前消息（通常只有一条用户消息）
        thread_id: 会话 ID（用于持久化）
        **kwargs: 可选的状态覆盖（通常不需要）

    Yields:
        事件流
    """
    from app.db.checkpointer import get_checkpointer

    # 构建 initial_state，只传入 messages
    initial_state: AgentState = {
        "messages": messages,
    }

    # 如果有额外的状态覆盖（通常不需要）
    for key in ["intent", "params", "extracted_interview", "pending_confirmation",
                "confirmed_data", "current_subgraph", "last_tool_result", "context"]:
        if key in kwargs and kwargs[key] is not None:
            initial_state[key] = kwargs[key]  # type: ignore

    final_state = None

    try:
        config: RunnableConfig = {
            "run_name": "MainWorkflow",
            "configurable": {
                "thread_id": thread_id or "default",
            }
        }

        async with get_checkpointer() as checkpointer:
            workflow = create_workflow(checkpointer=checkpointer)

            async for event in workflow.astream_events(initial_state, config=config, version="v2"):
                kind = event.get("event")
                name = event.get("name", "")
                metadata = event.get("metadata", {})

                # 获取 LangGraph 节点名称（用于过滤 router 节点）
                langgraph_node = metadata.get("langgraph_node", "")
                if langgraph_node == "router":
                    continue

                # 1. 捕获 LLM 的流式输出 (Token)
                if kind == "on_chat_model_stream":
                    # 过滤 router 节点的 token 流，避免泄露意图分类结果

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

                    if name == "MainWorkflow":
                        final_state = output

                    # 过滤内部节点（router 等）的输出，避免泄露到前端
                    elif isinstance(output, dict) and "last_tool_result" in output:
                        # 只输出用户可见的节点结果
                        if name in ["extract", "confirm", "handle_confirmation", "store_and_mq", "react_loop"]:
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

    if final_state:
        yield {
            "type": "final",
            "node": "__end__",
            "content": final_state.get("last_tool_result", ""),
            "state": final_state,
        }


__all__ = [
    "create_workflow",
    "run_workflow",
    "astream_workflow",
    "AgentState",
]