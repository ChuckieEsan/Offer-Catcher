"""Cluster 仓库的 Qdrant 实现

实现 ClusterRepository Protocol，基于 Qdrant 向量数据库持久化 Cluster 聚合。
由于 Cluster 不需要向量检索，使用同一 collection，通过 entity_type 区分。
"""

from typing import Optional

from qdrant_client import models
from qdrant_client.models import PointStruct

from app.domain.question.aggregates import Cluster
from app.domain.question.repositories import ClusterRepository

from app.infrastructure.persistence.qdrant.client import (
    QdrantClient,
    get_qdrant_client,
)
from app.infrastructure.common.logger import logger


# Cluster 存储的 entity_type 标识
ENTITY_TYPE_CLUSTER = "cluster"


class QdrantClusterRepository:
    """Cluster 仓库的 Qdrant 实现

    实现 ClusterRepository Protocol 的所有方法。
    使用与 Question 相同的 Qdrant collection，通过 payload 的 entity_type 字段区分。

    注意：
    - Cluster 不需要向量检索，使用零向量作为占位
    - find_by_question_id 通过 payload 的 question_ids 字段反向查询
    """

    def __init__(
        self,
        client: Optional[QdrantClient] = None,
    ) -> None:
        """初始化仓库

        Args:
            client: Qdrant 客户端（支持依赖注入）
        """
        self._client = client or get_qdrant_client()
        # 确保集合存在
        self._client.ensure_collection_exists()

    def _build_cluster_filter(self) -> models.Filter:
        """构建 Cluster 类型过滤条件"""
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="entity_type",
                    match=models.MatchValue(value=ENTITY_TYPE_CLUSTER),
                )
            ]
        )

    def _build_question_id_filter(self, question_id: str) -> models.Filter:
        """构建包含指定题目的 Cluster 过滤条件"""
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="entity_type",
                    match=models.MatchValue(value=ENTITY_TYPE_CLUSTER),
                ),
                models.FieldCondition(
                    key="question_ids",
                    match=models.MatchValue(value=question_id),
                ),
            ]
        )

    def find_by_id(self, cluster_id: str) -> Cluster | None:
        """根据 ID 查找考点簇

        Args:
            cluster_id: 考点簇唯一标识

        Returns:
            Cluster 实例或 None
        """
        try:
            results = self._client.retrieve(ids=[cluster_id])
            if results:
                payload = results[0].payload
                if payload and payload.get("entity_type") == ENTITY_TYPE_CLUSTER:
                    return Cluster.from_payload(payload)
            return None
        except Exception as e:
            logger.error(f"Failed to find cluster {cluster_id}: {e}")
            raise

    def save(self, cluster: Cluster) -> None:
        """保存考点簇

        Args:
            cluster: Cluster 实例
        """
        try:
            # 构建 payload，添加 entity_type 标识
            payload = cluster.to_payload()
            payload["entity_type"] = ENTITY_TYPE_CLUSTER

            # 使用零向量作为占位（Cluster 不需要向量检索）
            dummy_vector = [0.0] * self._client.vector_size

            # 构建 Point 结构
            point = PointStruct(
                id=cluster.cluster_id,
                vector=dummy_vector,
                payload=payload,
            )

            # Upsert
            self._client.upsert(points=[point])
            logger.info(f"Saved cluster: {cluster.cluster_id}")

        except Exception as e:
            logger.error(f"Failed to save cluster {cluster.cluster_id}: {e}")
            raise

    def delete(self, cluster_id: str) -> None:
        """删除考点簇

        Args:
            cluster_id: 考点簇唯一标识
        """
        try:
            self._client.delete(ids=[cluster_id])
            logger.info(f"Deleted cluster: {cluster_id}")
        except Exception as e:
            logger.error(f"Failed to delete cluster {cluster_id}: {e}")
            raise

    def find_all(self) -> list[Cluster]:
        """获取所有考点簇

        Returns:
            所有 Cluster 列表
        """
        try:
            all_clusters = []
            offset = None
            batch_size = 1000
            query_filter = self._build_cluster_filter()

            while True:
                results, offset = self._client.scroll(
                    limit=batch_size,
                    offset=offset,
                    query_filter=query_filter,
                )

                for point in results:
                    if point.payload:
                        try:
                            cluster = Cluster.from_payload(point.payload)
                            all_clusters.append(cluster)
                        except Exception as e:
                            logger.warning(f"Failed to parse cluster {point.id}: {e}")

                if offset is None:
                    break

            logger.info(f"Found all clusters, total: {len(all_clusters)}")
            return all_clusters

        except Exception as e:
            logger.error(f"Failed to find all clusters: {e}")
            raise

    def find_by_question_id(self, question_id: str) -> list[Cluster]:
        """查找包含指定题目的考点簇

        Args:
            question_id: 题目 ID

        Returns:
            包含该题目的 Cluster 列表
        """
        try:
            all_clusters = []
            offset = None
            batch_size = 100
            query_filter = self._build_question_id_filter(question_id)

            while True:
                results, offset = self._client.scroll(
                    limit=batch_size,
                    offset=offset,
                    query_filter=query_filter,
                )

                for point in results:
                    if point.payload:
                        try:
                            cluster = Cluster.from_payload(point.payload)
                            all_clusters.append(cluster)
                        except Exception as e:
                            logger.warning(f"Failed to parse cluster {point.id}: {e}")

                if offset is None:
                    break

            logger.info(
                f"Found {len(all_clusters)} clusters containing question {question_id}"
            )
            return all_clusters

        except Exception as e:
            logger.error(f"Failed to find clusters by question_id: {e}")
            raise

    def count(self) -> int:
        """统计考点簇总数"""
        try:
            query_filter = self._build_cluster_filter()
            return self._client.count(query_filter=query_filter)
        except Exception as e:
            logger.error(f"Failed to count clusters: {e}")
            raise


# 单例获取函数
_cluster_repository: Optional[QdrantClusterRepository] = None


def get_cluster_repository() -> QdrantClusterRepository:
    """获取 Cluster 仓库单例"""
    global _cluster_repository
    if _cluster_repository is None:
        _cluster_repository = QdrantClusterRepository()
    return _cluster_repository


__all__ = [
    "QdrantClusterRepository",
    "get_cluster_repository",
]