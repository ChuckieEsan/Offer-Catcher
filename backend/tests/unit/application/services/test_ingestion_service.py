"""IngestionApplicationService 单元测试

测试入库应用服务的实现。
使用 Mock 替代依赖组件。
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, AsyncMock

from app.application.services.ingestion_service import (
    IngestionApplicationService,
    IngestionResult,
)
from app.domain.question.aggregates import Question, ExtractTask, ExtractTaskStatus
from app.domain.shared.enums import QuestionType, MasteryLevel
from app.models import ExtractedInterview, QuestionItem


@pytest.fixture
def mock_question_repo():
    """创建 Mock Question 仓库"""
    repo = Mock()
    repo.find_by_id = Mock(return_value=None)
    repo.save = Mock()
    repo.search = Mock(return_value=[])
    return repo


@pytest.fixture
def mock_extract_task_repo():
    """创建 Mock ExtractTask 仓库"""
    repo = Mock()
    repo.find_by_id = Mock(return_value=None)
    repo.save = Mock()
    return repo


@pytest.fixture
def mock_embedding():
    """创建 Mock Embedding 适配器"""
    embedding = Mock()
    embedding.embed = Mock(return_value=[0.1] * 1024)
    return embedding


@pytest.fixture
def ingestion_service(mock_question_repo, mock_extract_task_repo, mock_embedding):
    """创建入库服务（使用 Mock 依赖）"""
    return IngestionApplicationService(
        question_repo=mock_question_repo,
        extract_task_repo=mock_extract_task_repo,
        embedding=mock_embedding,
    )


@pytest.fixture
def sample_interview():
    """创建示例 ExtractedInterview"""
    return ExtractedInterview(
        company="字节跳动",
        position="后端开发",
        questions=[
            QuestionItem(
                question_id="q_001",
                question_text="什么是微服务？",
                question_type=QuestionType.KNOWLEDGE,
                company="字节跳动",
                position="后端开发",
                core_entities=["微服务", "架构"],
            ),
            QuestionItem(
                question_id="q_002",
                question_text="介绍一下你的项目经历",
                question_type=QuestionType.PROJECT,
                company="字节跳动",
                position="后端开发",
            ),
        ],
    )


class TestIngestionApplicationService:
    """IngestionApplicationService 测试"""

    def test_init(self, ingestion_service, mock_question_repo):
        """测试初始化"""
        assert ingestion_service._question_repo == mock_question_repo

    @pytest.mark.asyncio
    async def test_ingest_interview_new_questions(
        self,
        ingestion_service,
        mock_question_repo,
        mock_embedding,
        sample_interview,
    ):
        """测试入库新题目"""
        # 所有题目都是新的
        mock_question_repo.find_by_id = Mock(return_value=None)
        mock_question_repo.search = Mock(return_value=[])

        # Mock MQ producer
        mock_producer = AsyncMock()
        mock_producer._connection = Mock()
        mock_producer._connection.is_closed = False
        mock_producer.publish_task = AsyncMock()
        ingestion_service._mq_producer = mock_producer

        result = await ingestion_service.ingest_interview(sample_interview)

        # 验证结果
        assert result.processed == 2
        assert len(result.question_ids) == 2
        # 只有 knowledge 类型会触发异步任务
        assert result.async_tasks == 1

        # 验证 save 被调用
        assert mock_question_repo.save.call_count == 2

    @pytest.mark.asyncio
    async def test_ingest_interview_existing_with_answer(
        self,
        ingestion_service,
        mock_question_repo,
        sample_interview,
    ):
        """测试已存在且有答案的题目"""
        # Mock 已存在的题目（有答案）
        existing_question = Question(
            question_id="q_001",
            question_text="什么是微服务？",
            question_type=QuestionType.KNOWLEDGE,
            mastery_level=MasteryLevel.LEVEL_1,
            company="字节跳动",
            position="后端开发",
            answer="微服务是一种架构风格...",
        )
        mock_question_repo.find_by_id = Mock(
            side_effect=lambda id: existing_question if id == "q_001" else None
        )
        mock_question_repo.search = Mock(return_value=[])

        # Mock MQ producer
        mock_producer = AsyncMock()
        mock_producer._connection = Mock()
        mock_producer._connection.is_closed = False
        ingestion_service._mq_producer = mock_producer

        result = await ingestion_service.ingest_interview(sample_interview)

        # q_001 已存在且有答案，不入库但计入 question_ids
        # q_002 是新题目（project 类型），入库但不触发 MQ
        assert result.processed == 1  # 只有 q_002 入库
        # q_001 被跳过，但仍计入 question_ids（用于追踪）
        assert len(result.question_ids) >= 1
        assert result.async_tasks == 0  # project 类型不触发 MQ

    @pytest.mark.asyncio
    async def test_ingest_interview_reuse_answer(
        self,
        ingestion_service,
        mock_question_repo,
        mock_embedding,
        sample_interview,
    ):
        """测试复用相似题目的答案"""
        mock_question_repo.find_by_id = Mock(return_value=None)

        # Mock 相似题目（有答案）
        similar_question = Question(
            question_id="similar_001",
            question_text="微服务是什么？",
            question_type=QuestionType.KNOWLEDGE,
            mastery_level=MasteryLevel.LEVEL_1,
            company="字节跳动",
            position="后端开发",
            answer="微服务是一种架构风格...",
        )
        mock_question_repo.search = Mock(return_value=[similar_question])

        result = await ingestion_service.ingest_interview(sample_interview)

        # 验证复用答案
        assert result.processed == 2
        # 复用答案的题目不会触发异步任务
        assert result.async_tasks == 0

    @pytest.mark.asyncio
    async def test_ingest_from_task(
        self,
        ingestion_service,
        mock_extract_task_repo,
        mock_question_repo,
    ):
        """测试从任务入库"""
        # Mock 任务
        task = ExtractTask(
            task_id="task_001",
            source_type="image",
            source_content="url",
            status=ExtractTaskStatus.COMPLETED,
            extracted_interview={
                "company": "字节跳动",
                "position": "后端开发",
                "questions": [
                    {
                        "question_id": "q_001",
                        "question_text": "测试题目",
                        "question_type": "knowledge",
                        "company": "字节跳动",
                        "position": "后端开发",
                    }
                ],
            },
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        mock_extract_task_repo.find_by_id = Mock(return_value=task)
        mock_question_repo.find_by_id = Mock(return_value=None)
        mock_question_repo.search = Mock(return_value=[])

        # Mock MQ producer
        mock_producer = AsyncMock()
        mock_producer._connection = Mock()
        mock_producer._connection.is_closed = False
        ingestion_service._mq_producer = mock_producer

        result = await ingestion_service.ingest_from_task("task_001")

        assert result.processed == 1
        # 验证任务状态更新
        assert mock_extract_task_repo.save.called

    @pytest.mark.asyncio
    async def test_ingest_from_task_not_found(
        self,
        ingestion_service,
        mock_extract_task_repo,
    ):
        """测试任务不存在"""
        mock_extract_task_repo.find_by_id = Mock(return_value=None)

        with pytest.raises(ValueError, match="ExtractTask not found"):
            await ingestion_service.ingest_from_task("not_exist")

    @pytest.mark.asyncio
    async def test_ingest_from_task_not_ready(
        self,
        ingestion_service,
        mock_extract_task_repo,
    ):
        """测试任务未准备好"""
        task = ExtractTask(
            task_id="task_001",
            source_type="image",
            source_content="url",
            status=ExtractTaskStatus.PENDING,  # 未完成
            extracted_interview=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        mock_extract_task_repo.find_by_id = Mock(return_value=task)

        with pytest.raises(ValueError, match="not ready for ingestion"):
            await ingestion_service.ingest_from_task("task_001")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])