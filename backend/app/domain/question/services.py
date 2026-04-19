"""Question Domain Services - 接口定义

定义 Question Domain 的领域服务接口（Protocol）。
遵循依赖倒置原则：Domain 层只定义接口，Application 层实现。

接口列表：
- AnswerGenerator: 答案生成器接口
- InterviewExtractor: 面经提取器接口
"""

from typing import Protocol

from app.models import ExtractedInterview, QuestionItem


class AnswerGenerator(Protocol):
    """答案生成器接口

    由 AnswerSpecialistAgent 实现，在 Application 层。
    """

    def generate_answer(self, question: QuestionItem) -> str:
        """生成题目答案

        Args:
            question: 题目对象

        Returns:
            生成的答案文本
        """
        ...


class InterviewExtractor(Protocol):
    """面经提取器接口

    由 VisionExtractor 实现，在 Application 层。
    """

    def extract(
        self,
        source: str | list[str],
        source_type: str = "text",
        use_ocr: bool = True,
    ) -> ExtractedInterview:
        """从文本或图片提取面经数据

        Args:
            source: 输入内容（文本/图片路径）
            source_type: 输入类型 "text" | "image"
            use_ocr: 是否使用 OCR 预处理

        Returns:
            ExtractedInterview 结构化数据
        """
        ...


__all__ = [
    "AnswerGenerator",
    "InterviewExtractor",
]