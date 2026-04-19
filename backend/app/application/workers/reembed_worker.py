"""Reembed Worker - 批量重新嵌入脚本

用于在所有题目已存在的情况下，使用新的上下文格式重新计算 embedding。

运行方式：
    PYTHONPATH=. uv run python -m app.application.workers.reembed_worker
"""

import asyncio

from app.infrastructure.persistence.qdrant import get_qdrant_client
from app.infrastructure.adapters.embedding_adapter import get_embedding_adapter
from app.infrastructure.common.logger import logger


async def reembed_all():
    """重新嵌入所有题目"""
    print("=" * 60)
    print("批量重新嵌入脚本")
    print("=" * 60)

    qdrant_client = get_qdrant_client()
    embedding_adapter = get_embedding_adapter()

    # 遍历获取所有题目
    print("\n[Step 1] 获取所有题目...")
    all_questions = []
    offset = None

    while True:
        batch, offset = qdrant_client.scroll(limit=100, offset=offset)
        if not batch:
            break
        all_questions.extend(batch)
        print(f"  已获取 {len(all_questions)} 道题目...")
        if offset is None:
            break

    if not all_questions:
        print("没有找到任何题目")
        return

    print(f"共找到 {len(all_questions)} 道题目")

    # 批量重新嵌入（每次 10 道）
    print("\n[Step 2] 开始重新嵌入...")

    BATCH_SIZE = 10
    total_reembedded = 0
    total_failed = 0

    for i in range(0, len(all_questions), BATCH_SIZE):
        batch = all_questions[i:i + BATCH_SIZE]
        print(f"\n处理批次 {i // BATCH_SIZE + 1}/{(len(all_questions) + BATCH_SIZE - 1) // BATCH_SIZE}: "
              f"题目 {i + 1}-{min(i + BATCH_SIZE, len(all_questions))}")

        ids = []
        vectors = []

        for record in batch:
            try:
                payload = record.payload

                entities = payload.get("core_entities", [])
                entities_str = ",".join(entities) if entities else "综合"

                context = (
                    f"公司：{payload.get('company', '')} | "
                    f"岗位：{payload.get('position', '')} | "
                    f"类型：{payload.get('question_type', 'knowledge')} | "
                    f"考点：{entities_str} | "
                    f"题目：{payload.get('question_text', '')}"
                )

                vector = embedding_adapter.embed(context)

                ids.append(record.id)
                vectors.append(vector)
                total_reembedded += 1

            except Exception as e:
                print(f"  失败：{record.id} - {e}")
                total_failed += 1

        if ids:
            try:
                qdrant_client.update_vectors(ids, vectors)
                print(f"  批次完成：{len(ids)} 道题目")
            except Exception as e:
                print(f"  批次失败：{e}")

    print("\n" + "=" * 60)
    print(f"重新嵌入完成!")
    print(f"  成功：{total_reembedded} 道")
    print(f"  失败：{total_failed} 道")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(reembed_all())