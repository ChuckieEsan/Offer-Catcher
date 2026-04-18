"""session_summaries 表操作测试

测试 session_summaries 表的 CRUD 操作和语义检索功能。
注意：测试在 test 数据库中进行，避免影响业务数据。
"""

import os
import sys
import uuid
from pathlib import Path

import numpy as np
import pytest

# 设置测试环境变量
os.environ["POSTGRES_DB"] = "offer_catcher_test"

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.infrastructure.persistence.postgres import PostgresClient, SessionSummary, get_postgres_client
from app.infrastructure.common.logger import logger


@pytest.fixture
def postgres_client():
    """获取 PostgreSQL 客户端"""
    client = get_postgres_client()
    yield client
    # 不关闭连接，因为是单例


@pytest.fixture
def test_user_id():
    """测试用户 ID"""
    return f"test_memory_user_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_conversation(postgres_client, test_user_id):
    """创建测试对话"""
    conv = postgres_client.create_conversation(test_user_id, "记忆测试对话")
    yield conv
    # 清理：删除对话（CASCADE 会自动删除 session_summaries）
    postgres_client.delete_conversation(test_user_id, conv.id)


class TestSessionSummaryCRUD:
    """测试 SessionSummary CRUD 操作"""

    def test_create_session_summary(
        self,
        postgres_client: PostgresClient,
        test_user_id: str,
        test_conversation,
    ):
        """测试创建会话摘要"""
        summary_text = "讨论了 RAG 原理。关键问题：召回阈值怎么设置？用户反馈：希望有代码示例"
        embedding = [0.1] * 1024  # 模拟向量
        metadata = {"key_questions": ["召回阈值怎么设置？"]}

        result = postgres_client.create_session_summary(
            conversation_id=test_conversation.id,
            user_id=test_user_id,
            summary=summary_text,
            embedding=embedding,
            session_type="chat",
            metadata=metadata,
        )

        assert result is not None
        assert result.conversation_id == test_conversation.id
        assert result.user_id == test_user_id
        assert result.summary == summary_text
        assert np.allclose(result.embedding, embedding)
        assert result.session_type == "chat"
        assert result.metadata == metadata

    def test_create_session_summary_without_embedding(
        self,
        postgres_client: PostgresClient,
        test_user_id: str,
    ):
        """测试创建不带向量的会话摘要（embedding 失败时的降级）"""
        conv = postgres_client.create_conversation(test_user_id, "无向量测试对话")

        result = postgres_client.create_session_summary(
            conversation_id=conv.id,
            user_id=test_user_id,
            summary="主题：无向量测试",
            embedding=None,  # 无向量
            session_type="chat",
        )

        assert result is not None
        assert result.embedding is None

        # 清理
        postgres_client.delete_conversation(test_user_id, conv.id)

    def test_get_session_summary(
        self,
        postgres_client: PostgresClient,
        test_user_id: str,
        test_conversation,
    ):
        """测试获取会话摘要"""
        # 先创建
        postgres_client.create_session_summary(
            conversation_id=test_conversation.id,
            user_id=test_user_id,
            summary="测试摘要内容",
            embedding=[0.2] * 1024,
        )

        # 再获取
        result = postgres_client.get_session_summary(
            conversation_id=test_conversation.id,
            user_id=test_user_id,
        )

        assert result is not None
        assert result.summary == "测试摘要内容"

    def test_get_session_summary_not_found(
        self,
        postgres_client: PostgresClient,
        test_user_id: str,
    ):
        """测试获取不存在的会话摘要"""
        result = postgres_client.get_session_summary(
            conversation_id="non_existent_conv_id",
            user_id=test_user_id,
        )
        assert result is None

    def test_update_session_summary(
        self,
        postgres_client: PostgresClient,
        test_user_id: str,
        test_conversation,
    ):
        """测试更新会话摘要"""
        # 先创建
        postgres_client.create_session_summary(
            conversation_id=test_conversation.id,
            user_id=test_user_id,
            summary="原始摘要",
            embedding=[0.3] * 1024,
        )

        # 更新
        updated = postgres_client.update_session_summary(
            conversation_id=test_conversation.id,
            user_id=test_user_id,
            summary="更新后的摘要",
            embedding=[0.4] * 1024,
            metadata={"updated": True},
        )

        assert updated is True

        # 验证
        result = postgres_client.get_session_summary(
            conversation_id=test_conversation.id,
            user_id=test_user_id,
        )
        assert result.summary == "更新后的摘要"

    def test_update_session_summary_only_text(
        self,
        postgres_client: PostgresClient,
        test_user_id: str,
        test_conversation,
    ):
        """测试只更新摘要文本（不更新向量）"""
        # 先创建
        postgres_client.create_session_summary(
            conversation_id=test_conversation.id,
            user_id=test_user_id,
            summary="原始摘要",
            embedding=[0.5] * 1024,
        )

        # 只更新文本
        updated = postgres_client.update_session_summary(
            conversation_id=test_conversation.id,
            user_id=test_user_id,
            summary="只更新文本",
        )

        assert updated is True

        # 验证向量保持不变
        result = postgres_client.get_session_summary(
            conversation_id=test_conversation.id,
            user_id=test_user_id,
        )
        assert result.summary == "只更新文本"
        assert np.allclose(result.embedding, [0.5] * 1024)

    def test_count_session_summaries(
        self,
        postgres_client: PostgresClient,
        test_user_id: str,
    ):
        """测试统计会话摘要数量"""
        # 创建多个对话和摘要
        convs = []
        for i in range(3):
            conv = postgres_client.create_conversation(test_user_id, f"统计测试{i}")
            postgres_client.create_session_summary(
                conversation_id=conv.id,
                user_id=test_user_id,
                summary=f"摘要{i}",
                embedding=[0.1] * 1024,
            )
            convs.append(conv)

        # 统计
        count = postgres_client.count_session_summaries(test_user_id)
        assert count >= 3

        # 清理
        for conv in convs:
            postgres_client.delete_conversation(test_user_id, conv.id)

    def test_cascade_delete(
        self,
        postgres_client: PostgresClient,
        test_user_id: str,
    ):
        """测试 CASCADE DELETE：删除对话时自动删除摘要"""
        # 创建对话和摘要
        conv = postgres_client.create_conversation(test_user_id, "CASCADE 测试")
        postgres_client.create_session_summary(
            conversation_id=conv.id,
            user_id=test_user_id,
            summary="将被 CASCADE 删除的摘要",
            embedding=[0.1] * 1024,
        )

        # 删除对话
        postgres_client.delete_conversation(test_user_id, conv.id)

        # 验证摘要也被删除
        result = postgres_client.get_session_summary(
            conversation_id=conv.id,
            user_id=test_user_id,
        )
        assert result is None


