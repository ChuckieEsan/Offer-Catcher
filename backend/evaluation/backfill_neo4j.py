"""Neo4j 历史数据补全脚本

从 Qdrant 题库导入已有的考频数据到 Neo4j。

运行方式：
    cd backend
    uv run python -m evaluation.backfill_neo4j
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.infrastructure.persistence.qdrant.question_repository import get_question_repository
from app.infrastructure.persistence.neo4j import get_graph_client
from app.infrastructure.common.logger import logger


def backfill_neo4j():
    """从 Qdrant 补全 Neo4j 考频数据"""

    repo = get_question_repository()
    graph = get_graph_client()

    # 获取所有题目
    all_questions = repo.find_all()
    total = len(all_questions)
    logger.info(f"从 Qdrant 获取到 {total} 条题目")

    # 统计
    success_count = 0
    skip_count = 0

    for i, q in enumerate(all_questions, 1):
        if q.core_entities:
            try:
                graph.record_question_entities(
                    company=q.company,
                    entities=q.core_entities,
                )
                success_count += 1
                logger.debug(f"[{i}/{total}] 写入: {q.company} - {q.core_entities}")
            except Exception as e:
                logger.error(f"[{i}/{total}] 写入失败: {e}")
        else:
            skip_count += 1

    logger.info(f"补全完成: 成功 {success_count} 条, 跳过 {skip_count} 条(无考点)")

    # 验证：查询 Neo4j 中的考频关系数量
    try:
        with graph.session() as session:
            result = session.run("MATCH ()-[r:考频]->() RETURN count(r) as count")
            record = result.single()
            if record:
                logger.info(f"Neo4j 考频关系总数: {record['count']}")
    except Exception as e:
        logger.error(f"验证失败: {e}")


if __name__ == "__main__":
    backfill_neo4j()