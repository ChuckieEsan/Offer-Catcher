"""OCR 适配器

封装 EasyOCR，提供图片文字识别能力。
作为基础设施层适配器，为应用层和领域层提供 OCR 服务。
"""

import base64
import tempfile
from pathlib import Path
from urllib.request import urlopen
from typing import Optional

import easyocr

from app.infrastructure.common.logger import logger


class OCRAdapter:
    """OCR 适配器

    封装 EasyOCR，支持多种图片源的文字识别：
    - 本地文件路径
    - URL 图片
    - Base64 编码图片

    设计原则：
    - 复用 EasyOCR 组件
    - 支持依赖注入（便于测试）
    - 自动清理临时文件
    """

    def __init__(
        self,
        langs: Optional[list[str]] = None,
        use_gpu: bool = True,
    ) -> None:
        """初始化 OCR 适配器

        Args:
            langs: 语言列表，默认 ["ch_sim", "en"]
            use_gpu: 是否使用 GPU
        """
        self._langs = langs or ["ch_sim", "en"]
        self._use_gpu = use_gpu

        self._reader = easyocr.Reader(
            self._langs,
            gpu=self._use_gpu,
            verbose=False,
        )

        logger.info(f"OCRAdapter initialized with langs: {self._langs}, gpu={use_gpu}")

    def recognize(
        self,
        image_source: str,
    ) -> str:
        """识别单张图片中的文字

        Args:
            image_source: 图片源（文件路径/URL/Base64）

        Returns:
            识别出的文本内容
        """
        temp_path = None
        try:
            image_path = self._normalize_image_source(image_source)

            is_temp_file = (
                image_source.startswith("data:") or
                image_source.startswith("http://") or
                image_source.startswith("https://")
            )
            if is_temp_file:
                temp_path = image_path

            # webp 格式转换
            if image_path.suffix.lower() == ".webp":
                from PIL import Image
                with Image.open(image_path) as img:
                    if img.mode in ("RGBA", "LA", "P"):
                        img = img.convert("RGB")
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                        temp_path = tmp.name
                        img.save(temp_path, "PNG")
                image_path = Path(temp_path)

            result = self._reader.readtext(str(image_path))

            if not result:
                logger.warning(f"No text detected in image: {image_source}")
                return ""

            text_lines = [detection[1] for detection in result]
            full_text = "\n".join(text_lines)

            logger.info(f"OCR detected {len(text_lines)} lines from image")
            return full_text

        except Exception as e:
            logger.error(f"OCR failed for {image_source}: {e}")
            raise
        finally:
            if temp_path and Path(temp_path).exists():
                Path(temp_path).unlink()

    def recognize_batch(
        self,
        image_sources: list[str],
    ) -> str:
        """识别多张图片并返回合并文本

        Args:
            image_sources: 图片源列表

        Returns:
            合并后的 OCR 识别文本
        """
        all_texts = []

        for i, image_source in enumerate(image_sources):
            logger.info(f"OCR processing image {i + 1}/{len(image_sources)}")
            text = self.recognize(image_source)
            if text:
                all_texts.append(f"--- 第 {i + 1} 张图片 ---")
                all_texts.append(text)

        full_text = "\n\n".join(all_texts)
        logger.info(f"OCR completed: {len(image_sources)} images -> {len(all_texts)} sections")

        return full_text

    def _normalize_image_source(
        self,
        image_source: str,
    ) -> Path:
        """将图片源标准化为本地文件路径

        Args:
            image_source: 图片源（文件路径/URL/Base64）

        Returns:
            本地文件路径 Path 对象

        Raises:
            ValueError: 无效的图片源
        """
        # 本地文件路径
        if not image_source.startswith("http") and not image_source.startswith("data:"):
            path = Path(image_source)
            if path.exists():
                return path
            raise ValueError(f"Image file not found: {image_source}")

        # Base64 编码
        if image_source.startswith("data:image"):
            if "," in image_source:
                base64_data = image_source.split(",", 1)[1]
            else:
                raise ValueError("Invalid Base64 image format")

            if "png" in image_source:
                suffix = ".png"
            elif "webp" in image_source:
                suffix = ".webp"
            elif "gif" in image_source:
                suffix = ".gif"
            else:
                suffix = ".jpg"

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


# 单例获取函数
_ocr_adapter: Optional[OCRAdapter] = None


def get_ocr_adapter() -> OCRAdapter:
    """获取 OCR 适配器单例

    Returns:
        OCRAdapter 实例
    """
    global _ocr_adapter
    if _ocr_adapter is None:
        _ocr_adapter = OCRAdapter()
    return _ocr_adapter


__all__ = [
    "OCRAdapter",
    "get_ocr_adapter",
]