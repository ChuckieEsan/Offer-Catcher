"""LangGraph 节点实现

包含 router、ingest_flow、query_flow 等核心节点。
"""

from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage

from app.agents.graph.state import AgentState
from app.agents.router import get_router_agent
from app.agents.vision_extractor import get_vision_extractor
from app.models.schemas import ExtractedInterview
from app.utils.logger import logger
from app.config.settings import create_llm
from app.skills import get_skills_prompt


# ==================== Router Node ====================

def router_node(state: AgentState) -> AgentState:
    """意图识别节点

    使用 Router Agent 分析用户输入，识别意图并提取参数。
    """
    user_input = state["messages"][-1].content
    logger.info(f"Router processing: {user_input[:50]}...")

    # 使用 Router Agent
    router = get_router_agent()
    result = router.route(user_input)

    # 更新状态
    new_state: AgentState = {
        "intent": result.intent.value,
        "params": result.params,
    }

    # 如果识别到公司/岗位，更新全局上下文
    if result.params.get("company"):
        state["context"]["company"] = result.params["company"]
    if result.params.get("position"):
        state["context"]["position"] = result.params["position"]

    logger.info(f"Router result: intent={result.intent.value}, params={result.params}")
    return new_state


# ==================== Ingest Flow Nodes ====================

def extract_node(state: AgentState) -> AgentState:
    """提取面经节点

    调用 Vision Extractor 从图片/文本中提取面经题目。
    """
    user_input = state["messages"][-1].content

    # 判断是图片还是文本
    # 这里需要根据实际情况判断，简化处理：假设用户上传的是图片路径或直接文本
    # TODO: 需要从 UI 层传入 source_type

    logger.info("Extracting interview questions...")

    # 使用 Vision Extractor
    extractor = get_vision_extractor()

    try:
        # 这里需要判断是图片还是文本
        # 暂时默认从文本提取
        result = extractor.extract(source=user_input, source_type="text")

        # 更新上下文（公司/岗位）
        if result.company:
            state["context"]["company"] = result.company
        if result.position:
            state["context"]["position"] = result.position

        return {
            "extracted_interview": result,
            "pending_confirmation": True,
            "current_subgraph": "ingest",
        }
    except Exception as e:
        logger.error(f"Extract failed: {e}")
        return {
            "last_tool_result": f"提取失败: {e}",
            "pending_confirmation": False,
        }


def confirm_node(state: AgentState) -> AgentState:
    """确认节点

    展示提取结果给用户，等待用户确认。
    """
    interview = state.get("extracted_interview")
    if not interview:
        return {
            "last_tool_result": "没有提取到面经数据",
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
        "last_tool_result": "\n".join(output),
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
    """
    from app.db.qdrant_client import get_qdrant_manager
    from app.models.enums import QuestionType

    interview = state.get("extracted_interview")
    if not interview:
        return {"last_tool_result": "没有可存储的数据"}

    qdrant = get_qdrant_manager()
    stored_count = 0
    mq_count = 0

    for q in interview.questions:
        try:
            # 存储到 Qdrant
            qdrant.upsert_question(q)
            stored_count += 1

            # 分类熔断：knowledge/scenario 需要发 MQ 异步生成答案
            if q.question_type in [QuestionType.KNOWLEDGE, QuestionType.SCENARIO]:
                # TODO: 发送 MQ
                mq_count += 1

        except Exception as e:
            logger.error(f"Store failed for {q.question_id}: {e}")

    result = f"已存储 {stored_count} 道题目"
    if mq_count > 0:
        result += f"，其中 {mq_count} 道题目将异步生成答案"

    return {
        "last_tool_result": result,
        "current_subgraph": None,  # 退出子图
        "intent": "idle",
    }


# ==================== Query Flow Node ====================

def query_node(state: AgentState) -> AgentState:
    """查询节点 - ReAct 循环入口

    使用 LangGraph ReAct 模式，让 LLM 自主决策调用工具。
    本节点负责初始化 ReAct 循环，后续通过 should_continue 边判断是否继续。
    """
    # 这个节点只是标记进入 ReAct 循环
    # 实际的工具调用在 react_loop 节点中进行
    return {"current_subgraph": "query"}


def react_loop_node(state: AgentState) -> AgentState:
    """ReAct 循环节点

    执行一步 ReAct：LLM 决定是否调用工具，如果调用则执行工具并返回结果。
    使用新版 LangChain create_agent API。
    """
    from langchain.agents import create_agent
    from app.tools.search_question_tool import search_questions
    from app.tools.web_search_tool import search_web
    from app.tools.query_graph_tool import query_graph

    # 构建 LLM 和工具
    # 注意：MiniMax-M2.5 必须开启 thinking 模式
    llm = create_llm("dashscope", "chat")
    tools = [search_questions, search_web, query_graph]

    skills_prompt = get_skills_prompt()
    system_prompt = f"""你是一个 AI 面试助手。

你的能力：
1. 搜索题目：当用户提问技术问题时，调用 search_questions 或 search_web
2. 查询知识图谱：当用户询问知识点之间的关系时，调用 query_graph

注意：
- 回答要专业、准确
- 如果不确定信息，说明不确定的原因

{skills_prompt}"""

    # 使用新版 create_agent API
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
    )

    # 获取最近的消息
    messages = state["messages"][-10:]

    try:
        # 调用 agent
        result = agent.invoke({"messages": messages})
        # result 是 AgentState，包含 messages
        response = result.get("messages", [])
        if response and hasattr(response[-1], "content"):
            final_response = response[-1].content
        else:
            final_response = str(result)
        return {"last_tool_result": final_response}
    except Exception as e:
        logger.error(f"ReAct loop failed: {e}")
        return {"last_tool_result": f"查询失败: {e}"}


# ==================== General Chat Node ====================

def chat_node(state: AgentState) -> AgentState:
    """闲聊节点

    处理一般对话，不调用工具。
    """
    from langchain_openai import ChatOpenAI
    from app.config.settings import create_llm

    llm = create_llm("dashscope", "chat")

    skills_prompt = get_skills_prompt()
    system_prompt = f"""你是一个 AI 面试助手，擅长回答面试相关问题。

{skills_prompt}

注意：
- 回答要专业、准确、简洁
- 保持友好的对话风格"""

    messages = state["messages"][-10:]
    messages.insert(0, HumanMessage(content=system_prompt))

    try:
        response = llm.invoke(messages)
        return {"last_tool_result": response.content}
    except Exception as e:
        logger.error(f"Chat failed: {e}")
        return {"last_tool_result": f"抱歉，我遇到了问题: {e}"}


__all__ = [
    "router_node",
    "extract_node",
    "confirm_node",
    "handle_confirmation_node",
    "store_and_mq_node",
    "query_node",
    "react_loop_node",
    "chat_node",
]