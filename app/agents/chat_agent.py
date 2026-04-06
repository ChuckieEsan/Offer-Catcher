"""Chat Agent - AI 面试助手

基于 LangGraph ReAct 工作流，支持：
- 多模式对话（导入面经、查询、闲聊）
- 流式输出
- 用户确认节点
"""

from typing import Optional, Generator

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from app.agents.graph import run_workflow, stream_workflow
from app.utils.logger import logger


class ChatAgent:
    """AI 面试助手 Agent

    基于 LangGraph ReAct 工作流，支持：
    - search_questions: 向量检索题目
    - search_web: Web 搜索
    - query_graph: 图数据库查询
    - extract_interview: 提取面经（带确认流程）
    """

    def __init__(self, provider: str = "dashscope"):
        self.provider = provider
        # 会话状态存储
        self._session_state: dict = {}

    def _get_session_state(self, session_id: str = "default") -> dict:
        """获取会话状态"""
        if session_id not in self._session_state:
            self._session_state[session_id] = {
                "intent": "idle",
                "params": {},
                "extracted_interview": None,
                "pending_confirmation": False,
                "confirmed_data": False,
                "current_subgraph": None,
                "last_tool_result": "",
                "context": {},
            }
        return self._session_state[session_id]

    def chat(self, message: str, history: Optional[list[BaseMessage]] = None, session_id: str = "default") -> str:
        """处理用户消息（同步模式）

        Args:
            message: 用户消息
            history: 对话历史 (LangChain BaseMessage 列表)
            session_id: 会话 ID

        Returns:
            Agent 回复
        """
        logger.info(f"ChatAgent processing: {message[:50]}...")

        # 构建消息列表
        messages = list(history) if history else []
        messages.append(HumanMessage(content=message))

        # 获取会话状态
        session_state = self._get_session_state(session_id)

        try:
            result = run_workflow(
                messages=messages,
                intent=session_state.get("intent"),
                params=session_state.get("params"),
                extracted_interview=session_state.get("extracted_interview"),
                pending_confirmation=session_state.get("pending_confirmation", False),
                confirmed_data=session_state.get("confirmed_data", False),
                current_subgraph=session_state.get("current_subgraph"),
                last_tool_result=session_state.get("last_tool_result", ""),
                context=session_state.get("context", {}),
            )

            # 更新会话状态
            self._update_session_state(session_id, result)

            response = result.get("last_tool_result", "")
            logger.info(f"ChatAgent response: {response[:50]}...")

            # 更新历史
            messages.append(AIMessage(content=response))

            return response
        except Exception as e:
            logger.error(f"ChatAgent error: {e}")
            return f"抱歉，我遇到了问题: {e}"

    def chat_streaming(self, message: str, history: Optional[list[BaseMessage]] = None, session_id: str = "default") -> Generator[str, None, None]:
        """处理用户消息（流式模式）

        Args:
            message: 用户消息
            history: 对话历史 (LangChain BaseMessage 列表)
            session_id: 会话 ID

        Yields:
            Agent 回复的片段
        """
        logger.info(f"ChatAgent streaming: {message[:50]}...")

        # 构建消息列表
        messages = list(history) if history else []
        messages.append(HumanMessage(content=message))

        # 获取会话状态
        session_state = self._get_session_state(session_id)

        try:
            full_response = ""

            for event in stream_workflow(
                messages=messages,
                intent=session_state.get("intent"),
                params=session_state.get("params"),
                extracted_interview=session_state.get("extracted_interview"),
                pending_confirmation=session_state.get("pending_confirmation", False),
                confirmed_data=session_state.get("confirmed_data", False),
                current_subgraph=session_state.get("current_subgraph"),
                last_tool_result=session_state.get("last_tool_result", ""),
                context=session_state.get("context", {}),
            ):
                node = event.get("node")
                output = event.get("output", {})

                # 只输出最终结果节点的内容
                if node in ["confirm", "react_loop", "general_chat", "store_and_mq"]:
                    content = output.get("last_tool_result", "")
                    if content:
                        # 计算新增内容
                        new_content = content[len(full_response):]
                        full_response = content
                        if new_content:
                            yield new_content

                # 检查是否在等待确认
                if output.get("pending_confirmation"):
                    session_state["pending_confirmation"] = True

            # 更新会话状态
            session_state["last_tool_result"] = full_response
            session_state["intent"] = "idle"
            session_state["current_subgraph"] = None

            logger.info(f"ChatAgent streaming completed: {full_response[:50]}...")

        except Exception as e:
            logger.error(f"ChatAgent streaming error: {e}")
            yield f"抱歉，我遇到了问题: {e}"

    def _update_session_state(self, session_id: str, result: dict):
        """更新会话状态"""
        session_state = self._session_state[session_id]

        # 更新关键状态
        if "intent" in result:
            session_state["intent"] = result["intent"]
        if "params" in result:
            session_state["params"] = result["params"]
        if "extracted_interview" in result:
            session_state["extracted_interview"] = result["extracted_interview"]
        if "pending_confirmation" in result:
            session_state["pending_confirmation"] = result["pending_confirmation"]
        if "confirmed_data" in result:
            session_state["confirmed_data"] = result["confirmed_data"]
        if "current_subgraph" in result:
            session_state["current_subgraph"] = result["current_subgraph"]
        if "last_tool_result" in result:
            session_state["last_tool_result"] = result["last_tool_result"]
        if "context" in result:
            session_state["context"].update(result["context"])

    def clear_session(self, session_id: str = "default"):
        """清除会话状态"""
        if session_id in self._session_state:
            del self._session_state[session_id]


# 全局单例
_chat_agent: Optional[ChatAgent] = None


def get_chat_agent(provider: str = "dashscope") -> ChatAgent:
    """获取 Chat Agent 单例"""
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = ChatAgent(provider=provider)
    return _chat_agent


__all__ = ["ChatAgent", "get_chat_agent"]