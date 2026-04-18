"""Vision Extractor 模块

从文本或 OCR 识别后的文字中提取面经题目信息，输出 ExtractedInterview 结构化数据。

支持输入类型：
- text: 直接分析文本内容
- image: OCR 识别图片文字后分析（默认必须使用 OCR）
"""

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.models import ExtractedInterview, QuestionItem, QuestionType, MasteryLevel
from app.domain.question.utils import generate_question_id
from app.infrastructure.common.logger import logger
from app.infrastructure.adapters.ocr_adapter import get_ocr_adapter


# 用于 with_structured_output 的 Pydantic 模型
class ExtractedQuestion(BaseModel):
    """提取的单个题目"""
    question_text: str = Field(description="题目文本内容")
    question_type: str = Field(description="题目类型: knowledge/project/behavioral/scenario")
    core_entities: list[str] = Field(
        default_factory=list,
        description="考察的知识点实体列表"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="题目元数据，如面试轮次等"
    )


class ExtractedInterviewSchema(BaseModel):
    """Vision Extractor 输出的结构化数据"""
    company: str = Field(description="公司名称")
    position: str = Field(description="岗位名称")
    questions: list[ExtractedQuestion] = Field(
        default_factory=list,
        description="题目列表"
    )


class VisionExtractor(BaseAgent[ExtractedInterviewSchema]):
    """Vision Extractor

    从文本或 OCR 识别后的文字中提取面经题目信息。
    图片输入必须经过 OCR 预处理，统一走文本 LLM 路径。
    """

    _prompt_filename = "vision_extractor.md"
    _structured_output_schema = ExtractedInterviewSchema

    def __init__(self, provider: str = "deepseek", use_structured_output: bool = True):
        """初始化 Vision Extractor

        Args:
            provider: LLM Provider 名称，默认 deepseek
            use_structured_output: 是否使用 structured output，默认 True
        """
        super().__init__(provider)
        self.use_structured_output = use_structured_output
        self._ocr_adapter = get_ocr_adapter()

    def _parse_json_response(self, response: str) -> ExtractedInterviewSchema:
        """手动解析 JSON 响应"""
        try:
            # 查找 JSON 块
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")

            json_str = response[json_start:json_end]
            data = json.loads(json_str)

            # 处理 questions 字段可能是字符串的情况
            if "questions" in data and isinstance(data["questions"], str):
                # LLM 可能返回了字符串形式的列表，尝试解析
                try:
                    data["questions"] = json.loads(data["questions"])
                except json.JSONDecodeError:
                    # 如果还是失败，尝试提取数组
                    match = re.search(r'\[.*\]', data["questions"])
                    if match:
                        data["questions"] = json.loads(match.group())

            return ExtractedInterviewSchema(**data)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.error(f"Response: {response}")
            raise ValueError(f"Invalid JSON response: {e}")

    def _convert_to_extracted_interview(
        self,
        schema: ExtractedInterviewSchema,
    ) -> ExtractedInterview:
        """将 schema 转换为 ExtractedInterview"""
        questions = []

        for q in schema.questions:
            # 转换 question_type（使用 Enum 直接转换，更简洁）
            try:
                question_type = QuestionType(q.question_type)
            except ValueError:
                question_type = QuestionType.KNOWLEDGE

            # 生成 question_id
            question_id = generate_question_id(schema.company, q.question_text)

            question = QuestionItem(
                question_id=question_id,
                question_text=q.question_text,
                question_type=question_type,
                requires_async_answer=(question_type in (QuestionType.KNOWLEDGE, QuestionType.SCENARIO, QuestionType.ALGORITHM)),
                core_entities=q.core_entities,
                mastery_level=MasteryLevel.LEVEL_0,
                company=schema.company,
                position=schema.position,
                metadata=q.metadata,
            )
            questions.append(question)

        return ExtractedInterview(
            company=schema.company,
            position=schema.position,
            questions=questions,
        )

    def _extract_with_structured_output(self, text: str) -> ExtractedInterview:
        """使用 structured output 提取"""
        prompt = self._build_prompt(text=text)
        result = self.structured_llm.invoke(prompt)
        return self._convert_to_extracted_interview(result)

    def _extract_with_parsing(self, text: str) -> ExtractedInterview:
        """使用手动解析提取"""
        prompt = self._build_prompt(text=text)
        response = self.llm.invoke(prompt)
        schema = self._parse_json_response(response.content)
        return self._convert_to_extracted_interview(schema)

    def extract(
        self,
        source: str | list[str],
        source_type: str = "text",
        use_ocr: bool = True,
    ) -> ExtractedInterview:
        """从文本或图片提取面经数据

        Args:
            source: 输入内容（文本/单个图片路径/多个图片路径列表）
            source_type: 输入类型 "text" | "image"
            use_ocr: 是否使用 OCR 预处理（仅对 image 有效），默认 True

        Returns:
            ExtractedInterview 结构化数据

        Raises:
            NotImplementedError: 当 source_type="image" 且 use_ocr=False 时
        """
        # 图片输入必须使用 OCR
        if source_type == "image":
            if not use_ocr:
                raise NotImplementedError(
                    "图片提取必须使用 OCR 预处理，请设置 use_ocr=True"
                )

            # 将 source 规范化为列表
            image_sources = [source] if isinstance(source, str) else source

            logger.info(f"OCR processing {len(image_sources)} images...")

            # 使用 OCRAdapter 识别文字
            ocr_text = self._ocr_adapter.recognize_batch(image_sources)

            logger.info(f"OCR completed, extracted text length: {len(ocr_text)}")

            if not ocr_text.strip():
                raise ValueError("OCR 未能识别出任何文字")

            # 使用 OCR 结果作为文本输入
            source = ocr_text

        # 记录日志
        logger.info(f"Extracting from text: {source[:100]}...")

        # 选择提取方式
        if self.use_structured_output and self.structured_llm:
            try:
                return self._extract_with_structured_output(source)
            except Exception as e:
                logger.warning(f"Structured output failed, falling back to manual parsing: {e}")
                return self._extract_with_parsing(source)
        else:
            return self._extract_with_parsing(source)


# 单例获取函数
_vision_extractor: "VisionExtractor | None" = None


def get_vision_extractor(provider: str = "deepseek") -> VisionExtractor:
    """获取 Vision Extractor 单例

    Args:
        provider: LLM Provider 名称

    Returns:
        VisionExtractor 实例
    """
    global _vision_extractor
    if _vision_extractor is None:
        _vision_extractor = VisionExtractor(provider=provider)
    return _vision_extractor