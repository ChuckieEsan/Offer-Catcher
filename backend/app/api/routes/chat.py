"""Chat API - AI 对话接口

提供同步和流式对话能力。
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

from langchain_core.messages import HumanMessage, AIMessage

from app.agents.chat_agent import get_chat_agent
from app.utils.logger import logger

router = APIRouter(prefix="/chat", tags=["chat"])


# ========== Request/Response Models ==========

class Message(BaseModel):
    """消息模型"""
    role: str
    content: str


class ChatRequest(BaseModel):
    """对话请求"""
    message: str
    session_id: str = "default"
    history: List[Message] = []


class ChatResponse(BaseModel):
    """对话响应"""
    response: str
    intent: Optional[str] = None


# ========== API Endpoints ==========

@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """同步对话接口

    发送消息并等待完整响应。
    """
    logger.info(f"Chat request: session={request.session_id}, message={request.message[:50]}...")

    agent = get_chat_agent()

    # 转换历史消息
    history_messages = []
    for msg in request.history:
        if msg.role == "user":
            history_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            history_messages.append(AIMessage(content=msg.content))

    # 调用 Agent
    response = agent.chat(
        message=request.message,
        history=history_messages if history_messages else None,
        session_id=request.session_id
    )

    return ChatResponse(response=response)


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """流式对话接口 (SSE)

    使用 Server-Sent Events 返回流式响应。
    """
    logger.info(f"Chat stream request: session={request.session_id}")

    agent = get_chat_agent()

    # 转换历史消息
    history_messages = []
    for msg in request.history:
        if msg.role == "user":
            history_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            history_messages.append(AIMessage(content=msg.content))

    async def generate():
        try:
            async for chunk in agent.achat_streaming(
                message=request.message,
                history=history_messages if history_messages else None,
                session_id=request.session_id
            ):
                # SSE 格式
                yield f"data: {chunk}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: [ERROR] {str(e)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )