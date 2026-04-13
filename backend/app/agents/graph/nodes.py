"""LangGraph 节点实现

包含 router、ingest_flow、react_loop 等核心节点。
"""

from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, trim_messages
from langchain_core.runnables import RunnableConfig
from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

from app.agents.graph.state import AgentState
from app.agents.vision_extractor import get_vision_extractor
from app.utils.logger import logger
from app.utils.telemetry import traced_async
from app.llm import get_llm
from app.utils.cache import singleton
from app.agents.prompts import load_prompt_template
from app.tools.search_question_tool import search_questions
from app.tools.web_search_tool import search_web
from app.tools.query_graph_tool import query_graph
from app.tools.memory_tools import (
    load_memory_reference,
    search_session_history,
    load_skill,
    UserContext,
)
from app.memory.io import read_memory
from app.memory.init import ensure_user_memory
from app.memory.store import get_memory_store


# ==================== State Gate Node ====================

def state_gate_node(state: AgentState) -> AgentState:
    """状态门节点

    这个节点不做任何事情，只是作为入口点。
    实际路由逻辑在 edges.state_gate 中处理。
    """
    # 直接返回空更新，让流程继续到 router
    return {}


# ==================== Router Node ====================

# 轻量级路由 Prompt（二分类）
ROUTER_PROMPT = """判断用户意图：
- 如果用户要"录入/上传/导入"面经，回复：ingest
- 其他情况回复：other

只回复一个词，不要其他内容。"""


def router_node(state: AgentState) -> AgentState:
    """轻量级路由节点：二分类判断是否需要 ingest 流程

    使用轻量 prompt 和最小上下文，延迟约 200-500ms。

    Note:
        此节点仅用于内部路由决策，不返回任何用户可见内容。
        避免返回 response_to_user 以免泄露到前端。

    Args:
        state: 当前状态

    Returns:
        包含 intent、params 和 context 的状态更新
    """
    user_input = state["messages"][-1].content
    logger.info(f"Router processing: {user_input[:50]}...")

    # 使用轻量 LLM 调用进行二分类
    llm = get_llm("deepseek", "chat")
    messages = [
        SystemMessage(content=ROUTER_PROMPT),
        HumanMessage(content=user_input),
    ]

    response = llm.invoke(messages)
    intent = response.content.strip().lower()

    logger.info(f"Router result: intent={intent}")

    # 只返回内部状态，session_context 由 LangGraph 自动保留
    return {
        "intent": intent,
        "params": {},
    }


# ==================== Ingest Flow Nodes ====================

def extract_node(state: AgentState) -> AgentState:
    """提取面经节点

    调用 Vision Extractor 从图片/文本中提取面经题目。

    Note:
        当前默认从文本提取。图片处理由前端通过 OCR 完成，
        OCR 结果作为文本消息传入。
    """
    user_input = state["messages"][-1].content

    logger.info("Extracting interview questions...")

    # 使用 Vision Extractor
    extractor = get_vision_extractor()

    try:
        # 这里需要判断是图片还是文本
        # 暂时默认从文本提取
        result = extractor.extract(source=user_input, source_type="text")

        # 更新会话上下文（公司/岗位）
        new_session_context = dict(state.get("session_context", {}))
        if result.company:
            new_session_context["company"] = result.company
        if result.position:
            new_session_context["position"] = result.position

        return {
            "extracted_interview": result,
            "pending_confirmation": True,
            "current_subgraph": "ingest",
            "session_context": new_session_context,
        }
    except Exception as e:
        logger.error(f"Extract failed: {e}")
        return {
            "response_to_user": f"提取失败：{e}",
            "pending_confirmation": False,
        }


def confirm_node(state: AgentState) -> AgentState:
    """确认节点

    展示提取结果给用户，等待用户确认。
    """
    interview = state.get("extracted_interview")
    if not interview:
        return {
            "response_to_user": "没有提取到面经数据",
        }

    # 构建展示给用户的内容
    output = [f"我已提取到以下面经信息：\n"]
    output.append(f"公司：{interview.company}")
    output.append(f"岗位：{interview.position}")
    output.append(f"\n题目列表：\n")

    for i, q in enumerate(interview.questions, 1):
        output.append(f"{i}. {q.question_text}")
        output.append(f"   类型：{q.question_type.value}")
        output.append("")

    output.append("\n请确认以上信息是否正确？回复\"确认\"继续，或提出修改意见。")

    return {
        "response_to_user": "\n".join(output),
    }


def handle_confirmation_node(state: AgentState) -> AgentState:
    """处理用户确认

    根据用户回复决定下一步：
    - 确认：存储并发送 MQ
    - 拒绝：重新提取或退出
    """
    user_input = state["messages"][-1].content.lower().strip()

    if "确认" in user_input or "正确" in user_input or "对" in user_input:
        return {
            "confirmed_data": True,
            "pending_confirmation": False,
        }
    elif "不" in user_input or "错" in user_input or "修改" in user_input:
        # 用户需要修改，重新提取
        return {
            "confirmed_data": False,
            "pending_confirmation": False,
            "extracted_interview": None,  # 清空，让用户重新输入
        }
    else:
        # 模糊回复，再次等待确认
        return {
            "pending_confirmation": True,
        }


def store_and_mq_node(state: AgentState) -> AgentState:
    """存储并发送 MQ

    将提取的题目存储到 Qdrant，并根据类型决定是否发送 MQ。

    Note:
        当前实现仅存储题目，未发送 MQ。
        完整的入库流程（包含 MQ 发送）应使用 `IngestionPipeline.ingest()`。
        MQ 异步答案生成功能在 `app/pipelines/ingestion.py` 中实现。
    """
    from app.db.qdrant_client import get_qdrant_manager
    from app.models.question import QuestionType

    interview = state.get("extracted_interview")
    if not interview:
        return {"response_to_user": "没有可存储的数据"}

    qdrant = get_qdrant_manager()
    stored_count = 0
    mq_count = 0

    for q in interview.questions:
        try:
            # 存储到 Qdrant
            qdrant.upsert_question(q)
            stored_count += 1

            # 分类熔断：knowledge/scenario 需要发 MQ 异步生成答案
            # 注：MQ 发送功能请使用 IngestionPipeline.ingest() 完成
            if q.question_type in [QuestionType.KNOWLEDGE, QuestionType.SCENARIO]:
                mq_count += 1

        except Exception as e:
            logger.error(f"Store failed for {q.question_id}: {e}")

    result = f"已存储 {stored_count} 道题目"
    if mq_count > 0:
        result += f"，其中 {mq_count} 道题目将异步生成答案"

    return {
        "response_to_user": result,
        "current_subgraph": None,  # 退出子图
        "intent": "idle",
    }


# ==================== ReAct Loop Node ====================

@singleton
def _get_react_agent() -> CompiledStateGraph:
    """获取 ReAct Agent 实例（带缓存）

    启用 DeepSeek thinking mode 以支持思考 + 工具调用。
    """
    # 启用 thinking mode
    llm = get_llm("deepseek", "chat", thinking_enabled=True)

    # 基础工具
    tools = [search_questions, search_web, query_graph]

    # 记忆工具（新版）
    tools.extend([
        load_memory_reference,
        search_session_history,
        load_skill,
    ])

    prompt = load_prompt_template("react_agent.md")
    # 提取原始模板字符串（create_agent 接受 str）
    system_prompt = prompt.messages[0].prompt.template
    # 移除 skills_prompt 占位符（暂时不使用 skill 系统）
    system_prompt = system_prompt.replace("{{ skills_prompt }}", "")
    # 添加 context_schema 以支持 ToolRuntime 注入 user_id
    return create_agent(llm, tools=tools, system_prompt=system_prompt, context_schema=UserContext)


def _trim_messages_by_token(
    messages: list[BaseMessage],
    max_tokens: int = 8000,
) -> list[BaseMessage]:
    """使用官方 trim_messages 进行精确 token 裁剪

    策略：
    1. 保留 SystemMessage
    2. 保留最新消息（strategy="last"）
    3. 按 token 数精确裁剪

    Args:
        messages: 原始消息列表
        max_tokens: 最大 token 数，默认 8000

    Returns:
        裁剪后的消息列表
    """
    if len(messages) <= 5:
        return messages

    def simple_token_counter(msgs: list[BaseMessage]) -> int:
        """简单的 token 计数器（基于字符数估算）

        中文字符约 1-2 token，英文约 4 字符 = 1 token
        使用保守估算：每 2 字符 = 1 token
        """
        total = 0
        for m in msgs:
            content = getattr(m, "content", "")
            if content:
                # 保守估算：中英文混合，每 2 字符 = 1 token
                total += len(content) // 2
        return total

    try:
        trimmed = trim_messages(
            messages,
            max_tokens=max_tokens,
            strategy="last",  # 保留最新消息
            include_system=True,  # 保留 system message
            allow_partial=False,  # 不允许截断消息
            token_counter=simple_token_counter,
        )
        logger.info(f"Trimmed messages: {len(messages)} -> {len(trimmed)}")
        return trimmed
    except Exception as e:
        logger.warning(f"trim_messages failed: {e}, fallback to simple trimming")
        # Fallback：保留最近 10 条消息
        system_msgs = [m for m in messages if getattr(m, "type", "") == "system"]
        other_msgs = [m for m in messages if getattr(m, "type", "") != "system"]
        trimmed = other_msgs[-10:]
        if system_msgs:
            trimmed = [system_msgs[0]] + trimmed
        return trimmed


