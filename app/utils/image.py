"""图片处理工具模块

提供图片相关的通用工具函数。
"""

import base64
from pathlib import Path
from typing import Optional
from urllib.request import urlopen

from app.utils.logger import logger


def encode_image_to_base64(image_source: str) -> str:
    """将图片转换为 Base64 编码

    支持以下输入类型：
    - 文件路径：本地图片文件
    - URL：http/https 图片链接
    - Base64：已经是 Base64 编码的图片（以 data:image 开头）

    Args:
        image_source: 图片源

    Returns:
        Base64 编码后的字符串（不含 data:image 前缀）

    Raises:
        ValueError: 无效的图片源
    """
    # 已经是 Base64 编码
    if image_source.startswith("data:image"):
        # 返回原始内容（不含 data:image/xxx;base64, 前缀）
        if "," in image_source:
            return image_source.split(",", 1)[1]
        return image_source

    # HTTP/HTTPS URL
    if image_source.startswith("http://") or image_source.startswith("https://"):
        try:
            with urlopen(image_source) as response:
                image_data = response.read()
                return base64.b64encode(image_data).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to download image from URL: {e}")
            raise ValueError(f"Invalid image URL: {image_source}")

    # 本地文件路径
    image_path = Path(image_source)
    if image_path.exists():
        with open(image_path, "rb") as f:
            image_data = f.read()
            return base64.b64encode(image_data).decode("utf-8")

    raise ValueError(f"Invalid image source: {image_source}")


def build_vision_message_content(
    prompt: str,
    image_source: str,
) -> list[dict[str, str]]:
    """构建 Vision 模型的消息内容

    Args:
        prompt: 提示词
        image_source: 图片源（文件路径/URL/Base64）

    Returns:
        LangChain 消息内容列表
    """
    image_base64 = encode_image_to_base64(image_source)
    return [
        {"type": "text", "text": prompt},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
        }
    ]


__all__ = ["encode_image_to_base64", "build_vision_message_content"]