"""聚类应用服务

使用 KMeans 算法进行题目聚类，支持自动选择最优簇数。
作为后台数据分析任务，放在 Application 层编排。
"""

from collections import Counter
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize

from app.domain.question.aggregates import Question, Cluster
from app.domain.question.repositories import QuestionRepository, ClusterRepository, GraphRepository

from app.infrastructure.persistence.qdrant.question_repository import (
    get_question_repository,
)
from app.infrastructure.persistence.neo4j import get_graph_client
from app.infrastructure.adapters.embedding_adapter import (
    EmbeddingAdapter,
    get_embedding_adapter,
)
from app.infrastructure.common.cache import singleton
from app.infrastructure.common.logger import logger


class ClusteringResult(BaseModel):
    """聚类结果"""

    total_questions: int = Field(description="题目总数")
    clustered_count: int = Field(description="被聚类的题目数量")
    cluster_count: int = Field(description="簇数量")
    silhouette_score: float = Field(description="轮廓系数")


class ClusteringApplicationService:
    """聚类应用服务

    使用 KMeans 进行题目聚类，支持自动选择最优簇数。
    作为后台数据分析任务，编排以下流程：
    1. 从 QuestionRepository 获取所有题目
    2. 使用 EmbeddingAdapter 计算向量
    3. 执行 KMeans 聚类
    4. 更新 Question 的 cluster_ids（存到 Qdrant）
    5. 创建 Neo4j Cluster 节点和关系（图数据库）

    注意：Cluster 只存储在 Neo4j，不存储在 Qdrant。
    Qdrant 用于向量检索，Cluster 不需要向量检索能力。
    """

    def __init__(
        self,
        question_repo: Optional[QuestionRepository] = None,
        graph_repo: Optional[GraphRepository] = None,
        embedding: Optional[EmbeddingAdapter] = None,
        min_cluster_size: int = 5,
        max_clusters: int = 30,
        auto_k: bool = True,
    ) -> None:
        """初始化聚类服务

        Args:
            question_repo: Question 仓库（支持依赖注入）
            graph_repo: Graph 仓库（支持依赖注入）
            embedding: Embedding 适配器（支持依赖注入）
            min_cluster_size: 最小簇大小
            max_clusters: 最大簇数量
            auto_k: 是否自动选择最优 K
        """
        self._question_repo = question_repo or get_question_repository()
        self._graph_repo = graph_repo or get_graph_client()
        self._embedding = embedding or get_embedding_adapter()
        self.min_cluster_size = min_cluster_size
        self.max_clusters = max_clusters
        self.auto_k = auto_k

    def _select_optimal_k(self, embeddings: list[list[float]]) -> int:
        """使用轮廓系数选择最优 K

        Args:
            embeddings: 嵌入向量列表

        Returns:
            最优簇数
        """
        n_samples = len(embeddings)

        # 根据数据量确定 K 的搜索范围
        max_k = min(self.max_clusters, n_samples // self.min_cluster_size)
        min_k = max(2, max_k // 4)  # 至少 2 个簇

        if max_k <= min_k:
            return min_k

        logger.info(f"Searching optimal K in range [{min_k}, {max_k}]...")

        best_k = min_k
        best_score = -1

        # 归一化向量（对 KMeans 很重要）
        normalized = normalize(embeddings)

        for k in range(min_k, max_k + 1):
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = kmeans.fit_predict(normalized)

            # 计算轮廓系数
            score = silhouette_score(normalized, labels, sample_size=min(1000, n_samples))

            logger.debug(f"K={k}, silhouette_score={score:.4f}")

            if score > best_score:
                best_score = score
                best_k = k

        logger.info(f"Selected optimal K={best_k} with silhouette_score={best_score:.4f}")
        return best_k

    def _extract_core_entities(self, questions: list[Question]) -> list[list[str]]:
        """提取题目列表的核心知识点

        Args:
            questions: 题目列表

        Returns:
            每个题目的核心知识点列表
        """
        return [q.core_entities or [] for q in questions]

    def _get_cluster_knowledge_points(
        self,
        cluster_indices: list[int],
        all_entities: list[list[str]],
    ) -> list[str]:
        """获取簇的核心知识点

        Args:
            cluster_indices: 属于该簇的题目索引列表
            all_entities: 所有题目的知识点列表

        Returns:
            核心知识点列表
        """
        cluster_entities = []
        for idx in cluster_indices:
            cluster_entities.extend(all_entities[idx])

        # 统计频率，取前 5 个
        counter = Counter(cluster_entities)
        return [item for item, _ in counter.most_common(5)]

    def _generate_cluster_id(self, knowledge_points: list[str]) -> str:
        """生成 cluster_id

        Args:
            knowledge_points: 核心知识点列表

        Returns:
            cluster_id
        """
        if not knowledge_points:
            return f"cluster_unknown_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # 取前 3 个知识点
        top_points = knowledge_points[:3]
        return "cluster_" + "_".join(top_points)

    def run_clustering(self, k: Optional[int] = None) -> ClusteringResult:
        """执行聚类

        Args:
            k: 预设簇数，如果为 None 则自动选择

        Returns:
            聚类结果
        """
        logger.info("Starting clustering...")

        # 1. 获取所有题目
        all_questions = self._question_repo.find_all()
        if not all_questions:
            logger.warning("No questions found for clustering")
            return ClusteringResult(
                total_questions=0,
                clustered_count=0,
                cluster_count=0,
                silhouette_score=0.0,
            )

        logger.info(f"Retrieved {len(all_questions)} questions")

        # 2. 生成 embedding
        texts = []
        for q in all_questions:
            entities = q.core_entities or []
            entities_str = ",".join(entities) if entities else "综合"
            texts.append(
                f"公司：{q.company} | "
                f"岗位：{q.position} | "
                f"类型：{q.question_type.value} | "
                f"考点：{entities_str} | "
                f"题目：{q.question_text}"
            )

        logger.info("Generating embeddings...")
        embeddings = self._embedding.embed_batch(texts)

        # 3. 归一化向量
        normalized_embeddings = normalize(embeddings)

        # 4. 确定 K 值
        if k is not None:
            n_clusters = k
            logger.info(f"Using preset K={n_clusters}")
        elif self.auto_k:
            n_clusters = self._select_optimal_k(embeddings)
        else:
            n_clusters = max(2, len(all_questions) // self.min_cluster_size)
            logger.info(f"Using calculated K={n_clusters}")

        # 5. KMeans 聚类
        logger.info(f"Running KMeans clustering with K={n_clusters}...")
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        cluster_labels = kmeans.fit_predict(normalized_embeddings)

        # 6. 计算轮廓系数
        sil_score = silhouette_score(
            normalized_embeddings,
            cluster_labels,
            sample_size=min(1000, len(embeddings)),
        )
        logger.info(f"Silhouette score: {sil_score:.4f}")

        # 7. 为每个簇分配 cluster_id 并更新
        all_entities = self._extract_core_entities(all_questions)

        # 按簇号分组
        cluster_to_indices: dict[int, list[int]] = {}
        for idx, label in enumerate(cluster_labels):
            if label not in cluster_to_indices:
                cluster_to_indices[label] = []
            cluster_to_indices[label].append(idx)

        # 为每个簇生成 cluster_id
        cluster_id_map: dict[int, str] = {}
        for label, cluster_indices in cluster_to_indices.items():
            # 获取核心知识点
            knowledge_points = self._get_cluster_knowledge_points(
                cluster_indices, all_entities
            )

            # 生成 cluster_id
            cluster_id = self._generate_cluster_id(knowledge_points)
            cluster_id_map[label] = cluster_id

            logger.info(
                f"Cluster {label}: {len(cluster_indices)} questions, "
                f"knowledge_points: {knowledge_points}"
            )

            # 8. 创建 Neo4j Cluster 节点（Cluster 只存图数据库，不存 Qdrant）
            self._graph_repo.create_cluster_node(
                cluster_id=cluster_id,
                cluster_name=knowledge_points[0] if knowledge_points else "未命名",
                summary=f"包含 {len(cluster_indices)} 道题目",
            )

            # 创建簇与知识点的关联关系
            for kp in knowledge_points:
                self._graph_repo.create_related_to_relationship(
                    cluster_id=cluster_id,
                    knowledge_point=kp,
                )

        # 9. 更新题目的 cluster_ids
        clustered_count = 0
        for idx, label in enumerate(cluster_labels):
            question = all_questions[idx]
            cluster_id = cluster_id_map[label]

            # 添加 cluster_id 到题目
            question.add_cluster(cluster_id)

            # 保存更新后的题目
            self._question_repo.save(question)
            clustered_count += 1

            # 创建题目归属 Neo4j 关系
            self._graph_repo.create_belongs_to_relationship(
                question_id=question.question_id,
                cluster_id=cluster_id,
            )

        logger.info(
            f"Clustering complete: {n_clusters} clusters, "
            f"{clustered_count} questions updated"
        )

        return ClusteringResult(
            total_questions=len(all_questions),
            clustered_count=clustered_count,
            cluster_count=n_clusters,
            silhouette_score=sil_score,
        )


@singleton
def get_clustering_service(
    min_cluster_size: int = 5,
    max_clusters: int = 30,
    auto_k: bool = True,
) -> ClusteringApplicationService:
    """获取聚类服务单例

    Note: 参数在首次调用后会被忽略。

    Args:
        min_cluster_size: 最小簇大小
        max_clusters: 最大簇数量
        auto_k: 是否自动选择最优 K

    Returns:
        ClusteringApplicationService 实例
    """
    return ClusteringApplicationService(
        min_cluster_size=min_cluster_size,
        max_clusters=max_clusters,
        auto_k=auto_k,
    )


__all__ = [
    "ClusteringApplicationService",
    "ClusteringResult",
    "get_clustering_service",
]