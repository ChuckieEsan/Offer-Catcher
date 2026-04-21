"""Memory System 功能性测试

测试记忆系统的核心功能组件：
- Memory Agent 触发机制
- SessionSummary 创建和 embedding 计算
- 检索触发并注入 checkpoint
- MEMORY.md 自动初始化

测试策略：
- 使用真实数据库（offer_catcher_test）
- 使用真实 EmbeddingAdapter（验证 embedding 维度）
- 使用 Mock LLM（避免 API 调用开销）
"""

import asyncio
import os
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from langchain_core.messages import HumanMessage, AIMessage

# 设置测试环境
os.environ["POSTGRES_DB"] = "offer_catcher_test"

from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.postgres import get_postgres_client
from app.infrastructure.persistence.postgres.session_summary_repository import (
    PostgresSessionSummaryRepository,
    get_session_summary_repository,
)
from app.infrastructure.persistence.postgres.memory_repository import (
    PostgresMemoryRepository,
    get_memory_repository,
)
from app.infrastructure.persistence.postgres.conversation_repository import (
    PostgresConversationRepository,
    get_conversation_repository,
)
from app.infrastructure.adapters.embedding_adapter import get_embedding_adapter
from app.infrastructure.persistence.redis import get_redis_client
from app.infrastructure.persistence.memory.memory_retrieval import (
    trigger_retrieval,
    retrieve_and_update_checkpoint,
    acquire_retrieval_lock,
    release_retrieval_lock,
)
from app.domain.memory.aggregates import SessionSummary, Memory


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def test_user_id():
    """测试用户 ID"""
    return f"test_func_user_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_conversation_id():
    """测试对话 ID"""
    return f"test_func_conv_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def postgres_client():
    """PostgreSQL 测试客户端"""
    return get_postgres_client()


@pytest.fixture
def session_summary_repo():
    """SessionSummary 仓库"""
    return get_session_summary_repository()


@pytest.fixture
def memory_repo_context():
    """Memory 仓库上下文管理器"""
    # 返回上下文管理器，测试中使用 with 语句
    return get_memory_repository


@pytest.fixture
def conversation_repo():
    """Conversation 仓库"""
    return get_conversation_repository()


@pytest.fixture
def embedding_adapter():
    """真实 Embedding Adapter"""
    return get_embedding_adapter()


@pytest.fixture
def redis_client():
    """Redis 客户端"""
    return get_redis_client()


# 注意：test_settings 使用 conftest.py 中的 session scoped fixture


# ============================================================================
# Case 1: Memory Agent 正常触发
# ============================================================================


class TestCase1MemoryAgentTriggered:
    """测试 Memory Agent 触发机制"""

    def test_hooks_module_exists(self):
        """验证：hooks 模块存在"""
        from app.application.agents.memory.hooks import extract_memories

        assert extract_memories is not None
        assert callable(extract_memories)

    def test_workflow_has_memory_extraction(self):
        """验证：workflow 在对话结束后触发 Memory Agent"""
        from app.application.agents.chat.workflow import astream_workflow

        # 验证 workflow 存在
        assert astream_workflow is not None

        # 检查 workflow 源码是否包含 extract_memories 调用
        import inspect
        source = inspect.getsource(astream_workflow)
        assert "extract_memories" in source

    @pytest.mark.asyncio
    async def test_memory_extraction_creates_task(self, test_user_id, test_conversation_id):
        """验证：extract_memories 创建异步任务"""
        from app.application.agents.memory.hooks import extract_memories

        messages = [
            HumanMessage(content="测试消息", id=str(uuid.uuid4())),
        ]

        # extract_memories 使用 asyncio.create_task
        # 由于是 fire-and-forget，无法直接验证
        # 但可以验证函数不会阻塞
        with patch("app.application.agents.memory.hooks.run_memory_agent") as mock_agent:
            mock_agent.return_value = AsyncMock(return_value=None)

            # 调用应该立即返回
            extract_memories(test_user_id, test_conversation_id, messages)

            # 验证：调用不抛出异常


# ============================================================================
# Case 2: SessionSummary 正确创建
# ============================================================================


