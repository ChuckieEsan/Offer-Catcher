"""搜索题目 LangChain @tool

从向量数据库中搜索面试题。
采用两阶段检索架构：
1. 第一阶段：向量召回（多召回候选，不做精确过滤）
2. 第二阶段：Rerank 精排

作为 Infrastructure 层组件，直接调用其他 Infrastructure Adapter。
"""

from langchain_core.tools import tool

from app.infrastructure.common.logger import logger
from app.infrastructure.common.cache_keys import CacheKeys


@tool
def search_questions(
    query: str,
    company: str = None,
    position: str = None,
    k: int = 5,
) -> str:
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
    # Lazy imports 避免 circular import
    from app.infrastructure.adapters.embedding_adapter import get_embedding_adapter
    from app.infrastructure.persistence.qdrant.question_repository import get_question_repository
    from app.infrastructure.adapters.reranker_adapter import get_reranker_adapter
    from app.application.services.cache_service import get_cache_service

    embedding = get_embedding_adapter()
    repo = get_question_repository()
    reranker = get_reranker_adapter()
    cache = get_cache_service()

    # 构建缓存 key
    query_hash = CacheKeys.hash_params(query, company=company, position=position, k=k)
    cache_key = CacheKeys.tool_search_questions(query_hash)

    def fetch():
        # 构建上下文（与入库格式一致，保证语义对齐）
        context = f"公司：{company or '综合'} | 岗位：{position or '综合'} | 题目：{query}"
        query_vector = embedding.embed(context)

        # Stage 1: 向量召回（多候选）
        recall_limit = k * 3
        search_results = repo.search(query_vector, limit=recall_limit)

        if not search_results:
            logger.info(f"Search: no candidates found for '{query}'")
            return []

        # 提取 Question（丢弃向量 score，后续用 rerank score）
        candidates = [question for question, _ in search_results]

        # Stage 2: Rerank 精排
        candidate_texts = [q.question_text for q in candidates]
        ranked_indices = reranker.rerank(query, candidate_texts, top_k=k)

        # 格式化输出
        output = []
        for idx, rerank_score in ranked_indices:
            question = candidates[idx]
            output.append(f"题目 {len(output)//4 + 1}: {question.question_text[:100]}...")
            if question.answer:
                output.append(f"答案: {question.answer[:200]}...")
            output.append(f"公司: {question.company} | 岗位: {question.position}")
            output.append("---")

        logger.info(
            f"Search completed: query='{query}', "
            f"recall={len(candidates)}, rerank_top={len(ranked_indices)}"
        )
        return output

    # 使用缓存服务（带分布式锁防击穿）
    output_lines = cache.get_with_lock(cache_key, fetch, ttl=300)

    if not output_lines:
        return "未找到相关题目"

    return "\n".join(output_lines)


__all__ = ["search_questions"]