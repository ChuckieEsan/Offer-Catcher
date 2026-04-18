"""LangGraph 边和条件路由

实现意图路由、子图内条件边等。
"""

from app.agents.graph.state import AgentState
from app.infrastructure.common.logger import logger


def state_gate(state: AgentState) -> str:
    """状态门节点：优先检查 pending_confirmation

    如果在等待用户确认，优先处理确认流程，避免被 router 误判。
    """
    pending_confirmation = state.get("pending_confirmation", False)
    current_subgraph = state.get("current_subgraph")

    logger.info(f"State gate: pending_confirmation={pending_confirmation}, current_subgraph={current_subgraph}")

    if pending_confirmation and current_subgraph == "ingest":
        return "handle_confirmation"
    else:
        return "router"


def route_by_intent(state: AgentState) -> str:
    """根据 router_node 的输出路由

    Returns:
        分支名称：ingest_flow / react_flow
    """
    intent = state.get("intent", "other")
    logger.info(f"Routing by intent: {intent}")

    if intent == "ingest":
        return "ingest_flow"
    else:
        return "react_flow"


def route_from_ingest(state: AgentState) -> str:
    """导入子图内部路由

    Returns:
        下一步：confirm / store_and_mq / extract
    """
    # 检查是否在等待用户确认
    if state.get("pending_confirmation"):
        return "confirm"

    # 检查是否有提取的数据
    if state.get("extracted_interview"):
        return "confirm"

    # 否则继续提取
    return "extract"


def route_by_confirmation(state: AgentState) -> str:
    """根据确认结果路由

    Returns:
        next: 存储 / extract（重新提取）
    """
    if state.get("confirmed_data"):
        return "store_and_mq"
    else:
        return "extract"  # 重新提取


def should_exit_subgraph(state: AgentState) -> bool:
    """检查是否应该退出子图

    检查条件：
    1. 用户明确说"好了"、"谢谢"、"不导了"等
    2. 当前子图任务已完成
    """
    if not state.get("current_subgraph"):
        return True

    # 检查是否有未完成的确认
    if state.get("pending_confirmation"):
        return False

    # 检查任务是否完成
    if state.get("current_subgraph") == "ingest" and state.get("extracted_interview"):
        if state.get("confirmed_data"):
            return True

    return False


__all__ = [
    "state_gate",
    "route_by_intent",
    "route_from_ingest",
    "route_by_confirmation",
    "should_exit_subgraph",
]