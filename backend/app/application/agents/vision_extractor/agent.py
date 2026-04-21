"""Vision Extractor Agent - 面经提取 Agent

从文本或图片中提取面经题目信息。
图片输入必须经过 OCR 预处理，统一走文本 LLM 路径。
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from app.application.agents.shared.base_agent import BaseAgent, LLMType
from app.application.agents.vision_extractor.prompts import PROMPTS_DIR
from app.domain.question.utils import generate_question_id
from app.infrastructure.adapters.ocr_adapter import OCRAdapter, get_ocr_adapter
from app.infrastructure.common.logger import logger
from app.domain.question.aggregates import ExtractedInterview, QuestionItem
from app.domain.shared.enums import MasteryLevel, QuestionType


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

    使用依赖注入：
    - llm: ChatOpenAI 实例
    - ocr_adapter: OCRAdapter 实例
    """

    _prompt_filename = "vision_extractor.md"
    _structured_output_schema = ExtractedInterviewSchema

    def __init__(
        self,
        llm: LLMType,
        ocr_adapter: OCRAdapter,
        prompts_dir: Any = PROMPTS_DIR,
        use_structured_output: bool = True,
    ) -> None:
        """初始化 Vision Extractor

        Args:
            llm: LLM 实例（依赖注入）
            ocr_adapter: OCR Adapter 实例（依赖注入）
            prompts_dir: Prompt 目录路径
            use_structured_output: 是否使用 structured output
        """
        super().__init__(llm, prompts_dir)
        self._ocr_adapter = ocr_adapter
        self.use_structured_output = use_structured_output

    def _parse_json_response(self, response: str) -> ExtractedInterviewSchema:
        """手动解析 JSON 响应"""
        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")

            json_str = response[json_start:json_end]
            data = json.loads(json_str)

            if "questions" in data and isinstance(data["questions"], str):
                try:
                    data["questions"] = json.loads(data["questions"])
                except json.JSONDecodeError:
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
            try:
                question_type = QuestionType(q.question_type)
            except ValueError:
                question_type = QuestionType.KNOWLEDGE

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
        content = response.content
        if isinstance(content, str):
            response_str = content
        elif isinstance(content, list):
            # 处理多部分内容
            text_parts = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict) and "text" in part:
                    text_parts.append(part["text"])
            response_str = " ".join(text_parts)
        else:
            response_str = str(content)
        schema = self._parse_json_response(response_str)
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
        if source_type == "image":
            if not use_ocr:
                raise NotImplementedError(
                    "图片提取必须使用 OCR 预处理，请设置 use_ocr=True"
                )

            image_sources = [source] if isinstance(source, str) else source

            logger.info(f"OCR processing {len(image_sources)} images...")

            ocr_text = self._ocr_adapter.recognize_batch(image_sources)

            logger.info(f"OCR completed, extracted text length: {len(ocr_text)}")

            if not ocr_text.strip():
                raise ValueError("OCR 未能识别出任何文字")

            # OCR 处理后，source 变为文本
            text_source: str = ocr_text
        else:
            text_source = source if isinstance(source, str) else source[0]

        logger.info(f"Extracting from text: {text_source[:100]}...")

        if self.use_structured_output and self.structured_llm:
            try:
                return self._extract_with_structured_output(text_source)
            except Exception as e:
                logger.warning(f"Structured output failed, falling back to manual parsing: {e}")
                return self._extract_with_parsing(text_source)
        else:
            return self._extract_with_parsing(text_source)


_vision_extractor: Optional[VisionExtractor] = None


def get_vision_extractor() -> VisionExtractor:
    """获取 Vision Extractor 单例

    Note: 使用 factory.get_vision_extractor() 获取实例，
    此函数作为备用入口。

    Returns:
        VisionExtractor 实例
    """
    global _vision_extractor
    if _vision_extractor is None:
        from app.infrastructure.adapters.llm_adapter import get_llm
        from app.infrastructure.adapters.ocr_adapter import get_ocr_adapter

        llm = get_llm("deepseek", "chat")
        ocr_adapter = get_ocr_adapter()
        _vision_extractor = VisionExtractor(llm, ocr_adapter)
    return _vision_extractor


__all__ = [
    "VisionExtractor",
    "get_vision_extractor",
    "ExtractedQuestion",
    "ExtractedInterviewSchema",
]