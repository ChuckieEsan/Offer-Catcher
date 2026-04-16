"""讯飞语音识别适配器

封装讯飞语音听写 WebSocket API，提供实时语音转文字能力。
作为基础设施层适配器，为应用层和领域层提供 ASR 服务。
"""

import asyncio
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Optional, AsyncIterator
from urllib.parse import urlencode

import websockets
from pydantic import BaseModel

from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger


class ASRResult(BaseModel):
    """语音识别结果"""
    text: str
    is_final: bool
    confidence: float = 1.0


class XfyunASRAdapter:
    """讯飞语音识别适配器

    封装讯飞语音听写 WebSocket API，支持流式和单次识别。
    作为基础设施层适配器，提供语音转文字服务。

    设计原则：
    - 封装外部 API（讯飞 WebSocket）
    - 支持依赖注入（便于测试）
    - 结构化返回结果
    """

    def __init__(self) -> None:
        """初始化适配器"""
        settings = get_settings()
        self._app_id = settings.xfyun_app_id
        self._api_key = settings.xfyun_api_key
        self._api_secret = settings.xfyun_api_secret

        if not all([self._app_id, self._api_key, self._api_secret]):
            logger.warning("Xfyun credentials not configured, ASR will not work")

        self._ws_url = "wss://iat-api.xfyun.cn/v2/iat"

    def _generate_url(self) -> str:
        """生成带签名的 WebSocket URL"""
        now = datetime.now(timezone.utc)
        date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

        signature_origin = f"host: iat-api.xfyun.cn\ndate: {date}\nGET /v2/iat HTTP/1.1"

        signature_sha = hmac.new(
            self._api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()

        signature_sha_base64 = base64.b64encode(signature_sha).decode("utf-8")

        authorization_origin = (
            f'api_key="{self._api_key}", '
            f'algorithm="hmac-sha256", '
            f'headers="host date request-line", '
            f'signature="{signature_sha_base64}"'
        )

        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")

        params = {
            "authorization": authorization,
            "date": date,
            "host": "iat-api.xfyun.cn",
        }

        return f"{self._ws_url}?{urlencode(params)}"

    async def recognize_stream(
        self,
        audio_generator: AsyncIterator[bytes],
        language: str = "zh_cn",
    ) -> AsyncIterator[ASRResult]:
        """流式语音识别

        Args:
            audio_generator: 音频数据生成器（PCM 格式，16kHz, 16bit, 单声道）
            language: 语言，zh_cn（中文）或 en_us（英文）

        Yields:
            识别结果
        """
        if not all([self._app_id, self._api_key, self._api_secret]):
            raise ValueError("Xfyun credentials not configured")

        url = self._generate_url()

        try:
            async with websockets.connect(url) as ws:
                start_frame = {
                    "common": {"app_id": self._app_id},
                    "business": {
                        "language": language,
                        "domain": "iat",
                        "accent": "mandarin",
                        "vad_eos": 2000,
                        "dwa": "wpgs",
                        "ptt": 1,
                    },
                    "data": {
                        "status": 0,
                        "format": "audio/L16;rate=16000",
                        "encoding": "raw",
                        "audio": "",
                    },
                }
                await ws.send(json.dumps(start_frame))

                result_queue: asyncio.Queue[Optional[ASRResult]] = asyncio.Queue()

                async def receive_results():
                    sentence_results: dict[int, str] = {}

                    try:
                        async for message in ws:
                            data = json.loads(message)
                            code = data.get("code", 0)

                            if code != 0:
                                error_msg = data.get("message", "Unknown error")
                                logger.error(f"Xfyun ASR error: code={code}, message={error_msg}")
                                await result_queue.put(None)
                                return

                            result_data = data.get("data", {})
                            status = result_data.get("status", 2)

                            result = result_data.get("result", {})
                            ws_list = result.get("ws", [])
                            sn = result.get("sn", 1)
                            pgs = result.get("pgs")
                            rg = result.get("rg")

                            text = ""
                            for ws_item in ws_list:
                                for cw_item in ws_item.get("cw", []):
                                    text += cw_item.get("w", "")

                            if pgs == "rpl" and rg:
                                start_sn, end_sn = rg[0], rg[1]
                                for i in range(start_sn, end_sn + 1):
                                    if i in sentence_results:
                                        del sentence_results[i]

                            if text:
                                sentence_results[sn] = text

                            full_text = "".join(
                                sentence_results.get(key, "")
                                for key in sorted(sentence_results.keys())
                            )

                            if full_text:
                                is_final = status == 2
                                await result_queue.put(ASRResult(
                                    text=full_text,
                                    is_final=is_final,
                                ))

                            if is_final:
                                await result_queue.put(None)
                                return
                    except Exception as e:
                        logger.error(f"Error receiving results: {e}")
                        await result_queue.put(None)

                receive_task = asyncio.create_task(receive_results())

                frame_count = 0
                async for audio_chunk in audio_generator:
                    audio_base64 = base64.b64encode(audio_chunk).decode("utf-8")

                    audio_frame = {
                        "data": {
                            "status": 1,
                            "format": "audio/L16;rate=16000",
                            "encoding": "raw",
                            "audio": audio_base64,
                        },
                    }
                    await ws.send(json.dumps(audio_frame))
                    frame_count += 1

                    while not result_queue.empty():
                        result = await result_queue.get()
                        if result is None:
                            receive_task.cancel()
                            return
                        yield result

                end_frame = {
                    "data": {
                        "status": 2,
                        "format": "audio/L16;rate=16000",
                        "encoding": "raw",
                        "audio": "",
                    },
                }
                await ws.send(json.dumps(end_frame))

                while True:
                    result = await result_queue.get()
                    if result is None:
                        break
                    yield result

                receive_task.cancel()

        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            raise

    async def recognize(
        self,
        audio_data: bytes,
        language: str = "zh_cn",
    ) -> str:
        """单次语音识别

        Args:
            audio_data: 完整音频数据（PCM 格式）
            language: 语言

        Returns:
            识别文本
        """
        async def audio_generator():
            chunk_size = 1280
            for i in range(0, len(audio_data), chunk_size):
                yield audio_data[i:i + chunk_size]
                await asyncio.sleep(0.04)

        full_text = ""
        async for result in self.recognize_stream(audio_generator(), language):
            full_text = result.text

        return full_text


# 单例获取函数
_xfyun_asr_adapter: Optional[XfyunASRAdapter] = None


def get_xfyun_asr_adapter() -> XfyunASRAdapter:
    """获取讯飞语音识别适配器单例

    Returns:
        XfyunASRAdapter 实例
    """
    global _xfyun_asr_adapter
    if _xfyun_asr_adapter is None:
        _xfyun_asr_adapter = XfyunASRAdapter()
    return _xfyun_asr_adapter


__all__ = [
    "ASRResult",
    "XfyunASRAdapter",
    "get_xfyun_asr_adapter",
]