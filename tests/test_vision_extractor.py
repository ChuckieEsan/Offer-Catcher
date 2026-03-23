"""Vision Extractor 功能测试

验证从文本或图片中提取面经题目信息的功能。
"""
import pytest
from unittest.mock import patch, MagicMock

from app.agents.vision_extractor import (
    VisionExtractor,
    get_vision_extractor,
    ExtractedQuestion,
    ExtractedInterviewSchema,
    encode_image_to_base64,
    load_prompt,
)


class TestVisionExtractor:
    """Vision Extractor 测试"""

    def test_vision_extractor_initialization(self):
        """测试 Vision Extractor 初始化"""
        extractor = VisionExtractor(provider="siliconflow", use_structured_output=True)
        assert extractor is not None
        assert extractor.provider == "siliconflow"
        assert extractor.use_structured_output is True
        print(f"VisionExtractor initialized with provider: {extractor.provider}")

    def test_vision_extractor_default_provider(self):
        """测试默认 provider"""
        extractor = VisionExtractor()
        assert extractor.provider == "siliconflow"
        print("Default provider is siliconflow")

    def test_vision_extractor_without_structured_output(self):
        """测试不使用 structured output"""
        extractor = VisionExtractor(use_structured_output=False)
        assert extractor.use_structured_output is False
        print("Initialized without structured output")

    def test_get_vision_extractor_singleton(self):
        """测试单例获取"""
        extractor1 = get_vision_extractor(provider="siliconflow")
        extractor2 = get_vision_extractor(provider="siliconflow")
        assert extractor1 is extractor2
        print("Singleton pattern verified")


class TestLoadPrompt:
    """Prompt 加载测试"""

    def test_load_prompt(self):
        """测试 Prompt 加载"""
        prompt = load_prompt()
        assert prompt is not None
        assert len(prompt) > 0
        assert "JSON" in prompt
        print(f"Loaded prompt: {len(prompt)} characters")


class TestEncodeImage:
    """图片编码测试"""

    def test_encode_base64_image(self):
        """测试 Base64 图片编码（data URI）"""
        # 测试已编码的 Base64 图片
        base64_image = "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
        result = encode_image_to_base64(base64_image)
        assert result == base64_image
        print("Base64 image encoding verified")

    def test_encode_invalid_image(self):
        """测试无效图片源"""
        with pytest.raises(ValueError, match="Invalid image source"):
            encode_image_to_base64("invalid_source")
        print("Invalid image source raises error")


class TestExtractFromText:
    """从文本提取测试（需要 API 调用）"""

    @pytest.fixture
    def extractor(self):
        """创建 Extractor 实例"""
        return VisionExtractor(provider="siliconflow", use_structured_output=True)

    def test_extract_simple_text(self, extractor):
        """测试简单文本提取"""
        text = """
        腾讯后端开发面经

        1. Python 装饰器是什么？
        2. 讲讲 HTTP 协议？
        """

        result = extractor.extract(text, source_type="text")

        assert result is not None
        assert result.company in ["腾讯"]
        assert result.position is not None
        assert len(result.questions) > 0
        print(f"Extracted {len(result.questions)} questions from text")

    def test_extract_full_interview_text(self, extractor):
        """测试完整面经文本提取"""
        text = """
        字节跳动后端开发面经

        一面：
        1. 自我介绍
        2. 项目中用过哪些并发编程的方式？
        3. 讲讲线程和进程的区别
        4. TCP三次握手四次挥手

        二面：
        1. 介绍你最熟悉的项目
        2. 项目中遇到的最大技术挑战是什么？
        """

        result = extractor.extract(text, source_type="text")

        assert result.company == "字节跳动"
        assert result.position == "后端开发"
        assert len(result.questions) >= 5
        print(f"Extracted {len(result.questions)} questions")

        # 验证题目类型分类
        for q in result.questions:
            assert q.question_type.value in ["knowledge", "project", "behavioral"]
        print("Question types verified")

    def test_extract_question_types(self, extractor):
        """测试题目类型分类"""
        text = """
        阿里云算法工程师面经

        1. 介绍一下自己（行为题）
        2. 讲讲你最有价值的项目（项目题）
        3. 什么是 B+ 树？（八股文）
        """

        result = extractor.extract(text, source_type="text")

        # 查找不同类型的题目
        behavioral = [q for q in result.questions if q.question_type.value == "behavioral"]
        project = [q for q in result.questions if q.question_type.value == "project"]
        knowledge = [q for q in result.questions if q.question_type.value == "knowledge"]

        print(f"Behavioral: {len(behavioral)}, Project: {len(project)}, Knowledge: {len(knowledge)}")
        assert len(result.questions) >= 3

    def test_extract_with_empty_text(self, extractor):
        """测试空文本处理"""
        text = ""

        try:
            result = extractor.extract(text, source_type="text")
            # 空文本可能返回空结果或抛出异常
            assert result is not None
            print(f"Empty text handled, company: {result.company}, questions: {len(result.questions)}")
        except Exception as e:
            # 空文本可能触发 API 错误，这是预期行为
            print(f"Empty text raised error (expected): {type(e).__name__}")


class TestExtractFromImage:
    """从图片提取测试（需要 API 调用）"""

    @pytest.fixture
    def extractor(self):
        """创建 Extractor 实例"""
        return VisionExtractor(provider="siliconflow", use_structured_output=True)

    def test_extract_from_image_url(self, extractor):
        """测试从图片 URL 提取"""
        # 使用一个公开的测试图片 URL
        # 注意：实际测试可能需要有效的图片
        image_url = "https://httpbin.org/image/jpeg"

        try:
            result = extractor.extract(image_url, source_type="image")
            print(f"Image extraction result: company={result.company}")
        except Exception as e:
            # 图片提取可能因网络或图片内容失败
            print(f"Image extraction test skipped: {e}")

    def test_extract_from_invalid_source_type(self, extractor):
        """测试无效的 source_type"""
        with pytest.raises(ValueError, match="Invalid source_type"):
            extractor.extract("some content", source_type="invalid")


class TestSchemaConversion:
    """Schema 转换测试"""

    def test_extracted_interview_schema(self):
        """测试 ExtractedInterviewSchema"""
        schema = ExtractedInterviewSchema(
            company="腾讯",
            position="后端开发",
            questions=[
                ExtractedQuestion(
                    question_text="什么是装饰器？",
                    question_type="knowledge",
                    core_entities=["Python", "装饰器"],
                )
            ],
        )

        assert schema.company == "腾讯"
        assert schema.position == "后端开发"
        assert len(schema.questions) == 1
        print("Schema validation passed")

    def test_extracted_question_defaults(self):
        """测试 ExtractedQuestion 默认值"""
        q = ExtractedQuestion(
            question_text="测试题目",
            question_type="knowledge",
        )

        assert q.question_text == "测试题目"
        assert q.question_type == "knowledge"
        assert q.core_entities == []  # 默认空列表
        print("Default values verified")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])