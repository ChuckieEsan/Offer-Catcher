"""搜索题目工具

从向量数据库中搜索面试题。
"""

from langchain_core.tools import tool

from app.tools.embedding_tool import get_embedding_tool
from app.db.qdrant_client import get_qdrant_manager


@tool
def search_questions(query: str, company: str = None, position: str = None, k: int = 5) -> str:
    """搜索本地题库中的面试题（默认首选工具）

    从本地向量数据库检索面试题目，无需联网。
    应优先使用此工具进行题目检索。

    Args:
        query: 搜索关键词
        company: 公司名称（可选，用于精确筛选）
        position: 岗位名称（可选，用于精确筛选）
        k: 返回数量，默认 5

    Returns:
        搜索结果，以文本形式返回
    """
    # 将 query 转为向量
    embedding_tool = get_embedding_tool()
    query_vector = embedding_tool.embed_text(query)

    # 检索
    qdrant = get_qdrant_manager()
    results = qdrant.search(query_vector, limit=k)

    if company:
        results = [r for r in results if r.company == company]
    if position:
        results = [r for r in results if r.position == position]

    if not results:
        return "未找到相关题目"

    output = []
    for i, r in enumerate(results, 1):
        output.append(f"题目 {i}: {r.question_text[:100]}...")
        if r.question_answer:
            output.append(f"答案: {r.question_answer[:200]}...")
        output.append("---")

    return "\n".join(output)


__all__ = ["search_questions"]