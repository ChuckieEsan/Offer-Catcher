"""批量重新嵌入 Worker

用于在所有题目已存在的情况下，使用新的上下文格式重新计算 embedding。

使用方式:
    PYTHONPATH=. uv run python workers/reembed_worker.py
"""

import asyncio
from app.pipelines.ingestion import get_ingestion_pipeline
from app.db.qdrant_client import get_qdrant_manager
from app.tools.embedding_tool import get_embedding_tool
from app.utils.logger import logger


async def reembed_all():
    """重新嵌入所有题目"""
    print("=" * 60)
    print("批量重新嵌入脚本")
    print("=" * 60)

    qdrant_manager = get_qdrant_manager()
    embedding_tool = get_embedding_tool()
    ingestion_pipeline = get_ingestion_pipeline()

    # 1. 获取所有题目
    print("\n[Step 1] 获取所有题目...")
    all_questions = qdrant_manager.scroll_all()
    if not all_questions:
        print("没有找到任何题目")
        return

    print(f"共找到 {len(all_questions)} 道题目")

    # 2. 批量重新嵌入（每次 10 道）
    print("\n[Step 2] 开始重新嵌入...")

    BATCH_SIZE = 10
    total_reembedded = 0
    total_failed = 0

    for i in range(0, len(all_questions), BATCH_SIZE):
        batch = all_questions[i:i + BATCH_SIZE]
        print(f"\n处理批次 {i // BATCH_SIZE + 1}/{(len(all_questions) + BATCH_SIZE - 1) // BATCH_SIZE}: "
              f"题目 {i + 1}-{min(i + BATCH_SIZE, len(all_questions))}")

        payloads = []
        vectors = []

        for question in batch:
            try:
                # 使用新的上下文格式
                entities = question.core_entities or []
                entities_str = ",".join(entities) if entities else "综合"

                # question_type 和 mastery_level 可能已经是字符串或 int 了
                q_type = question.question_type
                if hasattr(q_type, 'value'):
                    q_type = q_type.value
                else:
                    q_type = str(q_type)

                mastery = question.mastery_level
                if hasattr(mastery, 'value'):
                    mastery = mastery.value
                else:
                    mastery = int(mastery)

                context = (
                    f"公司：{question.company} | "
                    f"岗位：{question.position} | "
                    f"类型：{q_type} | "
                    f"考点：{entities_str} | "
                    f"题目：{question.question_text}"
                )

                # 计算新向量
                vector = embedding_tool.embed_text(context)

                # 构建 payload
                from app.models import QdrantQuestionPayload
                payload = QdrantQuestionPayload(
                    question_id=question.question_id,
                    question_text=question.question_text,
                    company=question.company,
                    position=question.position,
                    mastery_level=mastery,
                    question_type=q_type,
                    core_entities=question.core_entities,
                    metadata=question.metadata,
                    cluster_ids=question.cluster_ids,
                    question_answer=question.question_answer if hasattr(question, 'question_answer') else None,
                )

                payloads.append(payload)
                vectors.append(vector)
                total_reembedded += 1

            except Exception as e:
                print(f"  失败：{question.question_id} - {e}")
                total_failed += 1

        # 批量更新
        if payloads:
            try:
                qdrant_manager.upsert_questions(payloads, vectors)
                print(f"  批次完成：{len(payloads)} 道题目")
            except Exception as e:
                print(f"  批次失败：{e}")

    print("\n" + "=" * 60)
    print(f"重新嵌入完成!")
    print(f"  成功：{total_reembedded} 道")
    print(f"  失败：{total_failed} 道")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(reembed_all())
