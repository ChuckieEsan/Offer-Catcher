"""聚类服务模块

使用 KMeans 算法进行题目聚类，支持自动选择最优簇数。
"""

from typing import Optional
from collections import Counter
from datetime import datetime

from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize

from app.db.qdrant_client import get_qdrant_manager
from app.db.graph_client import get_graph_client
from app.tools.embedding import get_embedding_tool
from app.models.schemas import QdrantQuestionPayload, Cluster
from app.utils.logger import logger


class ClusteringResult:
    """聚类结果"""

    def __init__(
        self,
        total_questions: int,
        clustered_count: int,
        cluster_count: int,
        silhouette_score: float,
    ):
        self.total_questions = total_questions
        self.clustered_count = clustered_count
        self.cluster_count = cluster_count
        self.silhouette_score = silhouette_score


class ClusteringService:
    """聚类服务

    使用 KMeans 进行题目聚类，支持自动选择最优簇数。
    """

    def __init__(
        self,
        min_cluster_size: int = 5,
        max_clusters: int = 30,
        auto_k: bool = True,
    ):
        """初始化聚类服务

        Args:
            min_cluster_size: 最小簇大小
            max_clusters: 最大簇数量
            auto_k: 是否自动选择最优 K
        """
        self.min_cluster_size = min_cluster_size
        self.max_clusters = max_clusters
        self.auto_k = auto_k
        self.embedding_tool = get_embedding_tool()
        self.qdrant_manager = get_qdrant_manager()
        self.graph_client = get_graph_client()

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

    def _extract_core_entities(self, questions: list[QdrantQuestionPayload]) -> list[list[str]]:
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
        all_questions = self.qdrant_manager.scroll_all()
        if not all_questions:
            logger.warning("No questions found for clustering")
            return ClusteringResult(0, 0, 0, 0.0)

        logger.info(f"Retrieved {len(all_questions)} questions")

        # 2. 生成 embedding
        texts = []
        for q in all_questions:
            entities = q.core_entities or []
            entities_str = ",".join(entities) if entities else "综合"
            texts.append(f"考点标签：{entities_str} | 题目：{q.question_text}")

        logger.info("Generating embeddings...")
        embeddings = self.embedding_tool.embed_texts(texts)

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
        sil_score = silhouette_score(normalized_embeddings, cluster_labels, sample_size=min(1000, len(embeddings)))
        logger.info(f"Silhouette score: {sil_score:.4f}")

        # 7. 为每个簇分配 cluster_id 并更新
        all_entities = self._extract_core_entities(all_questions)
        cluster_ids_map: dict[str, list[str]] = {}

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

            # 创建 Neo4j Cluster 节点
            self.graph_client.create_cluster_node(
                cluster_id=cluster_id,
                cluster_name=knowledge_points[0] if knowledge_points else "未命名",
                summary=f"包含 {len(cluster_indices)} 道题目",
            )

            # 创建簇与知识点的关联关系
            for kp in knowledge_points:
                self.graph_client.create_related_to_relationship(
                    cluster_id=cluster_id,
                    knowledge_point=kp,
                )

        # 8. 构建 cluster_ids 映射
        for idx, label in enumerate(cluster_labels):
            question_id = all_questions[idx].question_id
            cluster_id = cluster_id_map[label]

            if question_id in cluster_ids_map:
                if cluster_id not in cluster_ids_map[question_id]:
                    cluster_ids_map[question_id].append(cluster_id)
            else:
                cluster_ids_map[question_id] = [cluster_id]

        # 9. 批量更新 Qdrant
        if cluster_ids_map:
            self.qdrant_manager.batch_update_cluster_ids(cluster_ids_map)

        # 10. 为题目创建 Neo4j 归属关系
        for question_id, cluster_ids in cluster_ids_map.items():
            for cluster_id in cluster_ids:
                self.graph_client.create_belongs_to_relationship(
                    question_id=question_id,
                    cluster_id=cluster_id,
                )

        logger.info(f"Clustering complete: {n_clusters} clusters, {len(cluster_ids_map)} questions")

        return ClusteringResult(
            total_questions=len(all_questions),
            clustered_count=len(cluster_ids_map),
            cluster_count=n_clusters,
            silhouette_score=sil_score,
        )


# 全局单例
_clustering_service: Optional[ClusteringService] = None


def get_clustering_service(
    min_cluster_size: int = 5,
    max_clusters: int = 30,
    auto_k: bool = True,
) -> ClusteringService:
    """获取聚类服务单例

    Args:
        min_cluster_size: 最小簇大小
        max_clusters: 最大簇数量
        auto_k: 是否自动选择最优 K

    Returns:
        ClusteringService 实例
    """
    global _clustering_service
    if _clustering_service is None:
        _clustering_service = ClusteringService(
            min_cluster_size=min_cluster_size,
            max_clusters=max_clusters,
            auto_k=auto_k,
        )
    return _clustering_service