"""Chat Agent - AI 面试助手

基于 LangGraph ReAct 工作流，支持：
- 多模式对话（导入面经、查询、闲聊）
- 流式输出
- 用户确认节点
"""

from typing import Optional, Generator, AsyncGenerator
import queue
import threading
import asyncio

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from app.agents.graph import run_workflow
from app.agents.graph.workflow import astream_workflow
from app.utils.logger import logger


class ChatAgent:
    """AI 面试助手 Agent

    基于 LangGraph ReAct 工作流，支持：
    - search_questions: 向量检索题目
    - search_web: Web 搜索
    - query_graph: 图数据库查询
    - extract_interview: 提取面经（带确认流程）
    """

    def __init__(self, provider: str = "dashscope") -> None:
        self.provider = provider
        # 会话状态存储
        self._session_state: dict[str, dict] = {}

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
        """处理用户消息（同步模式，使用 asyncio.run 包装）"""
        logger.info(f"ChatAgent processing: {message[:50]}...")

        messages = list(history) if history else []
        messages.append(HumanMessage(content=message))

        session_state = self._get_session_state(session_id)

        try:
            # run_workflow 现在是异步函数，使用 asyncio.run 调用
            result = asyncio.run(run_workflow(
                messages=messages,
                intent=session_state.get("intent"),
                params=session_state.get("params"),
                extracted_interview=session_state.get("extracted_interview"),
                pending_confirmation=session_state.get("pending_confirmation", False),
                confirmed_data=session_state.get("confirmed_data", False),
                current_subgraph=session_state.get("current_subgraph"),
                last_tool_result=session_state.get("last_tool_result", ""),
                context=session_state.get("context", {}),
                thread_id=session_id,
            ))

            self._update_session_state(session_id, result)

            response = result.get("last_tool_result", "")
            logger.info(f"ChatAgent response: {response[:50]}...")

            return response
        except Exception as e:
            logger.error(f"ChatAgent error: {e}")
            return f"抱歉，我遇到了问题: {e}"

    async def achat_streaming(self, message: str, history: Optional[list[BaseMessage]] = None, session_id: str = "default") -> AsyncGenerator[str, None]:
        """处理用户消息（异步流式模式，带持久化）

        session_id 作为 thread_id 传递给 LangGraph，
        实现状态持久化。
        """
        logger.info(f"ChatAgent streaming (async): {message[:50]}..., thread_id={session_id}")

        messages = list(history) if history else []
        messages.append(HumanMessage(content=message))

        session_state = self._get_session_state(session_id)

        try:
            final_state = None

            async for event in astream_workflow(
                messages=messages,
                intent=session_state.get("intent"),
                params=session_state.get("params"),
                extracted_interview=session_state.get("extracted_interview"),
                pending_confirmation=session_state.get("pending_confirmation", False),
                confirmed_data=session_state.get("confirmed_data", False),
                current_subgraph=session_state.get("current_subgraph"),
                last_tool_result=session_state.get("last_tool_result", ""),
                context=session_state.get("context", {}),
                thread_id=session_id,  # 关键：传递 thread_id
            ):
                event_type = event.get("type")

                if event_type == "token":
                    # LLM token 级流式输出
                    content = event.get("content", "")
                    if content:
                        yield content

                elif event_type == "update":
                    # 非 LLM 节点的状态更新
                    content = event.get("content", "")
                    if content:
                        # 确保独立显示在前面，如果需要换行可以用 yield content + "\n\n"
                        yield f"[{event.get('node', '系统')}] {content}\n\n"
                    final_state = event.get("state")

                elif event_type == "final":
                    # 最终结果状态记录
                    final_state = event.get("state", final_state)

                elif event_type == "error":
                    yield f"\n抱歉，我遇到了问题: {event.get('content')}"

            # 更新会话状态
            if final_state:
                self._update_session_state(session_id, final_state)

            logger.info("ChatAgent streaming completed")

        except Exception as e:
            logger.error(f"ChatAgent streaming error: {e}")
            yield f"\n抱歉，我遇到了问题: {e}"

    def chat_streaming(self, message: str, history: Optional[list[BaseMessage]] = None, session_id: str = "default") -> Generator[str, None, None]:
        """处理用户消息（同步流式模式的 Wrapper）
        
        专门适配如 Streamlit 等同步渲染框架，通过独立的后台线程事件循环运行异步的
        achat_streaming 生成器，并将产出的 chunk 通过线程安全的 queue 推送过来。
        """
        q = queue.Queue()

        async def run_async():
            try:
                async for chunk in self.achat_streaming(message, history, session_id):
                    q.put(("chunk", chunk))
            except Exception as e:
                q.put(("error", e))
            finally:
                q.put(("done", None))

        def thread_worker():
            # 创建并设置当前线程的新事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_async())
            finally:
                loop.close()

        # 启动后台线程执行流式调用
        t = threading.Thread(target=thread_worker, daemon=True)
        t.start()

        # 在主线程中同步消费队列并 yield
        while True:
            item_type, item = q.get()
            if item_type == "done":
                break
            elif item_type == "error":
                # 返回错误或抛出异常
                logger.error(f"Error caught in synchronous stream wrapper: {item}")
                yield f"\n[Stream Error] {str(item)}"
                break
            elif item_type == "chunk":
                yield item

    def _update_session_state(self, session_id: str, result: dict):
        """更新会话状态"""
        session_state = self._session_state[session_id]

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
