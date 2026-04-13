"""搜索题目工具

从向量数据库中搜索面试题。
采用两阶段检索架构：
1. 第一阶段：向量召回（多召回候选，不做精确过滤）
2. 第二阶段：Rerank 精排
"""

import time

from langchain_core.tools import tool

from app.tools.embedding_tool import get_embedding_tool
from app.tools.reranker_tool import get_reranker_tool
from app.db.qdrant_client import get_qdrant_manager
from app.models import SearchResult
from app.services.cache_service import get_cache_service, CacheKeys
from app.utils.telemetry import traced, record_vector_query
from app.utils.logger import logger


def _build_query_context(query: str, company: str = None, position: str = None) -> str:
    """构建与入库一致的查询上下文

    入库时的格式："公司：xxx | 岗位：xxx | 类型：xxx | 考点：xxx | 题目：xxx"
    检索时使用相同格式以保证语义对齐。

    Args:
        query: 查询关键词
        company: 公司名称（可选）
        position: 岗位名称（可选）

    Returns:
        拼接后的上下文文本
    """
    parts = []
    parts.append(f"公司：{company or '综合'}")
    parts.append(f"岗位：{position or '综合'}")
    parts.append(f"题目：{query}")
    return " | ".join(parts)


def _do_search(query: str, company: str, position: str, k: int) -> list[SearchResult]:
    """执行实际的搜索逻辑（内部函数）

    Args:
        query: 搜索关键词
        company: 公司名称
        position: 岗位名称
        k: 返回数量

    Returns:
        搜索结果列表
    """
    embedding_tool = get_embedding_tool()
    reranker_tool = get_reranker_tool()
    qdrant = get_qdrant_manager()

    # Stage 1: 构建与入库一致的上下文并做向量召回
    context = _build_query_context(query, company, position)
    query_vector = embedding_tool.embed_text(context)

    # 多召回候选（k * 3），不做精确过滤
    recall_limit = k * 3
    start_time = time.perf_counter()
    candidates = qdrant.search(query_vector, limit=recall_limit)

    # 记录向量查询指标
    duration_ms = (time.perf_counter() - start_time) * 1000
    record_vector_query(duration_ms=duration_ms, results_count=len(candidates))

    if not candidates:
        return []

    # Stage 2: Rerank 精排
    candidate_texts = [c.question_text for c in candidates]
    ranked_indices = reranker_tool.rerank(query, candidate_texts, top_k=k)

    # 根据重排结果重组 SearchResult
    ranked_results: list[SearchResult] = []
    for idx, rerank_score in ranked_indices:
        result = candidates[idx]
        ranked_results.append(result)

    logger.info(
        f"Search completed: query='{query}', "
        f"recall={len(candidates)}, rerank_top={len(ranked_results)}"
    )

    return ranked_results


@tool
@traced
def search_questions(query: str, company: str = None, position: str = None, k: int = 5) -> str:
    """搜索本地题库中的面试题（默认首选工具）

    从本地向量数据库检索面试题目，无需联网。
    采用两阶段检索：向量召回 + Rerank 精排。
    结果会被缓存 5 分钟，提升响应速度。

    Args:
        query: 搜索关键词
        company: 公司名称（可选，用于语义增强）
        position: 岗位名称（可选，用于语义增强）
        k: 返回数量，默认 5

    Returns:
        搜索结果，以文本形式返回
    """
    cache = get_cache_service()

    # 构建缓存 key
    query_hash = CacheKeys.hash_params(query, company=company, position=position, k=k)
    cache_key = CacheKeys.tool_search_questions(query_hash)

    def fetch():
        results = _do_search(query, company, position, k)
        if not results:
            return []

        # 格式化输出
        output = []
        for i, r in enumerate(results, 1):
            output.append(f"题目 {i}: {r.question_text[:100]}...")
            if r.question_answer:
                output.append(f"答案: {r.question_answer[:200]}...")
            output.append(f"公司: {r.company} | 岗位: {r.position}")
            output.append("---")
        return output

    # 使用缓存服务（带分布式锁防击穿）
    output_lines = cache.get_with_lock(cache_key, fetch, ttl=300)

    if not output_lines:
        return "未找到相关题目"

    return "\n".join(output_lines)


__all__ = ["search_questions"]