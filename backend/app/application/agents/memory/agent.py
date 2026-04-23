"""Memory Agent

记忆管理 Agent，负责从对话中提取有价值的信息并更新用户记忆。

使用 langchain.agents.create_agent 创建 Agent，
Agent 自主调用 Tools 完成记忆更新。

共享上下文机制：
- 传入游标前历史消息 + 游标后新消息
- Agent 分析新消息与历史的关系，识别行为模式
- 游标更新由确定性代码执行
"""

from pathlib import Path

from langchain_core.messages import (
    HumanMessage,
    BaseMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
)
from langchain.agents import create_agent

from app.infrastructure.adapters.llm_adapter import get_llm
from app.infrastructure.common.logger import logger
from app.infrastructure.common.prompt import load_prompt_template, build_prompt
from app.application.agents.memory.tools import (
    write_session_summary,
    update_preferences,
    update_behaviors,
    update_memory_index,
)
from app.application.agents.memory.cursor import (
    get_cursor,
    has_memory_writes_since,
    get_messages_since_cursor,
    save_cursor,
)
from app.infrastructure.persistence.postgres import (
    get_memory_repository,
    get_session_summary_repository,
)


# Memory Agent Tools 列表（不包含 update_cursor，游标更新由确定性代码执行）
MEMORY_AGENT_TOOLS = [
    write_session_summary,
    update_preferences,
    update_behaviors,
    update_memory_index,
]


# Prompts 目录路径
PROMPTS_DIR = Path(__file__).parent / "prompts"


def create_memory_agent():
    """创建记忆管理 Agent

    使用 create_agent 创建 Agent，Agent 通过 ReAct 模式自主调用 Tools。

    Returns:
        CompiledStateGraph 实例
    """
    llm = get_llm("deepseek", "chat")

    # 加载 Prompt
    prompt = load_prompt_template("memory_agent.md", PROMPTS_DIR)

    # 提取原始模板字符串
    system_prompt = prompt.messages[0].prompt.template

    agent = create_agent(
        llm,
        tools=MEMORY_AGENT_TOOLS,
        system_prompt=system_prompt,
    )

    return agent


async def run_memory_agent(
    user_id: str,
    conversation_id: str,
    messages: list[BaseMessage],
) -> None:
    """执行记忆 Agent

    Agent 自主分析消息并调用 Tools 完成记忆更新。
    这是 fire-and-forget 操作，不阻塞主流程。

    共享上下文机制：
    - 游标前历史：用于识别行为模式（对比新消息）
    - 游标后新消息：重点分析内容
    - 游标更新：确定性执行，不依赖 Agent

    Args:
        user_id: 用户唯一标识
        conversation_id: 对话唯一标识
        messages: LangChain 消息列表（完整对话历史）
    """
    try:
        # 1. 获取游标位置
        cursor_uuid = get_cursor(user_id, conversation_id)

        # 2. 检查游标互斥（主 Agent 是否已写入记忆）
        if cursor_uuid and has_memory_writes_since(messages, cursor_uuid):
            logger.info("Memory update skipped: main agent already wrote")
            return

        # 3. 获取游标后的新消息
        new_messages = get_messages_since_cursor(messages, cursor_uuid)

        if not new_messages:
            logger.info("No new messages to process")
            return

        # 4. 获取游标前的历史消息（用于行为模式分析）
        history_messages = _get_messages_before_cursor(messages, cursor_uuid)

        # 5. 获取已有会话摘要（用于去重）
        summary_repo = get_session_summary_repository()
        recent_summaries = summary_repo.get_recent(user_id, limit=10)
        memory_context = _format_session_summaries(recent_summaries)

        # 6. 获取当前 preferences 和 behaviors
        with get_memory_repository() as repo:
            current_preferences = repo.read_reference(user_id, "preferences")
            current_behaviors = repo.read_reference(user_id, "behaviors")

        # 7. 格式化消息（包含工具调用信息）
        formatted_history = _format_messages_rich(history_messages, max_messages=10)
        formatted_new = _format_messages_rich(new_messages)

        # 8. 获取最新消息的 UUID（用于更新游标）
        latest_uuid = _get_latest_message_uuid(new_messages)

        # 9. 使用 build_prompt 渲染提示词模板
        rendered_prompt = build_prompt(
            "memory_agent.md",
            PROMPTS_DIR,
            memory_context=memory_context,
            history_messages=formatted_history,
            new_messages=formatted_new,
            current_preferences=current_preferences or "",
            current_behaviors=current_behaviors or "",
            conversation_id=conversation_id,
            user_id=user_id,
        )

        # 10. 创建 Agent
        agent = create_memory_agent()

        # 11. 构建输入消息（使用渲染后的完整提示词）
        input_messages = [
            HumanMessage(content=rendered_prompt),
        ]

        # 12. 调用 Agent（Agent 自主调用 Tools，不含 update_cursor）
        await agent.ainvoke({"messages": input_messages})

        # 13. 确定性更新游标（无论 Agent 结果如何，都要更新）
        if latest_uuid:
            save_cursor(user_id, conversation_id, latest_uuid)
            logger.info(f"Cursor updated deterministically: {latest_uuid}")

        logger.info(f"Memory agent completed for conversation {conversation_id}")

    except Exception as e:
        logger.error(f"Memory agent failed: {e}", exc_info=True)


