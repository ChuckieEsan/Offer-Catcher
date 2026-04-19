"""搜索题目 LangChain @tool

从向量数据库中搜索面试题。
采用两阶段检索架构：
1. 第一阶段：向量召回（多召回候选，不做精确过滤）
2. 第二阶段：Rerank 精排

使用 RetrievalApplicationService 提供检索能力。
"""

from langchain_core.tools import tool

from app.application.services.retrieval_service import get_retrieval_service
from app.application.services.cache_service import get_cache_service, CacheKeys
from app.infrastructure.common.logger import logger


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
    cache = get_cache_service()
    retrieval = get_retrieval_service()

    # 构建缓存 key
    query_hash = CacheKeys.hash_params(
        query, company=company, position=position, k=k
    )
    cache_key = CacheKeys.tool_search_questions(query_hash)

    def fetch():
        # 使用两阶段检索
        results = retrieval.search_with_rerank(
            query=query,
            company=company,
            position=position,
            k=k,
        )

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