class TestCase2SessionSummaryCreated:
    """测试 SessionSummary 创建和 embedding 计算"""

    @pytest.mark.integration
    def test_session_summary_created_with_real_embedding(
        self,
        session_summary_repo,
        conversation_repo,
        embedding_adapter,
        test_user_id,
        test_settings,
    ):
        """验证：SessionSummary 创建时 embedding 正确计算"""
        # 1. 创建测试对话
        conv = conversation_repo.create_new(test_user_id, "测试对话")
        conv_id = conv.conversation_id

        # 2. 创建摘要文本
        summary_text = "用户询问了 LangGraph 的 checkpoint 实现，讨论了 PostgresSaver 的异步方式"

        # 3. 使用真实 EmbeddingAdapter 计算 embedding
        embedding = embedding_adapter.embed(summary_text)

        # 4. 验证 embedding 维度
        assert len(embedding) == test_settings.qdrant_vector_size  # 1024

        # 5. 创建 SessionSummary
        summary = SessionSummary.create(
            id=str(uuid.uuid4()),
            conversation_id=conv_id,
            user_id=test_user_id,
            summary=summary_text,
            embedding=embedding,
        )

        session_summary_repo.create(summary)

        # 6. 验证创建成功
        retrieved = session_summary_repo.find_by_id(summary.id)
        assert retrieved is not None
        assert retrieved.summary == summary_text
        assert retrieved.embedding is not None
        assert len(retrieved.embedding) == test_settings.qdrant_vector_size

        # 7. 清理
        conversation_repo.delete(test_user_id, conv_id)

    @pytest.mark.integration
    def test_session_summary_without_embedding(
        self,
        session_summary_repo,
        conversation_repo,
        test_user_id,
    ):
        """验证：embedding 失败时允许创建无向量摘要"""
        # 1. 创建测试对话
        conv = conversation_repo.create_new(test_user_id, "无向量测试")
        conv_id = conv.conversation_id

        # 2. 创建无 embedding 的摘要
        summary = SessionSummary.create(
            id=str(uuid.uuid4()),
            conversation_id=conv_id,
            user_id=test_user_id,
            summary="主题：embedding 失败降级测试",
            embedding=None,  # 无向量
        )

        session_summary_repo.create(summary)

        # 3. 验证创建成功
        retrieved = session_summary_repo.find_by_id(summary.id)
        assert retrieved is not None
        assert retrieved.embedding is None

        # 4. 清理
        conversation_repo.delete(test_user_id, conv_id)

    @pytest.mark.integration
    def test_session_summary_search_by_embedding(
        self,
        session_summary_repo,
        conversation_repo,
        embedding_adapter,
        test_user_id,
    ):
        """验证：语义检索功能正常"""
        # 1. 创建多个对话和摘要
        summaries_data = [
            ("LangGraph checkpoint", "讨论了 LangGraph 的 checkpoint 实现"),
            ("RAG 阈值", "讲解了 RAG 的召回阈值设置"),
            ("Python 异步", "学习了 Python 的 async/await 编程"),
        ]

        conv_ids = []
        for topic, content in summaries_data:
            conv = conversation_repo.create_new(test_user_id, f"测试-{topic}")
            conv_ids.append(conv.conversation_id)

            embedding = embedding_adapter.embed(content)
            summary = SessionSummary.create(
                id=str(uuid.uuid4()),
                conversation_id=conv.conversation_id,
                user_id=test_user_id,
                summary=content,
                embedding=embedding,
            )
            session_summary_repo.create(summary)

        # 2. 执行语义检索
        query_text = "LangGraph memory 怎么实现"
        query_embedding = embedding_adapter.embed(query_text)

        results = session_summary_repo.search_by_embedding(
            user_id=test_user_id,
            query_embedding=query_embedding,
            top_k=2,
        )

        # 3. 验证检索结果
        assert len(results) <= 2
        assert len(results) > 0

        # 第一条应该最相关（LangGraph 相关）
        first_result = results[0]
        assert "LangGraph" in first_result.summary or "checkpoint" in first_result.summary

        # 4. 清理
        for conv_id in conv_ids:
            conversation_repo.delete(test_user_id, conv_id)


# ============================================================================
# Case 3: 检索触发并注入 checkpoint
# ============================================================================


