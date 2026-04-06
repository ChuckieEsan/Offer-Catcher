"""OCR 工具模块

使用 EasyOCR 进行文字识别。
"""

import tempfile
from pathlib import Path
from typing import Optional

import easyocr
from langchain_core.messages import HumanMessage

from app.utils.logger import logger

# 全局 OCR 引擎单例
_ocr_reader: Optional[easyocr.Reader] = None


def get_ocr_reader(langs: list = None) -> easyocr.Reader:
    """获取 EasyOCR 读者单例

    Args:
        langs: 语言列表，默认 ["ch_sim", "en"]

    Returns:
        EasyOCR 读者实例
    """
    global _ocr_reader
    if _ocr_reader is None:
        if langs is None:
            langs = ["ch_sim", "en"]  # 简体中文 + 英文
        _ocr_reader = easyocr.Reader(
            langs,
            gpu=True,          # 使用 GPU
            verbose=False,    # 关闭详细输出
        )
        logger.info(f"EasyOCR reader initialized with langs: {langs}")
    return _ocr_reader


def ocr_image(image_path: str) -> str:
    """对单张图片进行 OCR 识别

    Args:
        image_path: 图片路径

    Returns:
        识别出的文本内容
    """
    # 检查文件类型，如果是 webp 先转换为 png
    image_path = Path(image_path)
    temp_path = None

    if image_path.suffix.lower() == ".webp":
        from PIL import Image
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                temp_path = tmp.name
                img.save(temp_path, "PNG")
        image_path = temp_path

    reader = get_ocr_reader()

    try:
        # 进行 OCR 识别
        result = reader.readtext(str(image_path))

        if not result:
            logger.warning(f"No text detected in image: {image_path}")
            return ""

        # 提取所有识别出的文本（按从上到下的顺序）
        text_lines = []
        for detection in result:
            # result 格式: (bbox, text, confidence)
            text = detection[1]
            text_lines.append(text)

        full_text = "\n".join(text_lines)
        logger.info(f"OCR detected {len(text_lines)} lines from {image_path}")
        return full_text

    except Exception as e:
        logger.error(f"OCR failed for {image_path}: {e}")
        raise
    finally:
        # 清理临时文件
        if temp_path and Path(temp_path).exists():
            Path(temp_path).unlink()


def ocr_images(
    image_paths: list[str],
    prompt: str = "经文本解析后，用户上传了如下图片内容：",
) -> HumanMessage:
    """对多张图片进行 OCR 识别并返回 HumanMessage

    符合 LangChain 最佳实践，直接返回可用于 Agent 的消息对象。

    Args:
        image_paths: 图片路径列表
        prompt: 提示词，默认分析面试题目

    Returns:
        HumanMessage 对象，可直接传给 Agent
    """
    all_texts = []

    for i, image_path in enumerate(image_paths):
        logger.info(f"OCR processing image {i + 1}/{len(image_paths)}: {image_path}")
        text = ocr_image(image_path)
        if text:
            all_texts.append(f"--- 第 {i + 1} 张图片 ---")
            all_texts.append(text)

    full_text = "\n\n".join(all_texts)
    logger.info(f"OCR completed: {len(image_paths)} images -> {len(all_texts)} sections")

    # 构建消息内容
    content = [
        {"type": "text", "text": prompt},
        {"type": "text", "text": f"--- OCR 识别结果 ---\n{full_text}"},
    ]

    return HumanMessage(content=content)


def cleanup_ocr_reader() -> None:
    """清理 OCR 读者（释放内存）"""
    global _ocr_reader
    if _ocr_reader is not None:
        _ocr_reader = None
        logger.info("EasyOCR reader cleaned up")


__all__ = [
    "get_ocr_reader",
    "ocr_image",
    "ocr_images",
    "cleanup_ocr_reader",
]