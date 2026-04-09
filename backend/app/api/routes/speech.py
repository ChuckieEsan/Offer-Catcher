"""语音识别 WebSocket API

提供实时语音转文字的 WebSocket 接口。
"""

import asyncio
import base64
import json
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from app.services.xfyun_asr import get_xfyun_client, XfyunASRClient
from app.utils.logger import logger

router = APIRouter(tags=["speech"])


async def get_xfyun_client_dep() -> XfyunASRClient:
    """获取讯飞客户端依赖"""
    return get_xfyun_client()


@router.websocket("/ws/speech")
async def speech_websocket(
    websocket: WebSocket,
):
    """语音识别 WebSocket 端点

    前端通过此 WebSocket 发送音频数据，接收识别结果。

    消息格式：
    - 发送: {"type": "audio", "data": "<base64 encoded pcm audio>"}
    - 发送: {"type": "start", "language": "zh_cn"}
    - 发送: {"type": "end"}
    - 接收: {"type": "result", "text": "识别文本", "is_final": false}
    - 接收: {"type": "error", "message": "错误信息"}
    """
    await websocket.accept()
    logger.info("Speech WebSocket connected")

    xfyun_client = get_xfyun_client()

    # 音频缓冲区
    audio_buffer = bytearray()
    audio_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
    result_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

    # 状态
    is_recognizing = False
    language = "zh_cn"
    last_text = ""  # 保存最后的识别文本

    async def audio_generator():
        """音频生成器"""
        while True:
            chunk = await audio_queue.get()
            if chunk is None:
                break
            yield chunk

    async def run_recognition():
        """运行语音识别"""
        nonlocal is_recognizing
        try:
            async for result in xfyun_client.recognize_stream(audio_generator(), language):
                await result_queue.put(result.text)
            await result_queue.put(None)
        except Exception as e:
            logger.error(f"Recognition error: {e}")
            await result_queue.put(None)
        finally:
            is_recognizing = False

    recognition_task = None

    try:
        while True:
            # 接收消息
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "start":
                    # 开始识别
                    language = data.get("language", "zh_cn")
                    audio_buffer.clear()
                    is_recognizing = True
                    last_text = ""  # 清空上次结果

                    # 启动识别任务
                    recognition_task = asyncio.create_task(run_recognition())

                    logger.info(f"Speech recognition started, language={language}")
                    await websocket.send_json({"type": "started"})

                elif msg_type == "audio":
                    # 接收音频数据
                    audio_base64 = data.get("data", "")
                    if audio_base64:
                        audio_chunk = base64.b64decode(audio_base64)
                        await audio_queue.put(audio_chunk)

                elif msg_type == "end":
                    # 结束识别
                    await audio_queue.put(None)  # 发送结束信号

            except asyncio.TimeoutError:
                pass

            # 发送识别结果
            while not result_queue.empty():
                text = await result_queue.get()
                if text is None:
                    # 发送最终结果（使用最后保存的文本）
                    if last_text:
                        await websocket.send_json({"type": "result", "text": last_text, "is_final": True})
                    else:
                        await websocket.send_json({"type": "result", "text": "", "is_final": True})
                    if recognition_task:
                        recognition_task.cancel()
                        recognition_task = None
                else:
                    # 保存中间结果
                    last_text = text
                    await websocket.send_json({"type": "result", "text": text, "is_final": False})

    except WebSocketDisconnect:
        logger.info("Speech WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
    finally:
        if recognition_task:
            recognition_task.cancel()


__all__ = ["router"]