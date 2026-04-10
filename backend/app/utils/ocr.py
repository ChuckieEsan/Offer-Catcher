"""OCR 工具模块

使用 EasyOCR 进行文字识别。
支持本地文件路径、URL 和 Base64 编码的图片。
"""

import base64
import tempfile
from pathlib import Path
from urllib.request import urlopen

import easyocr

from app.utils.cache import singleton
from app.utils.logger import logger


@singleton
def get_ocr_reader(langs: list = None) -> easyocr.Reader:
    """获取 EasyOCR 读者单例

    Note: langs 参数在首次调用后会被忽略。

    Args:
        langs: 语言列表，默认 ["ch_sim", "en"]

    Returns:
        EasyOCR 读者实例
    """
    if langs is None:
        langs = ["ch_sim", "en"]  # 简体中文 + 英文
    reader = easyocr.Reader(
        langs,
        gpu=True,          # 使用 GPU
        verbose=False,     # 关闭详细输出
    )
    logger.info(f"EasyOCR reader initialized with langs: {langs}")
    return reader


def _normalize_image_source(image_source: str) -> Path:
    """将图片源标准化为本地文件路径

    支持以下输入类型：
    - 本地文件路径：直接返回
    - URL：下载到临时文件
    - Base64：解码保存到临时文件

    Args:
        image_source: 图片源（文件路径/URL/Base64）

    Returns:
        本地文件路径 Path 对象

    Raises:
        ValueError: 无效的图片源
    """
    # 已经是本地文件路径
    if not image_source.startswith("http") and not image_source.startswith("data:"):
        path = Path(image_source)
        if path.exists():
            return path
        raise ValueError(f"Image file not found: {image_source}")

    # Base64 编码的图片
    if image_source.startswith("data:image"):
        # 提取 Base64 数据
        if "," in image_source:
            base64_data = image_source.split(",", 1)[1]
        else:
            raise ValueError("Invalid Base64 image format")

        # 检测图片格式
        if "png" in image_source:
            suffix = ".png"
        elif "webp" in image_source:
            suffix = ".webp"
        elif "gif" in image_source:
            suffix = ".gif"
        else:
            suffix = ".jpg"

        # 解码并保存到临时文件
        image_data = base64.b64decode(base64_data)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(image_data)
            logger.info(f"Base64 image saved to temp file: {tmp.name}")
            return Path(tmp.name)

    # URL 图片
    if image_source.startswith("http://") or image_source.startswith("https://"):
        try:
            with urlopen(image_source) as response:
                image_data = response.read()

            # 从 URL 或 Content-Type 推断格式
            content_type = response.headers.get("Content-Type", "image/jpeg")
            if "png" in content_type:
                suffix = ".png"
            elif "webp" in content_type:
                suffix = ".webp"
            elif "gif" in content_type:
                suffix = ".gif"
            else:
                suffix = ".jpg"

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(image_data)
                logger.info(f"URL image saved to temp file: {tmp.name}")
                return Path(tmp.name)
        except Exception as e:
            logger.error(f"Failed to download image from URL: {e}")
            raise ValueError(f"Failed to download image: {image_source}")

    raise ValueError(f"Invalid image source: {image_source}")


def ocr_image(image_source: str) -> str:
    """对单张图片进行 OCR 识别

    Args:
        image_source: 图片源（文件路径/URL/Base64）

    Returns:
        识别出的文本内容
    """
    temp_path = None
    try:
        # 标准化图片源为本地文件路径
        image_path = _normalize_image_source(image_source)

        # 判断是否需要清理临时文件
        # Base64 和 URL 会创建临时文件，本地文件路径不需要清理
        is_temp_file = (
            image_source.startswith("data:") or
            image_source.startswith("http://") or
            image_source.startswith("https://")
        )
        if is_temp_file:
            temp_path = image_path

        # 检查文件类型，如果是 webp 先转换为 png
        if image_path.suffix.lower() == ".webp":
            from PIL import Image
            with Image.open(image_path) as img:
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    temp_path = tmp.name
                    img.save(temp_path, "PNG")
            image_path = Path(temp_path)

        reader = get_ocr_reader()

        # 进行 OCR 识别
        result = reader.readtext(str(image_path))

        if not result:
            logger.warning(f"No text detected in image: {image_source}")
            return ""

        # 提取所有识别出的文本（按从上到下的顺序）
        text_lines = []
        for detection in result:
            # result 格式: (bbox, text, confidence)
            text = detection[1]
            text_lines.append(text)

        full_text = "\n".join(text_lines)
        logger.info(f"OCR detected {len(text_lines)} lines from image")
        return full_text

    except Exception as e:
        logger.error(f"OCR failed for {image_source}: {e}")
        raise
    finally:
        # 清理临时文件
        if temp_path and Path(temp_path).exists():
            Path(temp_path).unlink()


def ocr_images(image_sources: list[str]) -> str:
    """对多张图片进行 OCR 识别并返回合并后的文本

    Args:
        image_sources: 图片源列表（文件路径/URL/Base64）

    Returns:
        合并后的 OCR 识别文本
    """
    all_texts = []

    for i, image_source in enumerate(image_sources):
        logger.info(f"OCR processing image {i + 1}/{len(image_sources)}")
        text = ocr_image(image_source)
        if text:
            all_texts.append(f"--- 第 {i + 1} 张图片 ---")
            all_texts.append(text)

    full_text = "\n\n".join(all_texts)
    logger.info(f"OCR completed: {len(image_sources)} images -> {len(all_texts)} sections")

    return full_text


def cleanup_ocr_reader() -> None:
    """清理 OCR 读者（释放内存）"""
    get_ocr_reader.clear_cache()
    logger.info("EasyOCR reader cleaned up")


__all__ = [
    "get_ocr_reader",
    "ocr_image",
    "ocr_images",
    "cleanup_ocr_reader",
]