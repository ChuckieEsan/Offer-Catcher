"""Chat API - AI 对话接口

提供流式对话能力。
状态由 LangGraph Checkpointer 自动管理，消息同步到 PostgresClient。
"""

import json
from typing import Optional
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.chat_agent import get_chat_agent
from app.db.postgres_client import get_postgres_client
from app.utils.logger import logger

router = APIRouter(prefix="/chat", tags=["chat"])


# ========== Request/Response Models ==========

class ChatRequest(BaseModel):
    """对话请求"""
    message: str
    conversation_id: str
    user_id: Optional[str] = None  # 用户 ID，用于长期记忆


class ChatResponse(BaseModel):
    """对话响应"""
    response: str


# ========== API Endpoints ==========

@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """流式对话接口 (SSE)

    使用 Server-Sent Events 返回流式响应。

    状态管理：
    - LangGraph Checkpointer 自动恢复和保存 AgentState
    - PostgresClient 同步消息用于前端展示

    Args:
        request: 包含 message, conversation_id 和可选的 user_id

    Returns:
        SSE 流式响应
    """
    user_id = request.user_id or "default_user"
    logger.info(f"Chat stream: user={user_id}, conversation={request.conversation_id}, message={request.message[:50]}...")

    agent = get_chat_agent()
    pg = get_postgres_client()

    # 收集完整响应用于同步到 PostgresClient
    response_chunks = []

    async def generate():
        try:
            async for event in agent.achat_streaming(
                message=request.message,
                conversation_id=request.conversation_id,
                user_id=user_id,
            ):
                # event is now a dict with type, content, node fields
                response_chunks.append(event)
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: [ERROR] {str(e)}\n\n"
        finally:
            # 同步消息到 PostgresClient（用于前端历史展示）
            # 只收集 token 事件的 content 用于完整响应
            try:
                token_contents = [
                    e.get("content", "") for e in response_chunks
                    if e.get("type") == "token"
                ]
                full_response = "".join(token_contents)
                pg.add_message(
                    user_id,
                    request.conversation_id,
                    "user",
                    request.message
                )
                pg.add_message(
                    user_id,
                    request.conversation_id,
                    "assistant",
                    full_response
                )
                logger.info(f"Messages synced to PostgresClient: {len(full_response)} chars")
            except Exception as e:
                logger.error(f"Failed to sync messages: {e}")

            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁止 Nginx 缓存  
        }
    )