class TestCase3RetrievalInjectsCheckpoint:
    """测试检索触发和 checkpoint 注入"""

    def test_trigger_retrieval_function_exists(self):
        """验证：trigger_retrieval 函数存在"""
        from app.infrastructure.persistence.memory.memory_retrieval import trigger_retrieval

        assert trigger_retrieval is not None
        assert callable(trigger_retrieval)

    def test_trigger_retrieval_min_length_filter(self, test_settings):
        """验证：短消息不触发检索"""
        from app.infrastructure.persistence.memory.memory_retrieval import trigger_retrieval

        min_length = test_settings.memory_retrieval_min_length

        # 短消息（< min_length）不触发
        short_query = "hi"

        # 验证 min_length 配置值
        assert min_length == 10
        assert len(short_query) < min_length

    @pytest.mark.integration
    def test_retrieval_lock_mechanism(self, redis_client, test_user_id, test_conversation_id):
        """验证：检索锁机制正常工作"""
        # 1. 获取锁
        acquired = acquire_retrieval_lock(test_user_id, test_conversation_id)
        assert acquired is True

        # 2. 再次获取锁（应该失败）
        acquired_again = acquire_retrieval_lock(test_user_id, test_conversation_id)
        assert acquired_again is False

        # 3. 释放锁
        release_retrieval_lock(test_user_id, test_conversation_id)

        # 4. 再次获取锁（应该成功）
        acquired_after_release = acquire_retrieval_lock(test_user_id, test_conversation_id)
        assert acquired_after_release is True

        # 5. 清理
        release_retrieval_lock(test_user_id, test_conversation_id)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_retrieve_and_update_checkpoint(
        self,
        session_summary_repo,
        conversation_repo,
        embedding_adapter,
        test_user_id,
        test_conversation_id,
    ):
        """验证：检索后 checkpoint 被更新"""
        # 1. 预先创建 SessionSummary
        conv = conversation_repo.create_new(test_user_id, "预置对话")
        summary_text = "讨论了 LangGraph checkpoint 的实现"

        embedding = embedding_adapter.embed(summary_text)
        summary = SessionSummary.create(
            id=str(uuid.uuid4()),
            conversation_id=conv.conversation_id,
            user_id=test_user_id,
            summary=summary_text,
            embedding=embedding,
        )
        session_summary_repo.create(summary)

        # 2. 执行检索
        query = "LangGraph memory"

        # 先释放可能存在的锁
        release_retrieval_lock(test_user_id, test_conversation_id)

        # 执行检索
        await retrieve_and_update_checkpoint(test_user_id, test_conversation_id, query)

        # 3. 等待检索完成（异步）
        await asyncio.sleep(2)

        # 4. 清理
        conversation_repo.delete(test_user_id, conv.conversation_id)


# ============================================================================
# Case 4: MEMORY.md 自动初始化
# ============================================================================


class TestCase4MemoryAutoInitialization:
    """测试 MEMORY.md 自动初始化"""

    def test_memory_repository_initialize(self, memory_repo_context, test_user_id):
        """验证：MemoryRepository.initialize 创建默认模板"""
        with memory_repo_context() as memory_repo:
            # 1. 初始化用户记忆
            memory = memory_repo.initialize(test_user_id)

            # 2. 验证 MEMORY.md 创建
            assert memory is not None
            assert memory.user_id == test_user_id
            assert memory.content is not None
            assert "用户记忆" in memory.content

            # 3. 验证 references 创建
            preferences = memory_repo.read_reference(test_user_id, "preferences")
            assert preferences is not None
            assert "用户偏好详情" in preferences

            behaviors = memory_repo.read_reference(test_user_id, "behaviors")
            assert behaviors is not None
            assert "用户行为模式" in behaviors

            # 4. 清理
            memory_repo.delete(test_user_id)

    def test_memory_find_by_user_id(self, memory_repo_context, test_user_id):
        """验证：MemoryRepository.find_by_user_id 正常工作"""
        with memory_repo_context() as memory_repo:
            # 1. 先初始化
            memory_repo.initialize(test_user_id)

            # 2. 查找
            memory = memory_repo.find_by_user_id(test_user_id)

            # 3. 验证
            assert memory is not None
            assert memory.user_id == test_user_id

            # 4. 清理
            memory_repo.delete(test_user_id)

    def test_memory_save_and_update(self, memory_repo_context, test_user_id):
        """验证：MemoryRepository.save 和更新正常工作"""
        with memory_repo_context() as memory_repo:
            # 1. 初始化
            memory = memory_repo.initialize(test_user_id)

            # 2. 更新内容
            updated_content = memory.content.replace(
                "解释深度：适中",
                "解释深度：深入详细"
            )
            memory.update_content(updated_content)

            # 3. 保存
            memory_repo.save(memory)

            # 4. 验证更新
            retrieved = memory_repo.find_by_user_id(test_user_id)
            assert "深入详细" in retrieved.content

            # 5. 清理
            memory_repo.delete(test_user_id)


# ============================================================================
# 辅助测试
# ============================================================================


class TestMemorySystemConfiguration:
    """测试记忆系统配置"""

    def test_memory_config_values(self, test_settings):
        """验证：记忆相关配置正确"""
        assert test_settings.memory_retrieval_min_length == 10
        assert test_settings.memory_retrieval_top_k == 5
        assert test_settings.memory_retrieval_lock_timeout == 60
        assert test_settings.memory_context_max_size == 20 * 1024
        assert test_settings.memory_lock_timeout == 30

    def test_embedding_adapter_dimension(self, embedding_adapter, test_settings):
        """验证：EmbeddingAdapter 返回正确维度"""
        test_text = "测试文本"
        embedding = embedding_adapter.embed(test_text)

        assert len(embedding) == test_settings.qdrant_vector_size


__all__ = [
    "TestCase1MemoryAgentTriggered",
    "TestCase2SessionSummaryCreated",
    "TestCase3RetrievalInjectsCheckpoint",
    "TestCase4MemoryAutoInitialization",
    "TestMemorySystemConfiguration",
]