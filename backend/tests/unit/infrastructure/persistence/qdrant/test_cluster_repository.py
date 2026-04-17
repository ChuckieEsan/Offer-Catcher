"""ClusterRepository 单元测试

测试 QdrantClusterRepository 的实现。
使用 Mock 替代 Qdrant 客户端。
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock

from app.domain.question.aggregates import Cluster
from app.infrastructure.persistence.qdrant.cluster_repository import (
    QdrantClusterRepository,
    ENTITY_TYPE_CLUSTER,
)


@pytest.fixture
def mock_client():
    """创建 Mock Qdrant 客户端"""
    client = Mock()
    client.vector_size = 1024
    client.ensure_collection_exists = Mock()
    return client


@pytest.fixture
def cluster_repo(mock_client):
    """创建 Cluster 仓库（使用 Mock 客户端）"""
    return QdrantClusterRepository(client=mock_client)


@pytest.fixture
def sample_cluster():
    """创建示例 Cluster"""
    return Cluster(
        cluster_id="cluster_test_001",
        cluster_name="QLoRA 显存优化",
        summary="大模型量化训练技术",
        knowledge_points=["量化", "LoRA", "显存优化"],
        question_ids=["q1", "q2", "q3"],
        frequency=3,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


class TestQdrantClusterRepository:
    """QdrantClusterRepository 测试"""

    def test_find_by_id_found(self, cluster_repo, mock_client, sample_cluster):
        """测试 find_by_id 找到 Cluster"""
        # Mock 返回结果
        mock_record = Mock()
        mock_record.payload = sample_cluster.to_payload()
        mock_record.payload["entity_type"] = ENTITY_TYPE_CLUSTER
        mock_client.retrieve = Mock(return_value=[mock_record])

        # 执行
        result = cluster_repo.find_by_id("cluster_test_001")

        # 验证
        assert result is not None
        assert result.cluster_id == sample_cluster.cluster_id
        assert result.cluster_name == sample_cluster.cluster_name
        mock_client.retrieve.assert_called_once_with(ids=["cluster_test_001"])

    def test_find_by_id_not_found(self, cluster_repo, mock_client):
        """测试 find_by_id 未找到"""
        mock_client.retrieve = Mock(return_value=[])

        result = cluster_repo.find_by_id("not_exist")

        assert result is None

    def test_find_by_id_wrong_entity_type(self, cluster_repo, mock_client):
        """测试 find_by_id 返回非 Cluster 类型"""
        mock_record = Mock()
        mock_record.payload = {"entity_type": "question"}
        mock_client.retrieve = Mock(return_value=[mock_record])

        result = cluster_repo.find_by_id("some_id")

        assert result is None

    def test_save(self, cluster_repo, mock_client, sample_cluster):
        """测试 save"""
        mock_client.upsert = Mock()

        cluster_repo.save(sample_cluster)

        # 验证 upsert 被调用
        mock_client.upsert.assert_called_once()
        call_args = mock_client.upsert.call_args
        points = call_args[1]["points"]
        assert len(points) == 1
        assert points[0].id == sample_cluster.cluster_id
        assert points[0].payload["entity_type"] == ENTITY_TYPE_CLUSTER
        assert points[0].payload["cluster_name"] == sample_cluster.cluster_name

    def test_delete(self, cluster_repo, mock_client):
        """测试 delete"""
        mock_client.delete = Mock()

        cluster_repo.delete("cluster_test_001")

        mock_client.delete.assert_called_once_with(ids=["cluster_test_001"])

    def test_find_all(self, cluster_repo, mock_client, sample_cluster):
        """测试 find_all"""
        # Mock scroll 返回
        mock_record = Mock()
        mock_record.payload = sample_cluster.to_payload()
        mock_record.payload["entity_type"] = ENTITY_TYPE_CLUSTER
        mock_client.scroll = Mock(
            side_effect=[
                ([mock_record], None),  # 第一次返回数据，offset=None 结束
            ]
        )

        result = cluster_repo.find_all()

        assert len(result) == 1
        assert result[0].cluster_id == sample_cluster.cluster_id

    def test_find_by_question_id(self, cluster_repo, mock_client, sample_cluster):
        """测试 find_by_question_id"""
        # Mock scroll 返回
        mock_record = Mock()
        mock_record.payload = sample_cluster.to_payload()
        mock_record.payload["entity_type"] = ENTITY_TYPE_CLUSTER
        mock_client.scroll = Mock(
            side_effect=[
                ([mock_record], None),
            ]
        )

        result = cluster_repo.find_by_question_id("q1")

        assert len(result) == 1
        assert "q1" in result[0].question_ids

    def test_count(self, cluster_repo, mock_client):
        """测试 count"""
        mock_client.count = Mock(return_value=5)

        result = cluster_repo.count()

        assert result == 5
        mock_client.count.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])