@traced_async
async def react_loop_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """ReAct 循环节点

    执行 ReAct：LLM 决定是否调用工具，如果调用则执行工具并返回结果。

    记忆注入：
    - MEMORY.md 始终加载，注入到 System Prompt
    - 确保用户记忆在首次对话时自动初始化

    Note:
        使用 ainvoke 而不是 astream_events，让外层的 astream_events 自动捕获 token 流。
        LangGraph 会递归地捕获所有子图的事件，包括 LLM 的 token 流和 reasoning_content。
    """
    agent = _get_react_agent()

    # 获取消息并应用裁剪策略
    all_messages: list[BaseMessage] = state.get("messages", [])
    messages: list[BaseMessage] = _trim_messages_by_token(all_messages)

    # 从会话上下文获取用户 ID
    session_context = state.get("session_context", {})
    user_id = session_context.get("user_id") or "default_user"

    # 注入用户记忆上下文（MEMORY.md）
    _inject_memory_context(user_id, messages)

    logger.info(f"ReAct loop starting with {len(messages)} messages (trimmed from {len(all_messages)})")

    try:
        user_runtime_context = UserContext(user_id=user_id)

        result = await agent.ainvoke(
            {"messages": messages},
            context=user_runtime_context,
            config=config
        )

        # 提取最终响应
        if result and "messages" in result:
            last_message = result["messages"][-1]
            if hasattr(last_message, "content"):
                final_response = last_message.content
            else:
                final_response = str(last_message)

            logger.info(f"ReAct completed, response length: {len(final_response)}")
        else:
            logger.warning("ReAct loop returned empty result")
            final_response = "抱歉，我无法处理这个请求。"

        # 返回消息列表，让外层能正确更新状态
        return {
            "messages": result.get("messages", []),
            "response_to_user": final_response,
        }
    except Exception as e:
        logger.error(f"ReAct loop failed: {e}", exc_info=True)
        return {"response_to_user": f"查询失败：{e}"}


def _inject_memory_context(user_id: str, messages: list[BaseMessage]) -> str:
    """注入用户记忆上下文到 System Prompt

    Args:
        user_id: 用户 ID
        messages: 消息列表（会被修改）

    Returns:
        注入的记忆内容（用于日志记录）
    """
    try:
        memory_store = get_memory_store()
        if not memory_store.initialized:
            logger.warning("MemoryStore not initialized, skipping memory injection")
            return ""

        # 确保用户记忆存在（首次对话时自动初始化）
        ensure_user_memory(user_id)

        # 读取 MEMORY.md
        memory_content = read_memory(user_id)
        if not memory_content:
            logger.debug(f"No MEMORY.md found for user {user_id}")
            return ""

        # 构建记忆上下文
        memory_context = f"\n\n<用户记忆>\n{memory_content}\n</用户记忆>"

        # 找到 system message 并追加记忆上下文
        for i, msg in enumerate(messages):
            if getattr(msg, "type", "") == "system":
                original_content = getattr(msg, "content", "")
                if memory_context not in original_content:
                    # 创建新的 SystemMessage，避免修改原对象
                    messages[i] = SystemMessage(content=original_content + memory_context)
                    logger.info(f"Injected MEMORY.md for user {user_id} ({len(memory_content)} chars)")
                break

        return memory_content

    except Exception as e:
        logger.warning(f"Failed to inject memory context: {e}")
        return ""


__all__ = [
    "state_gate_node",
    "router_node",
    "extract_node",
    "confirm_node",
    "handle_confirmation_node",
    "store_and_mq_node",
    "react_loop_node",
]
