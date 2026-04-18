"""数据模型测试

验证 QuestionItem 和 ExtractedInterview 数据模型的修改。
"""

import pytest

from app.models import QuestionItem, ExtractedInterview, QuestionType, MasteryLevel
from app.domain.question.utils import generate_question_id


class TestQuestionItem:
    """QuestionItem 模型测试"""

    def test_question_item_with_company_position(self):
        """测试 QuestionItem 包含 company 和 position 字段"""
        q = QuestionItem(
            question_id='test123',
            question_text='什么是 RAG？',
            question_type=QuestionType.KNOWLEDGE,
            company='字节跳动',
            position='Agent开发',
        )

        assert q.company == '字节跳动'
        assert q.position == 'Agent开发'
        print("QuestionItem with company and position: PASSED")

    def test_question_item_all_fields(self):
        """测试 QuestionItem 所有字段"""
        q = QuestionItem(
            question_id='test456',
            question_text='Python 装饰器是什么？',
            question_type=QuestionType.KNOWLEDGE,
            requires_async_answer=True,
            core_entities=['Python', '装饰器'],
            mastery_level=MasteryLevel.LEVEL_1,
            company='腾讯',
            position='后端开发',
        )

        assert q.question_id == 'test456'
        assert q.question_text == 'Python 装饰器是什么？'
        assert q.question_type == QuestionType.KNOWLEDGE
        assert q.requires_async_answer is True
        assert q.core_entities == ['Python', '装饰器']
        assert q.mastery_level == MasteryLevel.LEVEL_1
        assert q.company == '腾讯'
        assert q.position == '后端开发'
        print("QuestionItem all fields: PASSED")

    def test_question_item_default_values(self):
        """测试 QuestionItem 默认值"""
        q = QuestionItem(
            question_id='test789',
            question_text='测试问题',
            question_type=QuestionType.PROJECT,
            company='阿里',
            position='算法工程师',
        )

        assert q.requires_async_answer is False
        assert q.core_entities == []
        assert q.mastery_level == MasteryLevel.LEVEL_0
        print("QuestionItem default values: PASSED")

    def test_question_id_generation(self):
        """测试 question_id 基于 company 和 question_text 生成"""
        question_text = '什么是 RAG？'
        company = '字节跳动'

        question_id = generate_question_id(company, question_text)

        q = QuestionItem(
            question_id=question_id,
            question_text=question_text,
            question_type=QuestionType.KNOWLEDGE,
            company=company,
            position='Agent开发',
        )

        assert q.question_id == question_id
        print(f"Generated question_id: {question_id}")


class TestExtractedInterview:
    """ExtractedInterview 模型测试"""

    def test_extracted_interview_with_questions(self):
        """测试 ExtractedInterview 包含 questions"""
        interview = ExtractedInterview(
            company='腾讯',
            position='后端开发',
            questions=[
                QuestionItem(
                    question_id='q1',
                    question_text='Python 装饰器是什么？',
                    question_type=QuestionType.KNOWLEDGE,
                    company='腾讯',
                    position='后端开发',
                ),
                QuestionItem(
                    question_id='q2',
                    question_text='讲讲你的项目？',
                    question_type=QuestionType.PROJECT,
                    company='腾讯',
                    position='后端开发',
                ),
            ]
        )

        assert interview.company == '腾讯'
        assert interview.position == '后端开发'
        assert len(interview.questions) == 2
        assert interview.questions[0].company == '腾讯'
        assert interview.questions[1].company == '腾讯'
        print("ExtractedInterview with questions: PASSED")

    def test_extracted_interview_empty_questions(self):
        """测试 ExtractedInterview 空题目列表"""
        interview = ExtractedInterview(
            company='美团',
            position='算法工程师',
            questions=[]
        )

        assert interview.company == '美团'
        assert interview.questions == []
        print("ExtractedInterview empty questions: PASSED")


class TestModelIntegration:
    """模型集成测试"""

    def test_question_item_from_interview(self):
        """测试从 ExtractedInterview 创建 QuestionItem"""
        # 模拟 Vision Extractor 输出的数据
        company = '字节跳动'
        position = 'Agent应用开发'
        question_text = 'qlora怎么优化显存？'

        question_id = generate_question_id(company, question_text)

        # 创建 QuestionItem（包含 company 和 position）
        q = QuestionItem(
            question_id=question_id,
            question_text=question_text,
            question_type=QuestionType.KNOWLEDGE,
            requires_async_answer=True,
            company=company,
            position=position,
        )

        # 创建 ExtractedInterview
        interview = ExtractedInterview(
            company=company,
            position=position,
            questions=[q],
        )

        # 验证数据一致性
        assert interview.questions[0].company == interview.company
        assert interview.questions[0].position == interview.position

        print("Model integration test: PASSED")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])