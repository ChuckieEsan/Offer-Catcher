"""图片处理工具模块

提供图片相关的通用工具函数。
作为基础设施层通用组件，为所有层提供图片处理服务。
"""

import base64
from pathlib import Path
from typing import Optional
from urllib.request import urlopen

from app.infrastructure.common.logger import logger


def get_image_mime_type(image_source: str) -> str:
    """获取图片的 MIME 类型

    Args:
        image_source: 图片源（文件路径/URL/Base64）

    Returns:
        MIME 类型字符串（如 "image/jpeg", "image/png", "image/webp"）
    """
    # 从 Base64 数据头检测
    if image_source.startswith("data:image"):
        if "," in image_source:
            prefix = image_source.split(",", 1)[0]
            if "png" in prefix:
                return "image/png"
            elif "webp" in prefix:
                return "image/webp"
            elif "gif" in prefix:
                return "image/gif"
        return "image/jpeg"

    # 从 URL 检测
    if image_source.startswith("http://") or image_source.startswith("https://"):
        try:
            with urlopen(image_source) as response:
                content_type = response.headers.get("Content-Type", "image/jpeg")
                return content_type
        except Exception:
            return "image/jpeg"

    # 从文件扩展名检测
    image_path = Path(image_source)
    ext = image_path.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    if ext in mime_map:
        return mime_map[ext]

    # 从文件内容检测
    try:
        with open(image_path, "rb") as f:
            header = f.read(32)
            if header.startswith(b"\xff\xd8"):
                return "image/jpeg"
            elif header.startswith(b"\x89PNG"):
                return "image/png"
            elif header.startswith(b"GIF"):
                return "image/gif"
            elif header.startswith(b"RIFF") and b"WEBP" in header:
                return "image/webp"
    except Exception:
        pass

    return "image/jpeg"


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
    image_source: str | list[str],
) -> list[dict[str, str]]:
    """构建 Vision 模型的消息内容

    Args:
        prompt: 提示词
        image_source: 图片源（文件路径/URL/Base64），支持单个或多个

    Returns:
        LangChain 消息内容列表
    """
    content: list[dict[str, str]] = [{"type": "text", "text": prompt}]

    # 支持单个或多个图片
    image_sources = [image_source] if isinstance(image_source, str) else image_source

    for img_source in image_sources:
        image_base64 = encode_image_to_base64(img_source)
        mime_type = get_image_mime_type(img_source)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}
        })

    return content


__all__ = [
    "encode_image_to_base64",
    "build_vision_message_content",
    "get_image_mime_type",
]