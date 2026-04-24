"""题库领域仓库 Protocol 定义

使用 Python Protocol（结构化子类型）定义仓库接口。
Protocol 不需要显式继承，只需实现定义的方法即可被视为该类型。
添加 @runtime_checkable 支持 isinstance 检查（用于测试）。
"""

from typing import Protocol, runtime_checkable

from app.domain.question.aggregates import Cluster, ExtractTask, Question
from app.domain.shared.enums import MasteryLevel


@runtime_checkable
class QuestionRepository(Protocol):
    """题目仓库协议

    定义题目聚合的持久化接口。
    任何实现了这些方法的类，都会被类型检查器识别为 QuestionRepository。
    不需要显式继承此 Protocol。

    聚合边界：Question 是聚合根，所有操作通过此接口进行。
    """

    def find_by_id(self, question_id: str) -> Question | None:
        """根据 ID 查找题目

        Args:
            question_id: 题目唯一标识

        Returns:
            Question 实例或 None
        """
        ...

    def save(self, question: Question) -> None:
        """保存题目

        使用 Upsert 语义，幂等性保证。
        同一 question_id 的题目会被更新而非重复创建。

        Args:
            question: Question 实例
        """
        ...

    def delete(self, question_id: str) -> None:
        """删除题目

        Args:
            question_id: 题目唯一标识
        """
        ...

    def search(
        self,
        query_vector: list[float],
        filter_conditions: dict | None = None,
        limit: int = 10,
        score_threshold: float | None = None,
    ) -> list[tuple[Question, float]]:
        """向量检索题目

        混合检索：先 Payload 过滤，后向量计算。

        Args:
            query_vector: 查询向量
            filter_conditions: Payload 过滤条件
            limit: 返回数量限制
            score_threshold: 相似度阈值（0-1），只返回高于此阈值的结果

        Returns:
            [(Question, score)] 列表，按相似度降序排列
        """
        ...

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
        ...

    def find_all(self) -> list[Question]:
        """获取所有题目

        用于聚类等批量操作。

        Returns:
            所有 Question 列表
        """
        ...

    def count(self) -> int:
        """统计题目总数

        Returns:
            题目数量
        """
        ...

    def exists(self, question_id: str) -> bool:
        """检查题目是否存在

        Args:
            question_id: 题目唯一标识

        Returns:
            是否存在
        """
        ...

    def update_mastery(self, question_id: str, mastery_level: MasteryLevel) -> None:
        """更新题目熟练度等级

        Args:
            question_id: 题目唯一标识
            mastery_level: 新的熟练度等级
        """
        ...

    def update_answer(self, question_id: str, answer: str) -> None:
        """更新题目答案

        Args:
            question_id: 题目唯一标识
            answer: 标准答案
        """
        ...

    def update_with_reembedding(
        self,
        question_id: str,
        question_text: str,
        company: str,
        position: str,
    ) -> None:
        """更新题目并重新计算 embedding

        Args:
            question_id: 题目唯一标识
            question_text: 新题目文本
            company: 公司名称
            position: 岗位名称
        """
        ...


@runtime_checkable
class ClusterRepository(Protocol):
    """考点簇仓库协议

    定义考点簇聚合的持久化接口。
    """

    def find_by_id(self, cluster_id: str) -> Cluster | None:
        """根据 ID 查找考点簇

        Args:
            cluster_id: 考点簇唯一标识

        Returns:
            Cluster 实例或 None
        """
        ...

    def save(self, cluster: Cluster) -> None:
        """保存考点簇

        Args:
            cluster: Cluster 实例
        """
        ...

    def delete(self, cluster_id: str) -> None:
        """删除考点簇

        Args:
            cluster_id: 考点簇唯一标识
        """
        ...

    def find_all(self) -> list[Cluster]:
        """获取所有考点簇

        Returns:
            所有 Cluster 列表
        """
        ...

    def find_by_question_id(self, question_id: str) -> list[Cluster]:
        """查找包含指定题目的考点簇

        Args:
            question_id: 题目 ID

        Returns:
            包含该题目的 Cluster 列表
        """
        ...

    def count(self) -> int:
        """统计考点簇总数"""
        ...


