"""LangGraph 边和条件路由

实现意图路由、子图内条件边等。
"""

from app.agents.graph.state import AgentState
from app.utils.logger import logger


def route_by_intent(state: AgentState) -> str:
    """根据意图路由到不同分支

    Returns:
        分支名称：ingest / query / general
    """
    intent = state.get("intent", "general")
    logger.info(f"Routing by intent: {intent}")

    # 检查是否有未完成的子图任务
    if state.get("pending_confirmation"):
        # 在等待确认时，优先处理用户对确认的回复
        if state.get("current_subgraph") == "ingest":
            return "handle_confirmation"

    # 根据意图路由
    if intent == "ingest":
        return "ingest_flow"
    elif intent == "query":
        return "query_flow"
    else:
        return "general_chat"


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
    "route_by_intent",
    "route_from_ingest",
    "route_by_confirmation",
    "should_exit_subgraph",
]