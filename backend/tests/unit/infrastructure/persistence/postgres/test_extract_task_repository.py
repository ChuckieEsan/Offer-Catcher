"""ExtractTaskRepository 单元测试

测试 PostgresExtractTaskRepository 的实现。
使用 Mock 替代 PostgreSQL 客户端。
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from app.domain.question.aggregates import ExtractTask, ExtractTaskStatus
from app.infrastructure.persistence.postgres.extract_task_repository import (
    PostgresExtractTaskRepository,
)


@pytest.fixture
def mock_client():
    """创建 Mock PostgreSQL 客户端"""
    client = Mock()
    client.conn = Mock()
    client.conn.cursor = Mock()
    client.conn.commit = Mock()
    return client


@pytest.fixture
def extract_task_repo(mock_client):
    """创建 ExtractTask 仓库（使用 Mock 客户端）"""
    return PostgresExtractTaskRepository(client=mock_client)


@pytest.fixture
def sample_extract_task():
    """创建示例 ExtractTask"""
    return ExtractTask(
        task_id="task_test_001",
        source_type="image",
        source_content="https://example.com/image.png",
        status=ExtractTaskStatus.COMPLETED,
        extracted_interview={
            "company": "字节跳动",
            "position": "后端开发",
            "questions": [
                {
                    "question_id": "q1",
                    "question_text": "什么是微服务？",
                    "question_type": "knowledge",
                }
            ],
        },
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


class TestPostgresExtractTaskRepository:
    """PostgresExtractTaskRepository 测试"""

    def test_find_by_id_found(self, extract_task_repo, mock_client, sample_extract_task):
        """测试 find_by_id 找到任务"""
        # Mock PostgresClient 的 get_extract_task 返回
        mock_model_task = Mock()
        mock_model_task.task_id = sample_extract_task.task_id
        mock_model_task.source_type = sample_extract_task.source_type
        mock_model_task.source_content = sample_extract_task.source_content
        mock_model_task.status = sample_extract_task.status
        mock_model_task.result = Mock()
        mock_model_task.result.model_dump = Mock(
            return_value=sample_extract_task.extracted_interview
        )
        mock_model_task.created_at = sample_extract_task.created_at
        mock_model_task.updated_at = sample_extract_task.updated_at

        mock_client.get_extract_task = Mock(return_value=mock_model_task)

        result = extract_task_repo.find_by_id("task_test_001")

        assert result is not None
        assert result.task_id == sample_extract_task.task_id
        assert result.status == sample_extract_task.status
        assert result.extracted_interview is not None

    def test_find_by_id_not_found(self, extract_task_repo, mock_client):
        """测试 find_by_id 未找到"""
        mock_client.get_extract_task = Mock(return_value=None)

        result = extract_task_repo.find_by_id("not_exist")

        assert result is None

    def test_find_by_status(self, extract_task_repo, mock_client, sample_extract_task):
        """测试 find_by_status"""
        # Mock cursor 返回
        mock_cursor = MagicMock()
        mock_cursor.fetchall = Mock(
            return_value=[
                (
                    sample_extract_task.task_id,
                    "user_001",
                    sample_extract_task.source_type,
                    sample_extract_task.source_content,
                    None,  # source_images_gz
                    sample_extract_task.status,
                    None,  # error_message
                    sample_extract_task.extracted_interview,
                    sample_extract_task.created_at,
                    sample_extract_task.updated_at,
                )
            ]
        )
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_client.conn.cursor = Mock(return_value=mock_cursor)

        result = extract_task_repo.find_by_status(ExtractTaskStatus.COMPLETED)

        assert len(result) == 1
        assert result[0].task_id == sample_extract_task.task_id

    def test_find_pending_tasks(self, extract_task_repo, mock_client):
        """测试 find_pending_tasks"""
        # Mock cursor 返回
        mock_cursor = Mock()
        mock_cursor.fetchall = Mock(return_value=[])

        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_client.conn.cursor = Mock(return_value=mock_cursor)

        with patch.object(mock_client.conn, 'cursor', return_value=mock_cursor):
            mock_client.conn.cursor().__enter__ = Mock(return_value=mock_cursor)
            mock_client.conn.cursor().__exit__ = Mock(return_value=None)

            result = extract_task_repo.find_pending_tasks(limit=10)

        assert len(result) == 0

    def test_delete(self, extract_task_repo, mock_client):
        """测试 delete"""
        mock_cursor = Mock()
        mock_cursor.execute = Mock()
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_client.conn.cursor = Mock(return_value=mock_cursor)

        extract_task_repo.delete("task_test_001")

        mock_cursor.execute.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])