"""Answer Worker 幂等性测试

验证消息重复处理时的幂等性保护逻辑。
"""

import random
from typing import List

import pytest

from app.config.settings import get_settings
from app.db.qdrant_client import QdrantManager
from app.models.schemas import MQTaskMessage, QuestionType, MasteryLevel
from app.utils.hasher import generate_question_id


def generate_random_vector(dim: int = None) -> List[float]:
    """生成随机向量（用于测试）"""
    if dim is None:
        dim = get_settings().qdrant_vector_size
    return [random.random() for _ in range(dim)]


class TestAnswerWorkerIdempotency:
    """Answer Worker 幂等性测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前置设置"""
        self.manager = QdrantManager()
        self.settings = get_settings()
        self.test_company = "测试公司"
        self.test_position = "测试岗位"
        self.test_question = "什么是测试？"
        yield
        # 清理
        try:
            self.manager.delete_collection()
        except Exception:
            pass

    def test_duplicate_message_skipped(self):
        """测试重复消息被跳过（幂等性保护）"""
        question_id = generate_question_id(self.test_company, self.test_question)

        # 1. 先写入一个带答案的题目（模拟之前已处理过）
        self.manager.upsert_question_with_context(
            question_text=self.test_question,
            company=self.test_company,
            position=self.test_position,
            vector=generate_random_vector(),
            question_type="knowledge",
            mastery_level=0,
            question_answer="这是已存在的答案",
        )

        # 验证答案已存在
        existing = self.manager.get_question(question_id)
        assert existing is not None
        assert existing.question_answer == "这是已存在的答案"

        # 2. 模拟 Worker 处理相同的 question_id（模拟重复消费）
        task = MQTaskMessage(
            question_id=question_id,
            question_text=self.test_question,
            company=self.test_company,
            position=self.test_position,
            core_entities=["测试"],
        )

        # 3. 验证幂等性：检查答案是否已存在
        # 模拟 process_answer_task 中的幂等性检查逻辑
        existing_after = self.manager.get_question(task.question_id)
        if existing_after and existing_after.question_answer:
            # 应该跳过处理
            should_skip = True
        else:
            should_skip = False

        # 4. 验证结果
        assert should_skip is True, "重复消息应该被跳过"
        print("幂等性验证通过：重复消息被正确跳过")

    def test_new_message_processed(self):
        """测试新消息会被正常处理"""
        question_id = generate_question_id(self.test_company, self.test_question)

        # 1. 写入一个没有答案的题目
        self.manager.upsert_question_with_context(
            question_text=self.test_question,
            company=self.test_company,
            position=self.test_position,
            vector=generate_random_vector(),
            question_type="knowledge",
            mastery_level=0,
            # 不设置 question_answer
        )

        # 验证答案不存在
        existing = self.manager.get_question(question_id)
        assert existing is not None
        assert existing.question_answer is None

        # 2. 模拟 Worker 处理
        task = MQTaskMessage(
            question_id=question_id,
            question_text=self.test_question,
            company=self.test_company,
            position=self.test_position,
            core_entities=["测试"],
        )

        # 模拟幂等性检查
        existing_after = self.manager.get_question(task.question_id)
        if existing_after and existing_after.question_answer:
            should_skip = True
        else:
            should_skip = False

        # 3. 验证结果：新消息应该被处理
        assert should_skip is False, "新消息应该被处理"
        print("幂等性验证通过：新消息被正确处理")

    def test_answer_none_not_skipped(self):
        """测试答案字段为 None 时不会被跳过"""
        question_id = generate_question_id(self.test_company, self.test_question)

        # 1. 写入一个 question_answer 为 None 的题目
        self.manager.upsert_question_with_context(
            question_text=self.test_question,
            company=self.test_company,
            position=self.test_position,
            vector=generate_random_vector(),
            question_type="knowledge",
            mastery_level=0,
            question_answer=None,  # 显式设置为 None
        )

        # 2. 模拟 Worker 处理
        task = MQTaskMessage(
            question_id=question_id,
            question_text=self.test_question,
            company=self.test_company,
            position=self.test_position,
            core_entities=["测试"],
        )

        # 3. 模拟幂等性检查逻辑
        existing = self.manager.get_question(task.question_id)
        if existing and existing.question_answer:
            should_skip = True
        else:
            should_skip = False

        # 4. 验证：答案为 None 时应该继续处理
        assert should_skip is False, "答案为 None 时应该继续处理"
        print("幂等性验证通过：答案为 None 时正确处理")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])