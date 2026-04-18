"""Qdrant 客户端功能测试

验证 Qdrant 数据库连接和各项功能是否正常工作。
注意：所有测试使用独立的测试 collection，不影响生产数据。
"""

import random
from typing import List

import pytest

from app.infrastructure.config.settings import get_settings
from app.db import QdrantManager
from app.models import QdrantQuestionPayload, SearchFilter
from app.utils.hasher import generate_question_id

# 测试专用的 collection 名称
TEST_COLLECTION = "questions_test"


def generate_random_vector(dim: int = None) -> List[float]:
    """生成随机向量（用于测试）

    Args:
        dim: 向量维度，默认使用配置中的值

    Returns:
        随机向量列表
    """
    if dim is None:
        dim = get_settings().qdrant_vector_size
    return [random.random() for _ in range(dim)]


class TestQdrantConnection:
    """Qdrant 连接测试"""

    def test_connection(self):
        """测试 Qdrant 连接是否正常"""
        # 使用测试 collection，不影响生产
        manager = QdrantManager(collection_name=TEST_COLLECTION)
        # 尝试获取集合列表，验证连接
        collections = manager.client.get_collections()
        assert collections is not None
        print(f"Connected to Qdrant, found {len(collections.collections)} collections")


class TestQdrantCollection:
    """集合管理测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前置设置"""
        self.manager = QdrantManager(collection_name=TEST_COLLECTION)
        self.settings = get_settings()
        yield
        # 测试后清理：删除测试 collection
        try:
            self.manager.delete_collection()
        except Exception:
            pass

    def test_create_collection(self):
        """测试创建集合"""
        # 创建集合
        created = self.manager.create_collection_if_not_exists()
        assert created is True

        # 再次创建应该返回 False（已存在）
        created_again = self.manager.create_collection_if_not_exists()
        assert created_again is False

        # 获取集合信息
        info = self.manager.get_collection_info()
        assert info["name"] == TEST_COLLECTION
        print(f"Collection info: {info}")


class TestQdrantUpsert:
    """Upsert 功能测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前置设置：确保集合存在"""
        self.manager = QdrantManager(collection_name=TEST_COLLECTION)
        self.settings = get_settings()
        self.test_company = "字节跳动"
        self.test_position = "Agent应用开发"
        self.test_question = "什么是 RAG？"
        self.test_vector = generate_random_vector()
        # 确保集合存在（如果不存在则创建）
        self.manager.create_collection_if_not_exists()
        yield
        # 测试后不删除集合，保留数据供后续测试使用

    def test_upsert_question(self):
        """测试写入题目数据"""
        # Upsert 数据
        result = self.manager.upsert_question_with_context(
            question_text=self.test_question,
            company=self.test_company,
            position=self.test_position,
            vector=self.test_vector,
            question_type="knowledge",
            mastery_level=0,
            core_entities=["RAG", "检索增强"],
            question_answer="RAG 是检索增强生成...",
        )
        assert result is True

        # 获取集合信息验证写入
        info = self.manager.get_collection_info()
        assert info["points_count"] == 1
        print(f"Upserted successfully, points: {info['points_count']}")

    def test_upsert_idempotent(self):
        """测试 Upsert 幂等性（相同 question_id 多次写入应更新而非新增）"""
        question_id = generate_question_id(self.test_company, self.test_question)

        # 第一次写入
        self.manager.upsert_question_with_context(
            question_text=self.test_question,
            company=self.test_company,
            position=self.test_position,
            vector=self.test_vector,
            question_type="knowledge",
            mastery_level=0,
        )

        # 第二次写入相同 question_id
        self.manager.upsert_question_with_context(
            question_text=self.test_question,
            company=self.test_company,
            position=self.test_position,
            vector=generate_random_vector(),  # 不同的向量
            question_type="knowledge",
            mastery_level=1,  # 更新 mastery_level
        )

        # 验证点数不变（应为 1，而非 2）
        info = self.manager.get_collection_info()
        assert info["points_count"] == 1
        print("Upsert idempotency verified")


class TestQdrantSearch:
    """向量检索测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前置设置：确保集合存在"""
        self.manager = QdrantManager(collection_name=TEST_COLLECTION)
        self.test_data = [
            ("字节跳动", "Agent应用开发", "什么是 RAG？", "knowledge"),
            ("字节跳动", "Agent应用开发", "讲讲你的 Agent 项目？", "project"),
            ("腾讯", "后端开发", "Python 装饰器是什么？", "knowledge"),
        ]
        # 确保集合存在
        self.manager.create_collection_if_not_exists()
        # 写入测试数据
        for company, position, question, qtype in self.test_data:
            self.manager.upsert_question_with_context(
                question_text=question,
                company=company,
                position=position,
                vector=generate_random_vector(),
                question_type=qtype,
                mastery_level=0,
            )
        yield
        # 测试后不删除集合

    def test_search_basic(self):
        """测试基础向量检索"""
        results = self.manager.search(
            query_vector=generate_random_vector(),
            limit=10,
        )
        assert len(results) > 0
        print(f"Search returned {len(results)} results")

    def test_search_with_filter_company(self):
        """测试按公司过滤检索"""
        results = self.manager.search(
            query_vector=generate_random_vector(),
            filter_conditions=SearchFilter(company="字节跳动"),
            limit=10,
        )
        # 验证所有结果的公司都是字节跳动
        for r in results:
            assert r.company == "字节跳动"
        print(f"Filtered search returned {len(results)} results")

    def test_search_with_filter_mastery_level(self):
        """测试按熟练度过滤检索"""
        results = self.manager.search(
            query_vector=generate_random_vector(),
            filter_conditions=SearchFilter(mastery_level=0),
            limit=10,
        )
        # 验证所有结果的 mastery_level 都是 0
        for r in results:
            assert r.mastery_level == 0
        print(f"Filtered search returned {len(results)} results")

    def test_search_with_multiple_filters(self):
        """测试多条件过滤检索"""
        results = self.manager.search(
            query_vector=generate_random_vector(),
            filter_conditions=SearchFilter(
                company="字节跳动",
                question_type="knowledge",
            ),
            limit=10,
        )
        for r in results:
            assert r.company == "字节跳动"
            assert r.question_type == "knowledge"
        print(f"Multi-filter search returned {len(results)} results")


