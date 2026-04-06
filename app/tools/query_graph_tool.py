"""图数据库查询工具

查询图数据库，获取知识点之间的关系。
"""

from langchain_core.tools import tool

from app.db.graph_client import get_graph_client
from app.utils.logger import logger


@tool
def query_graph(question: str) -> str:
    """查询图数据库，获取知识点之间的关系

    Args:
        question: 查询问题

    Returns:
        查询结果
    """
    try:
        graph_client = get_graph_client()

        # 提取关键词
        keywords = question.replace("关系", "").replace("?", "").replace("知识", "").split()

        # 如果有关键词，查询相关知识点
        if keywords and keywords[0]:
            keyword = keywords[0]
            # 使用 get_related_entities 获取相关知识点
            related = graph_client.get_related_entities(keyword, limit=5)

            if not related:
                # 如果没有相关知识点，尝试获取热门考点
                top_entities = graph_client.get_top_entities(limit=5)
                if not top_entities:
                    return "图数据库中暂无知识点数据"

                output = ["热门考点:"]
                for e in top_entities:
                    output.append(f"- {e.get('entity', e)}")
                return "\n".join(output)

            output = [f"与 '{keyword}' 相关的知识点:"]
            for e in related:
                output.append(f"- {e.get('related_entity', e.get('entity', e))}")
                count = e.get('co_occurrence_count', '')
                if count:
                    output.append(f"  共现次数: {count}")
            return "\n".join(output)
        else:
            # 没有关键词时，返回热门考点
            top_entities = graph_client.get_top_entities(limit=10)
            if not top_entities:
                return "图数据库中暂无知识点数据"

            output = ["热门考点 Top 10:"]
            for i, e in enumerate(top_entities, 1):
                entity = e.get('entity', e)
                count = e.get('count', '')
                output.append(f"{i}. {entity}" + (f" (考察次数: {count})" if count else ""))
            return "\n".join(output)

    except Exception as e:
        logger.error(f"Graph query failed: {e}")
        return f"图数据库查询失败: {e}"


__all__ = ["query_graph"]