def _get_messages_before_cursor(
    messages: list[BaseMessage],
    cursor_uuid: str | None,
) -> list[BaseMessage]:
    """获取游标前的历史消息"""
    if not cursor_uuid:
        return messages

    for i, msg in enumerate(messages):
        msg_id = getattr(msg, "id", None) or getattr(msg, "uuid", None)
        if msg_id == cursor_uuid:
            return messages[:i]

    return messages


def _format_messages_rich(
    messages: list[BaseMessage],
    max_messages: int | None = None,
) -> str:
    """格式化消息列表（包含工具调用信息）

    Args:
        messages: LangChain 消息列表
        max_messages: 最大消息数（用于限制历史消息长度）

    Returns:
        格式化后的文本
    """
    if not messages:
        return "（无消息）"

    # 限制消息数量
    if max_messages:
        messages = messages[-max_messages:]

    lines = []
    for msg in messages:
        # 使用 isinstance 严格类型检查
        if isinstance(msg, HumanMessage):
            lines.append(f"用户: {msg.content}")

        elif isinstance(msg, AIMessage):
            lines.append(f"AI: {msg.content}")

            # 提取工具调用信息（只保留 name 和 args）
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_name = tc.get("name", "unknown")
                    tool_args = tc.get("args", {})
                    args_str = str(tool_args)
                    lines.append(f"调用工具: {tool_name}({args_str})")

        elif isinstance(msg, ToolMessage):
            # 工具返回结果不参与记忆分析，跳过
            continue

        elif isinstance(msg, SystemMessage):
            # SystemMessage 不参与记忆分析
            continue

        lines.append("")  # 消息间分隔

    return "\n".join(lines)


def _format_session_summaries(summaries: list) -> str:
    """格式化会话摘要列表（清单格式，用于去重检查）

    Args:
        summaries: SessionSummary 实体列表

    Returns:
        格式化后的清单文本
    """
    if not summaries:
        return "（无历史摘要）"

    lines = []
    for s in summaries:
        # 使用 created_at 作为日期（last_accessed 可能为 None）
        date_str = s.created_at.strftime("%Y-%m-%d")
        layer = s.memory_layer.value
        lines.append(f"• {s.summary} [{date_str}, {layer}]")

    return "\n".join(lines)


def _get_latest_message_uuid(messages: list[BaseMessage]) -> str | None:
    """获取最新消息的 UUID"""
    if not messages:
        return None

    last_msg = messages[-1]
    return getattr(last_msg, "id", None) or getattr(last_msg, "uuid", None)


__all__ = [
    "create_memory_agent",
    "run_memory_agent",
    "MEMORY_AGENT_TOOLS",
]