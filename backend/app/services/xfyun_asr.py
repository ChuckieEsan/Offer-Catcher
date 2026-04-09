"""讯飞语音听写 WebSocket 客户端

实现实时语音转文字功能。
"""

import asyncio
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Optional, Callable, AsyncIterator
from urllib.parse import urlencode, quote

import websockets
from pydantic import BaseModel

from app.config.settings import get_settings
from app.utils.logger import logger


class XfyunASRResult(BaseModel):
    """语音识别结果"""
    text: str
    is_final: bool
    confidence: float = 1.0


class XfyunASRClient:
    """讯飞语音听写 WebSocket 客户端

    实现实时语音转文字，支持流式传输。
    """

    def __init__(self):
        """初始化客户端"""
        settings = get_settings()
        self.app_id = settings.xfyun_app_id
        self.api_key = settings.xfyun_api_key
        self.api_secret = settings.xfyun_api_secret

        if not all([self.app_id, self.api_key, self.api_secret]):
            logger.warning("Xfyun credentials not configured, speech recognition will not work")

        # WebSocket 地址
        self.ws_url = "wss://iat-api.xfyun.cn/v2/iat"

    def _generate_url(self) -> str:
        """生成带签名的 WebSocket URL

        Returns:
            带签名的完整 WebSocket URL
        """
        # RFC1123 格式的时间
        now = datetime.now(timezone.utc)
        date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

        # 拼接签名原文
        signature_origin = f"host: iat-api.xfyun.cn\ndate: {date}\nGET /v2/iat HTTP/1.1"

        # 进行 hmac-sha256 加密
        signature_sha = hmac.new(
            self.api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()

        signature_sha_base64 = base64.b64encode(signature_sha).decode("utf-8")

        # 拼接 authorization
        authorization_origin = (
            f'api_key="{self.api_key}", '
            f'algorithm="hmac-sha256", '
            f'headers="host date request-line", '
            f'signature="{signature_sha_base64}"'
        )

        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")

        # 拼接最终 URL
        params = {
            "authorization": authorization,
            "date": date,
            "host": "iat-api.xfyun.cn",
        }

        url = f"{self.ws_url}?{urlencode(params)}"
        return url

    async def recognize_stream(
        self,
        audio_generator: AsyncIterator[bytes],
        language: str = "zh_cn",
    ) -> AsyncIterator[XfyunASRResult]:
        """流式语音识别

        Args:
            audio_generator: 音频数据生成器（PCM 格式，16kHz, 16bit, 单声道）
            language: 语言，zh_cn（中文）或 en_us（英文）

        Yields:
            识别结果
        """
        if not all([self.app_id, self.api_key, self.api_secret]):
            raise ValueError("Xfyun credentials not configured")

        url = self._generate_url()

        try:
            async with websockets.connect(url) as ws:
                # 发送开始帧
                start_frame = {
                    "common": {
                        "app_id": self.app_id,
                    },
                    "business": {
                        "language": language,
                        "domain": "iat",
                        "accent": "mandarin",  # 普通话
                        "vad_eos": 2000,  # 静音检测时长（毫秒）
                        "dwa": "wpgs",  # 动态修正
                        "ptt": 1,  # 添加标点
                    },
                    "data": {
                        "status": 0,  # 首帧
                        "format": "audio/L16;rate=16000",
                        "encoding": "raw",
                        "audio": "",
                    },
                }
                await ws.send(json.dumps(start_frame))

                # 接收结果的协程
                result_queue: asyncio.Queue[Optional[XfyunASRResult]] = asyncio.Queue()

                async def receive_results():
                    """接收识别结果"""
                    # 保存所有句子结果，用于动态修正
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

                            # 解析识别结果
                            result = result_data.get("result", {})
                            ws_list = result.get("ws", [])
                            sn = result.get("sn", 1)  # 句子序号
                            pgs = result.get("pgs")  # 动态修正类型
                            rg = result.get("rg")  # 替换范围

                            # 拼接当前结果的文本
                            text = ""
                            for ws_item in ws_list:
                                for cw_item in ws_item.get("cw", []):
                                    text += cw_item.get("w", "")

                            if pgs == "rpl" and rg:
                                # 替换模式：删除 rg 范围内的结果
                                start_sn, end_sn = rg[0], rg[1]
                                for i in range(start_sn, end_sn + 1):
                                    if i in sentence_results:
                                        del sentence_results[i]

                            # 保存当前句子
                            if text:
                                sentence_results[sn] = text

                            # 拼接所有句子形成完整结果
                            full_text = "".join(
                                sentence_results.get(key, "")
                                for key in sorted(sentence_results.keys())
                            )

                            if full_text:
                                is_final = status == 2
                                await result_queue.put(XfyunASRResult(
                                    text=full_text,
                                    is_final=is_final,
                                ))

                            if is_final:
                                await result_queue.put(None)
                                return
                    except Exception as e:
                        logger.error(f"Error receiving results: {e}")
                        await result_queue.put(None)

                # 启动接收协程
                receive_task = asyncio.create_task(receive_results())

                # 发送音频数据
                frame_count = 0
                async for audio_chunk in audio_generator:
                    # Base64 编码音频数据
                    audio_base64 = base64.b64encode(audio_chunk).decode("utf-8")

                    # 发送音频帧
                    audio_frame = {
                        "data": {
                            "status": 1,  # 中间帧
                            "format": "audio/L16;rate=16000",
                            "encoding": "raw",
                            "audio": audio_base64,
                        },
                    }
                    await ws.send(json.dumps(audio_frame))
                    frame_count += 1

                    # 同时返回识别结果
                    while not result_queue.empty():
                        result = await result_queue.get()
                        if result is None:
                            receive_task.cancel()
                            return
                        yield result

                # 发送结束帧
                end_frame = {
                    "data": {
                        "status": 2,  # 结束帧
                        "format": "audio/L16;rate=16000",
                        "encoding": "raw",
                        "audio": "",
                    },
                }
                await ws.send(json.dumps(end_frame))

                # 继续返回剩余结果
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
            audio_data: 完整音频数据（PCM 格式，16kHz, 16bit, 单声道）
            language: 语言

        Returns:
            识别文本
        """
        async def audio_generator():
            # 分块发送，每块 1280 字节（40ms 音频）
            chunk_size = 1280
            for i in range(0, len(audio_data), chunk_size):
                yield audio_data[i:i + chunk_size]
                await asyncio.sleep(0.04)  # 模拟实时发送

        full_text = ""
        async for result in self.recognize_stream(audio_generator(), language):
            full_text = result.text  # 动态修正会更新文本

        return full_text


# 全局单例
_xfyun_client: Optional[XfyunASRClient] = None


def get_xfyun_client() -> XfyunASRClient:
    """获取讯飞语音客户端单例"""
    global _xfyun_client
    if _xfyun_client is None:
        _xfyun_client = XfyunASRClient()
    return _xfyun_client


__all__ = [
    "XfyunASRClient",
    "XfyunASRResult",
    "get_xfyun_client",
]