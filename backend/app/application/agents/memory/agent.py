"""Memory Agent

记忆管理 Agent，负责从对话中提取有价值的信息并更新用户记忆。

使用 langchain.agents.create_agent 创建 Agent，
Agent 自主调用 Tools 完成记忆更新。
"""

from pathlib import Path

from langchain_core.messages import HumanMessage, BaseMessage
from langchain.agents import create_agent

from app.infrastructure.adapters.llm_adapter import get_llm
from app.infrastructure.common.logger import logger
from app.infrastructure.common.prompt import load_prompt_template, build_prompt
from app.application.agents.memory.tools import (
    write_session_summary,
    update_preferences,
    update_behaviors,
    update_memory_index,
    update_cursor,
)
from app.application.agents.memory.cursor import (
    get_cursor,
    has_memory_writes_since,
    get_messages_since_cursor,
)
from app.infrastructure.persistence.postgres import get_memory_repository


# Memory Agent Tools 列表
MEMORY_AGENT_TOOLS = [
    write_session_summary,
    update_preferences,
    update_behaviors,
    update_memory_index,
    update_cursor,
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

    Args:
        user_id: 用户唯一标识
        conversation_id: 对话唯一标识
        messages: LangChain 消息列表
    """
    try:
        # 1. 获取游标位置
        cursor_uuid = get_cursor(user_id, conversation_id)

        # 2. 永久游标：如果该用户在该对话中已有游标，跳过处理
        if cursor_uuid:
            logger.info(f"Memory update skipped: cursor already exists for {conversation_id}")
            return

        # 3. 获取游标后的新消息（无游标时处理全部消息）
        new_messages = get_messages_since_cursor(messages, cursor_uuid)

        if not new_messages:
            logger.info("No new messages to process")
            return

        # 4. 获取当前 preferences 和 behaviors
        with get_memory_repository() as repo:
            current_preferences = repo.read_reference(user_id, "preferences")
            current_behaviors = repo.read_reference(user_id, "behaviors")

        # 5. 格式化新消息
        formatted_messages = _format_messages(new_messages)

        # 6. 获取最新消息的 UUID（用于更新游标）
        latest_uuid = _get_latest_message_uuid(new_messages)

        # 7. 使用 build_prompt 渲染提示词模板
        rendered_prompt = build_prompt(
            "memory_agent.md",
            PROMPTS_DIR,
            new_messages=formatted_messages,
            current_preferences=current_preferences or "",
            current_behaviors=current_behaviors or "",
            conversation_id=conversation_id,
            user_id=user_id,
            cursor_uuid=latest_uuid or "",
        )

        # 8. 创建 Agent
        agent = create_memory_agent()

        # 9. 构建输入消息（使用渲染后的完整提示词）
        input_messages = [
            HumanMessage(content=rendered_prompt),
        ]

        # 10. 调用 Agent（Agent 自主调用 Tools）
        await agent.ainvoke({"messages": input_messages})

        logger.info(f"Memory agent completed for conversation {conversation_id}")

    except Exception as e:
        logger.error(f"Memory agent failed: {e}", exc_info=True)


def _format_messages(messages: list[BaseMessage]) -> str:
    """格式化消息列表为文本"""
    lines = []
    for msg in messages:
        msg_type = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", "")
        role = "用户" if msg_type in ["human", "user"] else "AI"
        lines.append(f"{role}: {content[:200]}...")

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