"""Memory Agent

使用 LangChain 的 create_agent 创建记忆管理 Agent。
Agent 拥有自己的 tools，自主完成记忆更新。

设计要点：
- 使用 create_agent（LangChain 新标准）
- Agent 自主决定调用哪些 tools
- 游标机制避免重复处理
- 游标互斥保证主 Agent 写入不被覆盖

工作流程：
1. Stop Hook 触发 → 调用 Memory Agent
2. 获取游标后的新消息
3. 检查游标互斥
4. Agent 自主分析并调用 tools
5. Agent 最后调用 update_cursor
"""

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from app.llm import get_llm
from app.memory.cursor import (
    get_cursor,
    get_messages_since_cursor,
    get_last_message_uuid,
    has_memory_writes_since,
)
from app.memory.io import read_memory_reference
from app.memory.agent.tools import (
    write_session_summary,
    update_preferences,
    update_behaviors,
    update_memory_index,
    update_cursor,
)
from app.memory.agent.prompts import get_memory_agent_system_prompt
from app.utils.logger import logger
from app.utils.cache import singleton


# ==================== Agent 创建 ====================


@singleton
def _get_memory_agent():
    """获取 Memory Agent 实例（带缓存）

    使用 LangChain 的 create_agent API。
    Agent 拥有自己的 tools，自主决定调用哪些。

    Returns:
        Agent 实例（CompiledStateGraph）
    """
    # 使用 deepseek chat 模型（与其他 agent 一致）
    llm = get_llm("deepseek", "chat")

    # Agent 专用的 tools
    tools = [
        write_session_summary,
        update_preferences,
        update_behaviors,
        update_memory_index,
        update_cursor,
    ]

    # 从 prompts 模块加载 system_prompt
    system_prompt = get_memory_agent_system_prompt()

    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
    )


def create_memory_agent():
    """创建记忆管理 Agent（兼容旧接口）"""
    return _get_memory_agent()


# ==================== Agent 执行 ====================


async def run_memory_agent(
    user_id: str,
    conversation_id: str,
    messages: list,
) -> None:
    """执行记忆 Agent

    流程：
    1. 获取当前游标
    2. 检查游标互斥（主 Agent 已写入则跳过）
    3. 获取游标后的新消息
    4. 获取当前 preferences/behaviors 内容
    5. 构建 Prompt 上下文
    6. 调用 Agent（Agent 自主调用 tools）

    Args:
        user_id: 用户 ID
        conversation_id: 对话 ID
        messages: 消息列表（LangChain message 类型）
    """
    # 1. 获取当前游标
    cursor = get_cursor(user_id, conversation_id)

    # 2. 检查游标互斥
    if has_memory_writes_since(messages, cursor):
        logger.info(
            f"Memory update skipped (main agent wrote): "
            f"user_id={user_id}, conversation_id={conversation_id}"
        )
        # 更新游标到最新位置
        new_cursor = get_last_message_uuid(messages)
        if new_cursor:
            from app.memory.cursor import save_cursor
            save_cursor(user_id, conversation_id, new_cursor)
        return

    # 3. 获取游标后的新消息
    new_messages = get_messages_since_cursor(messages, cursor)

    if not new_messages:
        logger.info(
            f"No new messages after cursor: "
            f"user_id={user_id}, conversation_id={conversation_id}"
        )
        return

    # 4. 获取当前内容
    current_preferences = read_memory_reference(user_id, "preferences")
    current_behaviors = read_memory_reference(user_id, "behaviors")

    # 5. 格式化消息
    formatted_messages = format_messages_for_agent(new_messages)

    # 6. 构建包含上下文的 input
    input_content = f"""请分析以下对话并更新记忆。

<context>
游标后的新消息：
{formatted_messages}

当前 preferences.md：
{current_preferences or '(暂无内容)'}

当前 behaviors.md：
{current_behaviors or '(暂无内容)'}

conversation_id: {conversation_id}
user_id: {user_id}
cursor_uuid: {cursor or '初始'}
</context>
"""

    # 7. 创建 Agent 并调用
    agent = create_memory_agent()

    input_messages = [HumanMessage(content=input_content)]

    # 获取最新消息的 UUID（用于更新游标）
    new_cursor = get_last_message_uuid(messages)

    try:
        result = await agent.ainvoke({"messages": input_messages})

        # 记录 Agent 执行结果
        tool_calls = _extract_tool_calls(result)
        logger.info(
            f"Memory agent completed: user_id={user_id}, "
            f"conversation_id={conversation_id}, tools_called={tool_calls}"
        )

    except Exception as e:
        logger.error(f"Memory agent failed: {e}")
        # 即使失败也要更新游标，避免下次重复处理
        if new_cursor:
            from app.memory.cursor import save_cursor
            save_cursor(user_id, conversation_id, new_cursor)


# ==================== 辅助函数 ====================


def _extract_tool_calls(result: dict) -> list[str]:
    """从 Agent 结果中提取调用的工具名称

    Args:
        result: Agent 执行结果

    Returns:
        调用的工具名称列表
    """
    tool_calls = []
    messages = result.get("messages", [])

    for msg in messages:
        # AI 消息中包含 tool_calls
        if hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls:
                tool_calls.append(tc.get("name", "unknown"))

    return tool_calls


def format_messages_for_agent(messages: list) -> str:
    """格式化消息供 Agent 分析

    Args:
        messages: LangChain message 列表

    Returns:
        格式化的消息文本
    """
    formatted = []

    for msg in messages:
        msg_type = getattr(msg, "type", "")
        content = getattr(msg, "content", "")

        if msg_type == "human" or msg_type == "user":
            role = "用户"
        elif msg_type == "ai" or msg_type == "assistant":
            role = "助手"
        else:
            role = msg_type

        formatted.append(f"{role}: {content}")

    return "\n".join(formatted)


__all__ = [
    "create_memory_agent",
    "run_memory_agent",
]