"""Qdrant 向量数据库客户端

提供 Qdrant 的基础连接和集合管理功能。
封装 qdrant-client SDK，为仓库实现提供底层支持。
"""

from typing import Optional

from qdrant_client import QdrantClient as QdrantSDKClient
from qdrant_client import models
from qdrant_client.models import Distance

from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger


class QdrantClient:
    """Qdrant 向量数据库客户端

    提供以下核心功能：
    - 集合初始化与索引创建
    - 基础 CRUD 操作
    - 向量检索

    支持依赖注入，便于测试。
    """

    def __init__(
        self,
        url: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> None:
        """初始化 Qdrant 客户端

        Args:
            url: Qdrant 服务地址，默认使用配置
            collection_name: 集合名称，默认使用配置
        """
        settings = get_settings()
        self._url = url or settings.qdrant_url
        self._collection_name = collection_name or settings.qdrant_collection
        self._vector_size = settings.qdrant_vector_size

        # 建立 SDK 连接
        self._sdk_client = QdrantSDKClient(url=self._url)
        logger.info(f"QdrantClient connected: {self._url}")

    @property
    def collection_name(self) -> str:
        """获取集合名称"""
        return self._collection_name

    @property
    def vector_size(self) -> int:
        """获取向量维度"""
        return self._vector_size

    @property
    def sdk(self) -> QdrantSDKClient:
        """获取底层 SDK 客户端"""
        return self._sdk_client

    def ensure_collection_exists(self) -> bool:
        """确保集合存在，不存在则创建

        Returns:
            是否成功创建（已存在返回 False）
        """
        try:
            collections = self._sdk_client.get_collections().collections
            exists = any(c.name == self._collection_name for c in collections)

            if not exists:
                logger.info(f"Creating collection: {self._collection_name}")
                self._sdk_client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=models.VectorParams(
                        size=self._vector_size,
                        distance=Distance.COSINE,
                    ),
                )
                self._create_payload_indexes()
                logger.info(f"Collection '{self._collection_name}' created")
                return True

            logger.info(f"Collection '{self._collection_name}' already exists")
            return False

        except Exception as e:
            logger.error(f"Failed to ensure collection: {e}")
            raise

    def _create_payload_indexes(self) -> None:
        """创建 Payload 索引"""
        index_fields = [
            ("company", models.KeywordIndexType.KEYWORD),
            ("position", models.KeywordIndexType.KEYWORD),
            ("question_type", models.KeywordIndexType.KEYWORD),
            ("mastery_level", models.IntegerIndexType.INTEGER),
        ]

        for field_name, field_schema in index_fields:
            self._sdk_client.create_payload_index(
                collection_name=self._collection_name,
                field_name=field_name,
                field_schema=field_schema,
            )

    def retrieve(
        self,
        ids: list[str],
        with_payload: bool = True,
        with_vectors: bool = False,
    ) -> list[models.Record]:
        """根据 ID 查询点

        Args:
            ids: 点 ID 列表
            with_payload: 是否返回 payload
            with_vectors: 是否返回向量

        Returns:
            Record 列表
        """
        return self._sdk_client.retrieve(
            collection_name=self._collection_name,
            ids=ids,
            with_payload=with_payload,
            with_vectors=with_vectors,
        )

    def upsert(
        self,
        points: list[models.PointStruct],
    ) -> None:
        """批量 Upsert 点

        Args:
            points: 点结构列表
        """
        self._sdk_client.upsert(
            collection_name=self._collection_name,
            points=points,
        )

    def delete(self, ids: list[str]) -> None:
        """删除点

        Args:
            ids: 点 ID 列表
        """
        self._sdk_client.delete(
            collection_name=self._collection_name,
            points_selector=models.PointIdsList(points=ids),
        )

    def set_payload(
        self,
        ids: list[str],
        payload: dict,
    ) -> None:
        """更新 Payload

        Args:
            ids: 点 ID 列表
            payload: 新 Payload
        """
        self._sdk_client.set_payload(
            collection_name=self._collection_name,
            points=ids,
            payload=payload,
        )

    def update_vectors(
        self,
        ids: list[str],
        vectors: list[list[float]],
    ) -> None:
        """更新向量

        Args:
            ids: 点 ID 列表
            vectors: 新向量列表
        """
        points = [
            models.PointVectors(id=id, vector=vector)
            for id, vector in zip(ids, vectors)
        ]
        self._sdk_client.update_vectors(
            collection_name=self._collection_name,
            points=points,
        )

    def query(
        self,
        query_vector: list[float],
        query_filter: Optional[models.Filter] = None,
        limit: int = 10,
        score_threshold: Optional[float] = None,
    ) -> models.QueryResponse:
        """向量查询

        Args:
            query_vector: 查询向量
            query_filter: 过滤条件
            limit: 返回数量
            score_threshold: 相似度阈值

        Returns:
            QueryResponse
        """
        return self._sdk_client.query_points(
            collection_name=self._collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )

    def scroll(
        self,
        limit: int = 100,
        offset: Optional[str] = None,
        query_filter: Optional[models.Filter] = None,
    ) -> tuple[list[models.Record], Optional[str]]:
        """遍历点

        Args:
            limit: 每次遍历数量
            offset: 偏移量
            query_filter: 过滤条件

        Returns:
            (Record 列表, 新偏移量)
        """
        return self._sdk_client.scroll(
            collection_name=self._collection_name,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
            scroll_filter=query_filter,
        )

    def count(
        self,
        query_filter: Optional[models.Filter] = None,
    ) -> int:
        """统计数量

        Args:
            query_filter: 过滤条件

        Returns:
            数量
        """
        result = self._sdk_client.count(
            collection_name=self._collection_name,
            count_filter=query_filter,
            exact=True,
        )
        return result.count

    def build_filter(
        self,
        company: Optional[str] = None,
        position: Optional[str] = None,
        question_type: Optional[str] = None,
        mastery_level: Optional[int] = None,
        cluster_ids: Optional[list[str]] = None,
    ) -> Optional[models.Filter]:
        """构建 Qdrant 过滤条件

        Args:
            company: 公司过滤
            position: 岗位过滤
            question_type: 题目类型过滤
            mastery_level: 熟练度过滤
            cluster_ids: 考点簇过滤

        Returns:
            Filter 对象
        """
        must_conditions = []

        if company:
            must_conditions.append(
                models.FieldCondition(
                    key="company",
                    match=models.MatchValue(value=company),
                )
            )
        if position:
            must_conditions.append(
                models.FieldCondition(
                    key="position",
                    match=models.MatchValue(value=position),
                )
            )
        if question_type:
            must_conditions.append(
                models.FieldCondition(
                    key="question_type",
                    match=models.MatchValue(value=question_type),
                )
            )
        if mastery_level is not None:
            must_conditions.append(
                models.FieldCondition(
                    key="mastery_level",
                    match=models.MatchValue(value=mastery_level),
                )
            )
        if cluster_ids:
            must_conditions.append(
                models.FieldCondition(
                    key="cluster_ids",
                    match=models.MatchAny(any=cluster_ids),
                )
            )

        return models.Filter(must=must_conditions) if must_conditions else None


# 单例获取函数
_qdrant_client: Optional[QdrantClient] = None


def get_qdrant_client() -> QdrantClient:
    """获取 Qdrant 客户端单例"""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient()
    return _qdrant_client


__all__ = [
    "QdrantClient",
    "get_qdrant_client",
]