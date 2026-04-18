"""Chat Agent - AI 面试助手

基于 LangGraph ReAct 工作流，支持：
- 多模式对话（导入面经、查询、闲聊）
- 流式输出
- 通过 Checkpointer 自动状态恢复

状态管理：
- 完全依赖 LangGraph Checkpointer（PostgreSQL）
- 移除内存状态存储，避免数据不一致
"""

from typing import Optional, Generator, AsyncGenerator
import queue
import threading
import asyncio

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from app.agents.graph import run_workflow
from app.agents.graph.workflow import astream_workflow
from app.infrastructure.common.logger import logger
from app.infrastructure.common.cache import singleton


class ChatAgent:
    """AI 面试助手 Agent

    基于 LangGraph ReAct 工作流，支持：
    - search_questions: 向量检索题目
    - search_web: Web 搜索
    - query_graph: 图数据库查询
    - extract_interview: 提取面经（带确认流程）

    状态管理：
    - 使用 conversation_id 作为 thread_id
    - Checkpointer 自动恢复和保存状态
    - 无需手动维护会话状态
    """

    def __init__(self, provider: str = "deepseek") -> None:
        self.provider = provider

    async def achat_streaming(
        self,
        message: str,
        conversation_id: str,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[dict, None]:
        """处理用户消息（异步流式模式）

        状态由 LangGraph Checkpointer 自动管理：
        - 执行前：根据 conversation_id (thread_id) 恢复之前的 AgentState
        - 执行后：自动保存新的 AgentState

        Args:
            message: 用户消息
            conversation_id: 会话 ID（同时作为 thread_id）
            user_id: 用户 ID（用于长期记忆检索，可选）

        Yields:
            流式事件对象 {"type": "token"/"reasoning"/"error", "content": str, "node": str}
        """
        logger.info(f"ChatAgent streaming: conversation={conversation_id}, message={message[:50]}...")

        try:
            final_state = None

            async for event in astream_workflow(
                # 只传入当前消息，历史由 Checkpointer 恢复
                messages=[HumanMessage(content=message)],
                # 其他状态字段不传，由 Checkpointer 恢复
                thread_id=conversation_id,
                user_id=user_id,  # 传入 user_id 以检索长期记忆
            ):
                event_type = event.get("type")

                if event_type == "token":
                    # LLM token 级流式输出
                    yield event

                elif event_type == "reasoning":
                    # DeepSeek thinking mode 思考过程
                    yield event

                elif event_type == "update":
                    # 工具调用完成的状态更新
                    # 不输出内容，因为 token 流已经包含了 LLM 的输出
                    # 只记录状态用于后续处理
                    final_state = event.get("state")

                elif event_type == "final":
                    # 最终结果状态记录
                    final_state = event.get("state", final_state)

                elif event_type == "error":
                    yield event

            logger.info("ChatAgent streaming completed")

        except Exception as e:
            logger.error(f"ChatAgent streaming error: {e}")
            yield {"type": "error", "content": f"\n抱歉，我遇到了问题: {e}"}

    def chat_streaming(
        self,
        message: str,
        conversation_id: str,
        user_id: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """处理用户消息（同步流式模式的 Wrapper）

        专门适配如 Streamlit 等同步渲染框架，通过独立的后台线程事件循环运行异步的
        achat_streaming 生成器，并将产出的 chunk 通过线程安全的 queue 推送过来。
        """
        q = queue.Queue()

        async def run_async():
            try:
                async for chunk in self.achat_streaming(message, conversation_id, user_id):
                    q.put(("chunk", chunk))
            except Exception as e:
                q.put(("error", e))
            finally:
                q.put(("done", None))

        def thread_worker():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_async())
            finally:
                loop.close()

        t = threading.Thread(target=thread_worker, daemon=True)
        t.start()

        while True:
            item_type, item = q.get()
            if item_type == "done":
                break
            elif item_type == "error":
                logger.error(f"Error in synchronous stream wrapper: {item}")
                yield f"\n[Stream Error] {str(item)}"
                break
            elif item_type == "chunk":
                yield item


@singleton
def get_chat_agent(provider: str = "deepseek") -> ChatAgent:
    """获取 Chat Agent 单例

    Note: provider 参数在首次调用后会被忽略。
    """
    return ChatAgent(provider=provider)


__all__ = ["ChatAgent", "get_chat_agent"]