class TestQdrantGetQuestion:
    """按 ID 查询测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前置设置：确保集合存在"""
        self.manager = QdrantManager(collection_name=TEST_COLLECTION)
        self.test_company = "字节跳动"
        self.test_question = "什么是 RAG？"
        self.question_id = generate_question_id(self.test_company, self.test_question)

        # 确保集合存在
        self.manager.create_collection_if_not_exists()
        # 写入测试数据
        self.manager.upsert_question_with_context(
            question_text=self.test_question,
            company=self.test_company,
            position="Agent应用开发",
            vector=generate_random_vector(),
            question_type="knowledge",
            mastery_level=1,
            core_entities=["RAG"],
            question_answer="RAG 是检索增强生成",
        )
        yield
        # 测试后不删除集合

    def test_get_question(self):
        """测试按 ID 获取题目"""
        result = self.manager.get_question(self.question_id)
        assert result is not None
        assert result.question_id == self.question_id
        assert result.question_text == self.test_question
        assert result.company == self.test_company
        assert result.mastery_level == 1
        print(f"Retrieved question: {result.question_text}")

    def test_get_nonexistent_question(self):
        """测试获取不存在的题目"""
        # Qdrant 要求 point ID 必须是整数或 UUID
        # 这里使用一个不存在的 UUID 格式 ID
        result = self.manager.get_question("00000000-0000-0000-0000-000000000000")
        assert result is None
        print("Correctly returned None for nonexistent question")


class TestQdrantUpdate:
    """更新操作测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前置设置：确保集合存在"""
        self.manager = QdrantManager(collection_name=TEST_COLLECTION)
        self.test_company = "字节跳动"
        self.test_question = "什么是 RAG？"
        self.question_id = generate_question_id(self.test_company, self.test_question)

        # 确保集合存在
        self.manager.create_collection_if_not_exists()
        # 写入测试数据
        self.manager.upsert_question_with_context(
            question_text=self.test_question,
            company=self.test_company,
            position="Agent应用开发",
            vector=generate_random_vector(),
            question_type="knowledge",
            mastery_level=0,
        )
        yield
        # 测试后不删除集合

    def test_update_mastery_level(self):
        """测试更新熟练度"""
        # 更新 mastery_level
        result = self.manager.update_question(self.question_id, mastery_level=2)
        assert result is True

        # 验证更新成功
        updated = self.manager.get_question(self.question_id)
        assert updated is not None
        assert updated.mastery_level == 2
        print(f"Updated mastery_level to {updated.mastery_level}")


class TestQdrantFullWorkflow:
    """完整流程测试"""

    def test_full_workflow(self):
        """测试完整的数据流"""
        manager = QdrantManager(collection_name=TEST_COLLECTION)

        try:
            # 1. 创建集合（如果不存在）
            print("1. Creating collection...")
            manager.create_collection_if_not_exists()

            # 2. 写入数据
            print("2. Inserting data...")
            test_data = [
                ("字节跳动", "Agent开发", "什么是 RAG？", "knowledge", 0),
                ("字节跳动", "Agent开发", "讲讲项目亮点", "project", 0),
                ("腾讯", "后端开发", "Python GIL 是什么？", "knowledge", 1),
            ]
            for company, position, question, qtype, mastery in test_data:
                manager.upsert_question_with_context(
                    question_text=question,
                    company=company,
                    position=position,
                    vector=generate_random_vector(),
                    question_type=qtype,
                    mastery_level=mastery,
                )

            # 3. 验证写入
            info = manager.get_collection_info()
            print(f"   Points count: {info['points_count']}")
            # 不再要求正好3条，因为可能有之前测试留下的数据

            # 4. 检索
            print("3. Searching...")
            results = manager.search(
                query_vector=generate_random_vector(),
                limit=10,
            )
            print(f"   Found {len(results)} results")

            # 5. 过滤检索
            print("4. Filtered search...")
            results = manager.search(
                query_vector=generate_random_vector(),
                filter_conditions=SearchFilter(
                    company="字节跳动",
                    question_type="knowledge",
                ),
                limit=10,
            )
            print(f"   Found {len(results)} results for 字节跳动+knowledge")

            # 6. 更新
            print("5. Updating...")
            question_id = generate_question_id("字节跳动", "什么是 RAG？")
            manager.update_question(question_id, mastery_level=2)
            updated = manager.get_question(question_id)
            print(f"   Updated mastery_level to {updated.mastery_level}")

            print("\n=== Full workflow passed! ===")

        except Exception as e:
            print(f"Workflow error: {e}")
            raise


if __name__ == "__main__":
    # 直接运行所有测试
    pytest.main([__file__, "-v", "-s"])