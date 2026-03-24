"""Qdrant 向量数据库客户端模块

提供 Qdrant 的初始化、集合创建、Upsert 和 Hybrid Search 功能。
"""

from typing import Optional

from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance, PointStruct

from app.config.settings import get_settings
from app.models.schemas import QdrantQuestionPayload, SearchFilter, SearchResult
from app.utils.logger import logger
from app.utils.hasher import generate_question_id


class QdrantManager:
    """Qdrant 向量数据库管理器

    提供以下核心功能：
    - 集合初始化与索引创建
    - 批量 Upsert（插入或更新）
    - 混合检索（支持 Payload 预过滤）
    - 状态查询
    """

    def __init__(self) -> None:
        """初始化 Qdrant 管理器"""
        self.settings = get_settings()
        self._client: Optional[QdrantClient] = None

    @property
    def client(self) -> QdrantClient:
        """获取 Qdrant 客户端单例（延迟加载）"""
        if self._client is None:
            try:
                self._client = QdrantClient(url=self.settings.qdrant_url)
                logger.info(f"Qdrant client connected: {self.settings.qdrant_url}")
            except Exception as e:
                logger.error(f"Failed to connect to Qdrant: {e}")
                raise
        return self._client

    def create_collection_if_not_exists(
        self,
        vector_size: Optional[int] = None,
        force_recreate: bool = False,
    ) -> bool:
        """创建集合（如果不存在）

        Args:
            vector_size: 向量维度，默认使用配置中的值
            force_recreate: 是否强制重建集合（删除后重建）

        Returns:
            是否成功创建
        """
        vector_size = vector_size or self.settings.qdrant_vector_size
        collection_name = self.settings.qdrant_collection

        try:
            # 检查集合是否存在
            collections = self.client.get_collections().collections
            collection_exists = any(c.name == collection_name for c in collections)

            if collection_exists and force_recreate:
                logger.warning(f"Deleting existing collection: {collection_name}")
                self.client.delete_collection(collection_name=collection_name)
                collection_exists = False

            if not collection_exists:
                logger.info(f"Creating collection: {collection_name}")

                # 定义 Payload 索引（用于预过滤）
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=Distance.COSINE,
                    ),
                    # 创建 Payload 字段索引
                    # 1. keyword 类型索引（用于精确匹配）
                    # 2. integer 类型索引（用于范围查询和等值查询）
                )

                # 创建 Payload 索引
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name="company",
                    field_schema=models.KeywordIndexType.KEYWORD,
                )
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name="position",
                    field_schema=models.KeywordIndexType.KEYWORD,
                )
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name="question_type",
                    field_schema=models.KeywordIndexType.KEYWORD,
                )
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name="mastery_level",
                    field_schema=models.IntegerIndexType.INTEGER,
                )

                logger.info(
                    f"Collection '{collection_name}' created with payload indexes"
                )
                return True
            else:
                logger.info(f"Collection '{collection_name}' already exists")
                return False

        except Exception as e:
            logger.error(f"Failed to create collection: {e}")
            raise

    def upsert_questions(
        self,
        questions: list[QdrantQuestionPayload],
        vectors: list[list[float]],
    ) -> bool:
        """批量 Upsert 题目数据

        支持插入和更新。如果 question_id 已存在，则更新 Payload。

        Args:
            questions: 题目 Payload 列表
            vectors: 对应的向量嵌入列表（顺序必须与 questions 一致）

        Returns:
            是否成功

        Raises:
            ValueError: questions 和 vectors 长度不匹配
        """
        if not questions:
            logger.warning("No questions to upsert")
            return True

        if len(questions) != len(vectors):
            raise ValueError(
                f"Questions count ({len(questions)}) != vectors count ({len(vectors)})"
            )

        collection_name = self.settings.qdrant_collection

        try:
            # 确保集合存在
            self.create_collection_if_not_exists()

            # 构建 Point 结构
            points = [
                PointStruct(
                    id=p.question_id,  # 使用 question_id 作为主键
                    vector=vector,
                    payload=p.model_dump(exclude_none=True),
                )
                for p, vector in zip(questions, vectors)
            ]

            # 执行 Upsert
            self.client.upsert(
                collection_name=collection_name,
                points=points,
            )

            logger.info(f"Upserted {len(points)} questions to '{collection_name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to upsert questions: {e}")
            raise

    def upsert_question_with_context(
        self,
        question_text: str,
        company: str,
        position: str,
        vector: list[float],
        question_type: str = "knowledge",
        mastery_level: int = 0,
        core_entities: Optional[list[str]] = None,
        question_answer: Optional[str] = None,
    ) -> bool:
        """单条 Upsert（支持自动生成 question_id）

        这是一个便捷方法，内部会自动生成 question_id。

        Args:
            question_text: 题目文本
            company: 公司名称
            position: 岗位名称
            vector: 向量嵌入
            question_type: 题目类型
            mastery_level: 熟练度等级
            core_entities: 知识点实体列表
            question_answer: 生成的标准答案

        Returns:
            是否成功
        """
        question_id = generate_question_id(company, question_text)

        payload = QdrantQuestionPayload(
            question_id=question_id,
            question_text=question_text,
            company=company,
            position=position,
            mastery_level=mastery_level,
            question_type=question_type,
            core_entities=core_entities or [],
            question_answer=question_answer,
        )

        return self.upsert_questions(questions=[payload], vectors=[vector])

    def search(
        self,
        query_vector: list[float],
        filter_conditions: Optional[SearchFilter] = None,
        limit: int = 10,
        score_threshold: Optional[float] = None,
    ) -> list[SearchResult]:
        """向量检索

        支持基于 Payload 的预过滤（Pre-filtering）。

        Args:
            query_vector: 查询向量
            filter_conditions: 过滤条件
            limit: 返回结果数量
            score_threshold: 最低相似度阈值

        Returns:
            检索结果列表
        """
        collection_name = self.settings.qdrant_collection

        try:
            # 构建过滤条件
            must_conditions = []

            if filter_conditions:
                if filter_conditions.company:
                    must_conditions.append(
                        models.FieldCondition(
                            key="company",
                            match=models.MatchValue(value=filter_conditions.company),
                        )
                    )
                if filter_conditions.position:
                    must_conditions.append(
                        models.FieldCondition(
                            key="position",
                            match=models.MatchValue(value=filter_conditions.position),
                        )
                    )
                if filter_conditions.mastery_level is not None:
                    must_conditions.append(
                        models.FieldCondition(
                            key="mastery_level",
                            match=models.MatchValue(
                                value=filter_conditions.mastery_level
                            ),
                        )
                    )
                if filter_conditions.question_type:
                    must_conditions.append(
                        models.FieldCondition(
                            key="question_type",
                            match=models.MatchValue(
                                value=filter_conditions.question_type
                            ),
                        )
                    )

            # 构建查询请求
            query_filter = (
                models.Filter(must=must_conditions) if must_conditions else None
            )

            search_params = models.SearchParams(
                hnsw_ef=128,  # 优化检索精度
                exact=False,
            )

            results = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
                search_params=search_params,
            )

            # 转换结果
            search_results = []
            for r in results.points:
                payload = r.payload
                search_results.append(
                    SearchResult(
                        question_id=payload.get("question_id", ""),
                        question_text=payload.get("question_text", ""),
                        company=payload.get("company", ""),
                        position=payload.get("position", ""),
                        mastery_level=payload.get("mastery_level", 0),
                        question_type=payload.get("question_type", ""),
                        question_answer=payload.get("question_answer"),
                        score=r.score,
                    )
                )

            logger.info(f"Search returned {len(search_results)} results")
            return search_results

        except Exception as e:
            logger.error(f"Failed to search: {e}")
            raise

    def get_question(self, question_id: str) -> Optional[QdrantQuestionPayload]:
        """根据 ID 获取题目

        Args:
            question_id: 题目 ID

        Returns:
            题目数据，不存在则返回 None
        """
        collection_name = self.settings.qdrant_collection

        try:
            results = self.client.retrieve(
                collection_name=collection_name,
                ids=[question_id],
                with_payload=True,
            )

            if results:
                payload = results[0].payload
                return QdrantQuestionPayload(**payload)

            return None

        except Exception as e:
            logger.error(f"Failed to get question: {e}")
            raise

    def update_mastery_level(
        self,
        question_id: str,
        mastery_level: int,
    ) -> bool:
        """更新题目熟练度等级

        Args:
            question_id: 题目 ID
            mastery_level: 新的熟练度等级

        Returns:
            是否成功
        """
        collection_name = self.settings.qdrant_collection

        try:
            self.client.set_payload(
                collection_name=collection_name,
                points=[question_id],
                payload={"mastery_level": mastery_level},
            )

            logger.info(f"Updated mastery_level to {mastery_level} for {question_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update mastery_level: {e}")
            raise

    def update_answer(
        self,
        question_id: str,
        answer: str,
    ) -> bool:
        """更新题目答案

        Args:
            question_id: 题目 ID
            answer: 生成的标准答案

        Returns:
            是否成功
        """
        collection_name = self.settings.qdrant_collection

        try:
            self.client.set_payload(
                collection_name=collection_name,
                points=[question_id],
                payload={"question_answer": answer},
            )

            logger.info(f"Updated answer for {question_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update answer: {e}")
            raise

    def delete_collection(self) -> bool:
        """删除集合

        Returns:
            是否成功
        """
        collection_name = self.settings.qdrant_collection

        try:
            self.client.delete_collection(collection_name=collection_name)
            logger.info(f"Collection '{collection_name}' deleted")
            return True

        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            raise

    def get_collection_info(self) -> dict:
        """获取集合信息

        Returns:
            集合信息字典
        """
        collection_name = self.settings.qdrant_collection

        try:
            info = self.client.get_collection(collection_name=collection_name)
            return {
                "name": collection_name,
                "vectors_count": info.indexed_vectors_count,
                "points_count": info.points_count,
                "status": info.status.name if info.status else None,
            }
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            raise


# 全局单例
_qdrant_manager: Optional[QdrantManager] = None


def get_qdrant_manager() -> QdrantManager:
    """获取 Qdrant 管理器单例"""
    global _qdrant_manager
    if _qdrant_manager is None:
        _qdrant_manager = QdrantManager()
    return _qdrant_manager