@runtime_checkable
class ExtractTaskRepository(Protocol):
    """提取任务仓库协议

    定义提取任务聚合的持久化接口。
    """

    def create(
        self,
        user_id: str,
        source_type: str,
        source_content: str | None = None,
        source_images: list[str] | None = None,
    ) -> ExtractTask:
        """创建提取任务

        Args:
            user_id: 用户 ID
            source_type: 来源类型（text/image）
            source_content: 文本内容
            source_images: 图片列表

        Returns:
            新创建的 ExtractTask 聚合
        """
        ...

    def find_by_id(self, task_id: str) -> ExtractTask | None:
        """根据 ID 查找提取任务

        Args:
            task_id: 任务唯一标识

        Returns:
            ExtractTask 实例或 None
        """
        ...

    def find_by_user(
        self,
        user_id: str,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ExtractTask]:
        """查找用户的任务列表

        Args:
            user_id: 用户 ID
            status: 状态过滤
            limit: 返回数量
            offset: 偏移量

        Returns:
            ExtractTask 列表
        """
        ...

    def save(self, task: ExtractTask) -> None:
        """保存提取任务

        Args:
            task: ExtractTask 实例
        """
        ...

    def delete(self, task_id: str) -> None:
        """删除提取任务

        Args:
            task_id: 任务唯一标识
        """
        ...

    def update_status(self, task_id: str, status: str) -> None:
        """更新任务状态

        Args:
            task_id: 任务 ID
            status: 新状态
        """
        ...

    def update_result(
        self,
        task_id: str,
        result: dict,
    ) -> None:
        """更新任务结果

        Args:
            task_id: 任务 ID
            result: 提取结果（ExtractedInterview 字典）
        """
        ...

    def count_by_user(self, user_id: str, status: str | None = None) -> int:
        """统计用户任务数量

        Args:
            user_id: 用户 ID
            status: 状态过滤

        Returns:
            任务数量
        """
        ...

    def find_by_status(self, status: str) -> list[ExtractTask]:
        """根据状态查找提取任务

        Args:
            status: 任务状态

        Returns:
            匹配的 ExtractTask 列表
        """
        ...

    def find_pending_tasks(self, limit: int = 10) -> list[ExtractTask]:
        """查找待处理的任务

        Args:
            limit: 返回数量限制

        Returns:
            pending 状态的 ExtractTask 列表
        """
        ...

    def find_by_id_with_user(self, task_id: str, user_id: str) -> ExtractTask | None:
        """根据 ID 和用户 ID 查找提取任务

        Args:
            task_id: 任务唯一标识
            user_id: 用户 ID（用于验证归属）

        Returns:
            ExtractTask 实例或 None
        """
        ...

    def update_edit(
        self,
        task_id: str,
        user_id: str,
        company: str,
        position: str,
        questions: list[dict],
    ) -> ExtractTask | None:
        """编辑任务结果

        Args:
            task_id: 任务 ID
            user_id: 用户 ID
            company: 公司名称
            position: 岗位名称
            questions: 题目列表

        Returns:
            更新后的 ExtractTask 或 None
        """
        ...

    def delete_with_user(self, task_id: str, user_id: str) -> bool:
        """删除任务（带用户验证）

        Args:
            task_id: 任务唯一标识
            user_id: 用户 ID

        Returns:
            是否成功删除
        """
        ...


__all__ = [
    "QuestionRepository",
    "ClusterRepository",
    "ExtractTaskRepository",
    "GraphRepository",
]


@runtime_checkable
class GraphRepository(Protocol):
    """图数据库仓库协议

    定义考频关系、知识点关联等图数据的持久化接口。
    Neo4jClient 实现此 Protocol。

    核心功能：
    1. 考频关系写入（Company → Entity）
    2. 知识点关联查询（Entity 共现）
    3. 跨公司考点分析
    4. Cluster 节点管理
    """

    def create_company_node(self, company: str) -> bool:
        """创建公司节点

        Args:
            company: 公司名称

        Returns:
            是否成功
        """
        ...

    def create_entity_node(self, entity: str) -> bool:
        """创建考点实体节点

        Args:
            entity: 知识点名称

        Returns:
            是否成功
        """
        ...

    def create_exam_frequency_relationship(
        self,
        company: str,
        entity: str,
        question_count: int = 1,
    ) -> bool:
        """创建或更新考频关系

        Args:
            company: 公司名称
            entity: 知识点名称
            question_count: 题目数量（累加）

        Returns:
            是否成功
        """
        ...

    def record_question_entities(
        self,
        company: str,
        entities: list[str],
    ) -> bool:
        """记录题目的考点信息

        批量创建考频关系，每个 entity 增加 1 次。

        Args:
            company: 公司名称
            entities: 知识点列表

        Returns:
            是否成功
        """
        ...

    def get_top_entities(
        self,
        company: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """获取热门考点

        Args:
            company: 公司名称（可选，不传则返回全局热门）
            limit: 返回数量

        Returns:
            [{"entity": str, "count": int}] 列表
        """
        ...

    def get_company_stats(self, company: str) -> dict:
        """获取公司统计信息

        Args:
            company: 公司名称

        Returns:
            {"entity_count": int, "total_questions": int}
        """
        ...

    def get_related_entities(
        self,
        entity: str,
        limit: int = 5,
    ) -> list[dict]:
        """获取与给定知识点相关的其他知识点

        Args:
            entity: 知识点名称
            limit: 返回数量

        Returns:
            [{"related_entity": str, "co_occurrence_count": int}] 列表
        """
        ...

    def get_cross_company_entities(self, min_companies: int = 2) -> list[dict]:
        """获取跨多家公司考察的知识点

        Args:
            min_companies: 最少被多少家公司考察过

        Returns:
            [{"entity": str, "companies": list[str], "total_count": int}] 列表
        """
        ...

    def create_cluster_node(
        self,
        cluster_id: str,
        cluster_name: str,
        summary: str = "",
    ) -> bool:
        """创建考点簇节点

        Args:
            cluster_id: 簇 ID
            cluster_name: 簇名称
            summary: 簇摘要

        Returns:
            是否成功
        """
        ...

    def create_related_to_relationship(
        self,
        cluster_id: str,
        knowledge_point: str,
    ) -> bool:
        """创建簇与知识点的关联关系

        Args:
            cluster_id: 簇 ID
            knowledge_point: 知识点名称

        Returns:
            是否成功
        """
        ...

    def create_belongs_to_relationship(
        self,
        question_id: str,
        cluster_id: str,
    ) -> bool:
        """创建题目归属簇的关系

        Args:
            question_id: 题目 ID
            cluster_id: 簇 ID

        Returns:
            是否成功
        """
        ...

    def get_cluster_by_id(self, cluster_id: str) -> dict | None:
        """根据 ID 获取考点簇

        Args:
            cluster_id: 簇 ID

        Returns:
            簇信息字典或 None
        """
        ...

    def get_all_clusters(self, limit: int = 50) -> list[dict]:
        """获取所有考点簇

        Args:
            limit: 返回数量

        Returns:
            簇信息列表
        """
        ...

    def delete_companies(self, companies: list[str]) -> bool:
        """删除指定的公司节点及其关联关系

        Args:
            companies: 公司名称列表

        Returns:
            是否成功
        """
        ...