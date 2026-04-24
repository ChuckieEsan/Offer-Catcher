"""Redis Key 命名规则

纯技术实现，无业务逻辑。
作为基础设施层组件，供 Infrastructure Tools 和 Application Services 使用。
"""

import hashlib
from typing import Optional


class CacheKeys:
    """Redis Key 管理器

    定义缓存 key 的命名规则。
    纯技术实现，放在 Infrastructure 层。
    """

    PREFIX = "oc"

    # ========== Stats Keys ==========

    @classmethod
    def stats_overview(cls) -> str:
        return f"{cls.PREFIX}:stats:overview"

    @classmethod
    def stats_clusters(cls) -> str:
        return f"{cls.PREFIX}:stats:clusters"

    @classmethod
    def stats_companies(cls) -> str:
        return f"{cls.PREFIX}:stats:companies"

    @classmethod
    def stats_entities(cls, company: Optional[str] = None, limit: int = 20) -> str:
        """考点统计缓存 key"""
        company_key = company or "all"
        return f"{cls.PREFIX}:stats:entities:{company_key}:{limit}"

    @classmethod
    def stats_positions(cls) -> str:
        """岗位统计缓存 key"""
        return f"{cls.PREFIX}:stats:positions"

    @classmethod
    def stats_entities_pattern(cls) -> str:
        return f"{cls.PREFIX}:stats:entities:*"

    # ========== Questions Keys ==========

    @classmethod
    def questions_list(cls, filter_hash: str) -> str:
        return f"{cls.PREFIX}:questions:list:{filter_hash}"

    @classmethod
    def questions_count(cls, filter_hash: str) -> str:
        return f"{cls.PREFIX}:questions:count:{filter_hash}"

    @classmethod
    def questions_item(cls, question_id: str) -> str:
        return f"{cls.PREFIX}:questions:item:{question_id}"

    @classmethod
    def questions_list_pattern(cls) -> str:
        return f"{cls.PREFIX}:questions:list:*"

    @classmethod
    def questions_count_pattern(cls) -> str:
        return f"{cls.PREFIX}:questions:count:*"

    @classmethod
    def stats_pattern(cls) -> str:
        return f"{cls.PREFIX}:stats:*"

    # ========== Tool Cache Keys ==========

    @classmethod
    def tool_search_questions(cls, query_hash: str) -> str:
        """题目搜索工具缓存 key"""
        return f"{cls.PREFIX}:tool:search:{query_hash}"

    @classmethod
    def tool_query_graph(cls, query_hash: str) -> str:
        """图数据库查询工具缓存 key"""
        return f"{cls.PREFIX}:tool:graph:{query_hash}"

    @classmethod
    def tool_web_search(cls, query_hash: str) -> str:
        """Web 搜索工具缓存 key"""
        return f"{cls.PREFIX}:tool:web:{query_hash}"

    @classmethod
    def tool_company_topics(cls, company: str) -> str:
        """公司热门考点工具缓存 key"""
        return f"{cls.PREFIX}:tool:company_topics:{company}"

    @classmethod
    def tool_knowledge_relations(cls, entity: str) -> str:
        """知识点关联工具缓存 key"""
        return f"{cls.PREFIX}:tool:knowledge_relations:{entity}"

    @classmethod
    def tool_cross_company_trends(cls, min_companies: int) -> str:
        """跨公司考点趋势工具缓存 key"""
        return f"{cls.PREFIX}:tool:cross_company_trends:{min_companies}"

    @classmethod
    def tool_search_pattern(cls) -> str:
        return f"{cls.PREFIX}:tool:search:*"

    @classmethod
    def tool_graph_pattern(cls) -> str:
        return f"{cls.PREFIX}:tool:graph:*"

    @classmethod
    def tool_web_pattern(cls) -> str:
        return f"{cls.PREFIX}:tool:web:*"

    # ========== Utility Methods ==========

    @classmethod
    def hash_params(cls, *args, **kwargs) -> str:
        """生成参数哈希值

        Args:
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            8 字符哈希值
        """
        parts = [str(arg) for arg in args if arg is not None]
        if kwargs:
            sorted_items = sorted((k, v) for k, v in kwargs.items() if v is not None)
            parts.extend(f"{k}={v}" for k, v in sorted_items)

        if not parts:
            return "empty"

        content = ":".join(parts)
        return hashlib.md5(content.encode()).hexdigest()[:8]


__all__ = ["CacheKeys"]