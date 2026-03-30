"""Vision Extractor 模块

从文本或图片中提取面经题目信息，输出 ExtractedInterview 结构化数据。

支持输入类型：
- text: 直接分析文本内容
- image: 分析图片（支持 Base64、文件路径、URL）
"""

import json
import re
from typing import Any, Optional

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.config.settings import create_llm
from app.models.schemas import ExtractedInterview, QuestionItem, QuestionType, MasteryLevel
from app.utils.hasher import generate_question_id
from app.utils.image import build_vision_message_content
from app.utils.logger import logger


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

    从文本或图片中提取面经题目信息。
    使用 LangChain 的 with_structured_output 自动解析 JSON。
    """

    _prompt_filename = "vision_extractor.md"
    _structured_output_schema = ExtractedInterviewSchema

    def __init__(self, provider: str = "dashscope", use_structured_output: bool = True):
        """初始化 Vision Extractor

        Args:
            provider: LLM Provider 名称
            use_structured_output: 是否使用 structured output，默认 True
                                 如果模型不支持会自动回退
        """
        super().__init__(provider)
        self.use_structured_output = use_structured_output
        # Vision 需要专门的 vision model，不使用父类的 chat model
        self._vision_llm = None
        self._vision_structured_llm = None

    @property
    def llm(self):
        """获取 Vision LLM"""
        if self._vision_llm is None:
            extra_kwargs = {}
            if self.provider == "dashscope":
                extra_kwargs["extra_body"] = {"enable_thinking": False}

            self._vision_llm = create_llm(self.provider, "vision", **extra_kwargs)
        return self._vision_llm

    @property
    def structured_llm(self):
        """获取支持 structured output 的 Vision LLM"""
        if self._vision_structured_llm is None:
            if not self.use_structured_output:
                return None

            try:
                self._vision_structured_llm = self.llm.with_structured_output(
                    ExtractedInterviewSchema,
                    method="function_calling"
                )
            except Exception as e:
                from app.utils.logger import logger
                logger.warning(f"Model does not support structured output: {e}")
                self._vision_structured_llm = None

        return self._vision_structured_llm

    def _build_message(self, source: str | list[str], source_type: str) -> HumanMessage:
        """构建消息

        Args:
            source: 输入内容（文本/单个图片路径/多个图片路径列表/URL/Base64）
            source_type: 输入类型 "text" | "image"
        """
        if source_type == "text":
            content = [
                {"type": "text", "text": self.prompt_template + "\n\n" + "以下是需要分析的内容：\n" + source}
            ]
        elif source_type == "image":
            # 支持单个图片路径或多个图片路径列表
            content = build_vision_message_content(self.prompt_template, source)
        else:
            raise ValueError(f"Invalid source_type: {source_type}")

        return HumanMessage(content=content)

    def _parse_json_response(self, response: str) -> ExtractedInterviewSchema:
        """手动解析 JSON 响应"""
        import app.utils.logger as logger_module

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
            logger_module.logger.error(f"Failed to parse JSON: {e}")
            logger_module.logger.error(f"Response: {response}")
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

    def _extract_with_structured_output(self, message: HumanMessage) -> ExtractedInterview:
        """使用 structured output 提取"""
        result = self.structured_llm.invoke([message])
        return self._convert_to_extracted_interview(result)

    def _extract_with_parsing(self, message: HumanMessage) -> ExtractedInterview:
        """使用手动解析提取"""
        response = self.llm.invoke([message])
        schema = self._parse_json_response(response.content)
        return self._convert_to_extracted_interview(schema)

    def extract(self, source: str | list[str], source_type: str = "text", use_ocr: bool = False) -> ExtractedInterview:
        """从文本或图片提取面经数据

        Args:
            source: 输入内容（文本/单个图片路径/多个图片路径列表/URL/Base64）
            source_type: 输入类型 "text" | "image"
            use_ocr: 是否使用 OCR 预处理（仅对 image 有效），默认 False

        Returns:
            ExtractedInterview 结构化数据
        """

        # 如果是图片且需要使用 OCR
        if source_type == "image" and use_ocr:
            from app.utils.ocr import ocr_images

            # 将 source 规范化为列表
            image_sources = [source] if isinstance(source, str) else source

            # OCR 识别文字
            ocr_text = ocr_images(image_sources)
            logger.info(f"OCR completed, extracted text length: {len(ocr_text)}")

            if not ocr_text.strip():
                raise ValueError("OCR 未能识别出任何文字")

            # 使用 OCR 结果作为文本输入
            source_type = "text"
            source = ocr_text

        # 记录日志
        if isinstance(source, list):
            logger.info(f"Extracting from {source_type}: {len(source)} images")
        else:
            logger.info(f"Extracting from {source_type}: {source[:50]}...")

        # 构建消息
        message = self._build_message(source, source_type)

        # 选择提取方式
        if self.use_structured_output and self.structured_llm:
            try:
                return self._extract_with_structured_output(message)
            except Exception as e:
                logger.warning(f"Structured output failed, falling back to manual parsing: {e}")
                return self._extract_with_parsing(message)
        else:
            return self._extract_with_parsing(message)


# 全局单例
_vision_extractor: Optional[VisionExtractor] = None


def get_vision_extractor(provider: str = "siliconflow") -> VisionExtractor:
    """获取 Vision Extractor 单例"""
    global _vision_extractor
    if _vision_extractor is None:
        _vision_extractor = VisionExtractor(provider=provider)
    return _vision_extractor