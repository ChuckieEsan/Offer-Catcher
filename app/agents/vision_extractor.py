"""Vision Extractor 模块

从文本或图片中提取面经题目信息，输出 ExtractedInterview 结构化数据。

支持输入类型：
- text: 直接分析文本内容
- image: 分析图片（支持 Base64、文件路径、URL）
"""

import base64
import json
from pathlib import Path
from typing import Any, Optional
from urllib.request import urlopen

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.config.settings import create_llm, get_settings
from app.models.schemas import ExtractedInterview, QuestionItem, QuestionType, MasteryLevel
from app.utils.logger import logger
from app.utils.hasher import generate_question_id


# Prompt 模板路径
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "vision_extractor.md"


# 用于 with_structured_output 的 Pydantic 模型
class ExtractedQuestion(BaseModel):
    """提取的单个题目"""
    question_text: str = Field(description="题目文本内容")
    question_type: str = Field(description="题目类型: knowledge/project/behavioral")
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


def load_prompt() -> str:
    """加载 Prompt 模板"""
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    return ""


def encode_image_to_base64(image_source: str) -> str:
    """将图片转换为 Base64 编码"""
    if image_source.startswith("data:image"):
        return image_source

    if image_source.startswith("http://") or image_source.startswith("https://"):
        with urlopen(image_source) as response:
            image_data = response.read()
            return base64.b64encode(image_data).decode("utf-8")

    image_path = Path(image_source)
    if image_path.exists():
        with open(image_path, "rb") as f:
            image_data = f.read()
            return base64.b64encode(image_data).decode("utf-8")

    raise ValueError(f"Invalid image source: {image_source}")


class VisionExtractor:
    """Vision Extractor

    从文本或图片中提取面经题目信息。
    使用 LangChain 的 with_structured_output 自动解析 JSON。
    """

    def __init__(self, provider: str = "siliconflow", use_structured_output: bool = True):
        """初始化 Vision Extractor

        Args:
            provider: LLM Provider 名称，默认 siliconflow
            use_structured_output: 是否使用 structured output，默认 True
                                 如果模型不支持会自动回退
        """
        self.provider = provider
        self.use_structured_output = use_structured_output
        self._structured_llm = None
        self._base_llm = None
        self.prompt = load_prompt()
        logger.info(f"VisionExtractor initialized with provider: {provider}")

    @property
    def base_llm(self):
        """获取基础 LLM"""
        if self._base_llm is None:
            self._base_llm = create_llm(self.provider, "vision")
        return self._base_llm

    @property
    def structured_llm(self):
        """获取支持 structured output 的 LLM"""
        if self._structured_llm is None:
            try:
                self._structured_llm = self.base_llm.with_structured_output(ExtractedInterviewSchema, method="function_calling")
            except Exception as e:
                logger.warning(f"Model does not support structured output: {e}")
                self._structured_llm = None
        return self._structured_llm

    def _build_message(self, source: str, source_type: str) -> HumanMessage:
        """构建消息"""
        if source_type == "text":
            content = [
                {"type": "text", "text": self.prompt + "\n\n" + "以下是需要分析的内容：\n" + source}
            ]
        elif source_type == "image":
            image_base64 = encode_image_to_base64(source)
            content = [
                {"type": "text", "text": self.prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                }
            ]
        else:
            raise ValueError(f"Invalid source_type: {source_type}")

        return HumanMessage(content=content)

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
            # 转换 question_type
            if q.question_type == "project":
                question_type = QuestionType.PROJECT
            elif q.question_type == "behavioral":
                question_type = QuestionType.BEHAVIORAL
            else:
                question_type = QuestionType.KNOWLEDGE

            # 生成 question_id
            question_id = generate_question_id(schema.company, q.question_text)

            question = QuestionItem(
                question_id=question_id,
                question_text=q.question_text,
                question_type=question_type,
                requires_async_answer=(question_type == QuestionType.KNOWLEDGE),
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
        response = self.base_llm.invoke([message])
        schema = self._parse_json_response(response.content)
        return self._convert_to_extracted_interview(schema)

    def extract(self, source: str, source_type: str = "text") -> ExtractedInterview:
        """从文本或图片提取面经数据

        Args:
            source: 输入内容（文本/图片路径/URL/Base64）
            source_type: 输入类型 "text" | "image"

        Returns:
            ExtractedInterview 结构化数据
        """
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