"""Question 仓库的 Qdrant 实现

实现 QuestionRepository Protocol，基于 Qdrant 向量数据库持久化 Question 聚合。
"""

from typing import Optional

from qdrant_client import models
from qdrant_client.models import PointStruct

from app.domain.question.aggregates import Question
from app.domain.question.repositories import QuestionRepository
from app.domain.shared.enums import MasteryLevel, QuestionType

from app.infrastructure.persistence.qdrant.client import (
    QdrantClient,
    get_qdrant_client,
)
from app.infrastructure.adapters.embedding_adapter import (
    EmbeddingAdapter,
    get_embedding_adapter,
)
from app.infrastructure.common.logger import logger


class QdrantQuestionRepository:
    """Question 仓库的 Qdrant 实现

    实现 QuestionRepository Protocol 的所有方法。
    使用 Qdrant 向量数据库进行持久化，支持向量检索。

    注意：不需要显式继承 QuestionRepository Protocol，
    只需实现 Protocol 定义的方法即可被视为该类型。
    """

    def __init__(
        self,
        client: Optional[QdrantClient] = None,
        embedding: Optional[EmbeddingAdapter] = None,
    ) -> None:
        """初始化仓库

        Args:
            client: Qdrant 客户端（支持依赖注入）
            embedding: Embedding 适配器（支持依赖注入）
        """
        self._client = client or get_qdrant_client()
        self._embedding = embedding or get_embedding_adapter()

        # 确保集合存在
        self._client.ensure_collection_exists()

    def find_by_id(self, question_id: str) -> Question | None:
        """根据 ID 查找题目

        Args:
            question_id: 题目唯一标识

        Returns:
            Question 实例或 None
        """
        try:
            results = self._client.retrieve(ids=[question_id])
            if results:
                payload = results[0].payload
                if payload:
                    return Question.from_payload(payload)
            return None
        except Exception as e:
            logger.error(f"Failed to find question {question_id}: {e}")
            raise

    def save(self, question: Question) -> None:
        """保存题目（Upsert 语义）

        Args:
            question: Question 实例
        """
        try:
            # 计算 embedding
            context = question.to_context()
            vector = self._embedding.embed(context)

            # 构建 Point 结构
            point = PointStruct(
                id=question.question_id,
                vector=vector,
                payload=question.to_payload(),
            )

            # Upsert
            self._client.upsert(points=[point])
            logger.info(f"Saved question: {question.question_id}")

        except Exception as e:
            logger.error(f"Failed to save question {question.question_id}: {e}")
            raise

    def delete(self, question_id: str) -> None:
        """删除题目

        Args:
            question_id: 题目唯一标识
        """
        try:
            self._client.delete(ids=[question_id])
            logger.info(f"Deleted question: {question_id}")
        except Exception as e:
            logger.error(f"Failed to delete question {question_id}: {e}")
            raise

    def search(
        self,
        query_vector: list[float],
        filter_conditions: dict | None = None,
        limit: int = 10,
        score_threshold: Optional[float] = None,
    ) -> list[Question]:
        """向量检索题目

        Args:
            query_vector: 查询向量
            filter_conditions: Payload 过滤条件
            limit: 返回数量限制
            score_threshold: 相似度阈值（0-1），只返回高于此阈值的结果

        Returns:
            匹配的 Question 列表
        """
        try:
            # 构建过滤条件
            query_filter = self._build_filter_from_dict(filter_conditions)

            # 执行查询
            response = self._client.query(
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit,
                score_threshold=score_threshold,
            )

            # 转换结果
            questions = []
            for point in response.points:
                if point.payload:
                    questions.append(Question.from_payload(point.payload))

            logger.info(f"Search returned {len(questions)} results")
            return questions

        except Exception as e:
            logger.error(f"Failed to search: {e}")
            raise

    def find_by_company_and_position(
        self,
        company: str,
        position: str,
        limit: int = 100,
    ) -> list[Question]:
        """根据公司和岗位查找题目

        Args:
            company: 公司名称
            position: 岗位名称
            limit: 返回数量限制

        Returns:
            匹配的 Question 列表
        """
        try:
            query_filter = self._client.build_filter(
                company=company,
                position=position,
            )

            all_questions = []
            offset = None
            batch_size = 100

            while len(all_questions) < limit:
                results, offset = self._client.scroll(
                    limit=min(batch_size, limit - len(all_questions)),
                    offset=offset,
                    query_filter=query_filter,
                )

                for point in results:
                    if point.payload:
                        try:
                            question = Question.from_payload(point.payload)
                            all_questions.append(question)
                        except Exception as e:
                            logger.warning(f"Failed to parse question {point.id}: {e}")

                if offset is None:
                    break

            logger.info(
                f"Found {len(all_questions)} questions for company={company}, position={position}"
            )
            return all_questions[:limit]

        except Exception as e:
            logger.error(f"Failed to find by company/position: {e}")
            raise

    def find_all(self) -> list[Question]:
        """获取所有题目

        Returns:
            所有 Question 列表
        """
        try:
            all_questions = []
            offset = None
            batch_size = 1000

            while True:
                results, offset = self._client.scroll(
                    limit=batch_size,
                    offset=offset,
                )

                for point in results:
                    if point.payload:
                        try:
                            question = Question.from_payload(point.payload)
                            all_questions.append(question)
                        except Exception as e:
                            logger.warning(f"Failed to parse question {point.id}: {e}")

                if offset is None:
                    break

            logger.info(f"Found all questions, total: {len(all_questions)}")
            return all_questions

        except Exception as e:
            logger.error(f"Failed to find all: {e}")
            raise

    def count(self) -> int:
        """统计题目总数

        Returns:
            题目数量
        """
        try:
            return self._client.count()
        except Exception as e:
            logger.error(f"Failed to count: {e}")
            raise

    def exists(self, question_id: str) -> bool:
        """检查题目是否存在

        Args:
            question_id: 题目唯一标识

        Returns:
            是否存在
        """
        return self.find_by_id(question_id) is not None

    def update_answer(self, question_id: str, answer: str) -> None:
        """更新题目答案

        Args:
            question_id: 题目 ID
            answer: 答案内容
        """
        try:
            self._client.set_payload(
                ids=[question_id],
                payload={"answer": answer},
            )
            logger.info(f"Updated answer for question: {question_id}")
        except Exception as e:
            logger.error(f"Failed to update answer: {e}")
            raise

    def update_mastery(self, question_id: str, mastery_level: MasteryLevel) -> None:
        """更新熟练度等级

        Args:
            question_id: 题目 ID
            mastery_level: 新熟练度等级
        """
        try:
            self._client.set_payload(
                ids=[question_id],
                payload={"mastery_level": mastery_level.value},
            )
            logger.info(f"Updated mastery for question: {question_id}")
        except Exception as e:
            logger.error(f"Failed to update mastery: {e}")
            raise

    def update_with_reembedding(
        self,
        question: Question,
        new_text: str,
    ) -> None:
        """更新题目文本并重新计算向量

        Args:
            question: 原题目（用于获取上下文信息）
            new_text: 新题目文本
        """
        try:
            # 构建新上下文
            context = f"公司：{question.company} | 岗位：{question.position} | 题目：{new_text}"
            new_vector = self._embedding.embed(context)

            # 更新向量
            self._client.update_vectors(
                ids=[question.question_id],
                vectors=[new_vector],
            )

            # 更新文本 payload
            self._client.set_payload(
                ids=[question.question_id],
                payload={"question_text": new_text},
            )

            logger.info(f"Updated question with reembedding: {question.question_id}")

        except Exception as e:
            logger.error(f"Failed to update with reembedding: {e}")
            raise

    def _build_filter_from_dict(
        self,
        filter_conditions: dict | None,
    ) -> Optional[models.Filter]:
        """从字典构建 Qdrant 过滤条件

        Args:
            filter_conditions: 过滤条件字典

        Returns:
            Filter 对象
        """
        if not filter_conditions:
            return None

        return self._client.build_filter(
            company=filter_conditions.get("company"),
            position=filter_conditions.get("position"),
            question_type=filter_conditions.get("question_type"),
            mastery_level=filter_conditions.get("mastery_level"),
            cluster_ids=filter_conditions.get("cluster_ids"),
        )


# 单例获取函数
_question_repository: Optional[QdrantQuestionRepository] = None


def get_question_repository() -> QdrantQuestionRepository:
    """获取 Question 仓库单例"""
    global _question_repository
    if _question_repository is None:
        _question_repository = QdrantQuestionRepository()
    return _question_repository


__all__ = [
    "QdrantQuestionRepository",
    "get_question_repository",
]