class TestSessionSummarySearch:
    """测试 SessionSummary 语义检索"""

    def test_search_session_summaries(
        self,
        postgres_client: PostgresClient,
        test_user_id: str,
    ):
        """测试语义检索"""
        # 创建多个对话和摘要
        convs = []
        summaries_data = [
            ("RAG 原理讨论", "讨论了向量检索和召回阈值"),
            ("Agent 架构对比", "对比了 LangChain 和 LangGraph"),
            ("Python 基础", "讲解了 Python 装饰器"),
        ]

        for idx, (title, summary_text) in enumerate(summaries_data):
            conv = postgres_client.create_conversation(test_user_id, title)
            postgres_client.create_session_summary(
                conversation_id=conv.id,
                user_id=test_user_id,
                summary=summary_text,
                embedding=[0.1 + idx * 0.05] * 1024,  # 不同向量
            )
            convs.append(conv)

        # 检索（使用模拟向量）
        query_embedding = [0.12] * 1024  # 应该最接近第一条
        results = postgres_client.search_session_summaries(
            user_id=test_user_id,
            query_embedding=query_embedding,
            top_k=2,
        )

        assert len(results) <= 2
        assert all(hasattr(r, "conversation_id") for r in results)
        assert all(hasattr(r, "summary") for r in results)
        assert all(hasattr(r, "similarity") for r in results)

        # 清理
        for conv in convs:
            postgres_client.delete_conversation(test_user_id, conv.id)

    def test_search_session_summaries_empty_user(
        self,
        postgres_client: PostgresClient,
    ):
        """测试用户无摘要时的检索"""
        results = postgres_client.search_session_summaries(
            user_id="non_existent_user",
            query_embedding=[0.1] * 1024,
            top_k=5,
        )
        assert len(results) == 0

    def test_get_recent_session_summaries(
        self,
        postgres_client: PostgresClient,
        test_user_id: str,
    ):
        """测试获取最近会话摘要"""
        # 创建多个对话和摘要
        convs = []
        for i in range(5):
            conv = postgres_client.create_conversation(test_user_id, f"最近测试{i}")
            postgres_client.create_session_summary(
                conversation_id=conv.id,
                user_id=test_user_id,
                summary=f"摘要{i}",
                embedding=[0.1] * 1024,
            )
            convs.append(conv)

        # 获取最近 3 条
        results = postgres_client.get_recent_session_summaries(
            user_id=test_user_id,
            limit=3,
        )

        assert len(results) <= 3
        assert all(hasattr(r, "title") for r in results)
        assert all(hasattr(r, "summary") for r in results)
        assert all(hasattr(r, "created_at") for r in results)

        # 清理
        for conv in convs:
            postgres_client.delete_conversation(test_user_id, conv.id)


class TestSessionSummaryIsolation:
    """测试多租户隔离"""

    def test_user_isolation(
        self,
        postgres_client: PostgresClient,
    ):
        """测试用户数据隔离"""
        user1 = f"user1_{uuid.uuid4().hex[:8]}"
        user2 = f"user2_{uuid.uuid4().hex[:8]}"

        # 用户1 创建摘要
        conv1 = postgres_client.create_conversation(user1, "用户1对话")
        postgres_client.create_session_summary(
            conversation_id=conv1.id,
            user_id=user1,
            summary="用户1的摘要",
            embedding=[0.1] * 1024,
        )

        # 用户2 创建摘要
        conv2 = postgres_client.create_conversation(user2, "用户2对话")
        postgres_client.create_session_summary(
            conversation_id=conv2.id,
            user_id=user2,
            summary="用户2的摘要",
            embedding=[0.2] * 1024,
        )

        # 用户1 检索只能看到自己的
        results1 = postgres_client.search_session_summaries(
            user_id=user1,
            query_embedding=[0.1] * 1024,
            top_k=10,
        )
        assert all(r.conversation_id != conv2.id for r in results1)

        # 用户2 检索只能看到自己的
        results2 = postgres_client.search_session_summaries(
            user_id=user2,
            query_embedding=[0.2] * 1024,
            top_k=10,
        )
        assert all(r.conversation_id != conv1.id for r in results2)

        # 清理
        postgres_client.delete_conversation(user1, conv1.id)
        postgres_client.delete_conversation(user2, conv2.id)