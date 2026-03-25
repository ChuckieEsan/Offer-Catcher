#!/usr/bin/env python
"""将没有答案的题目重新加入 RabbitMQ 队列

用法:
    python scripts/resend_to_queue.py [--dry-run]

选项:
    --dry-run  只显示要重发的题目，不实际发送
"""

import argparse
import asyncio

from app.db.qdrant_client import get_qdrant_manager
from app.mq.producer import AsyncRabbitMQProducer
from app.models.schemas import MQTaskMessage
from app.utils.logger import logger
from app.models.schemas import QuestionType

async def resend_unanswered_questions(dry_run: bool = True):
    """将没有答案的题目重新加入队列

    Args:
        dry_run: 如果为 True，只显示不发送
    """
    
    qdrant = get_qdrant_manager()

    # 获取所有题目（使用空的 query_vector 搜索会返回所有）
    # 这里用一个全零向量来获取所有记录
    zero_vector = [0.0] * 1024  # BGE-M3 的维度

    logger.info("正在搜索没有答案的题目...")
    results = qdrant.search(
        query_vector=zero_vector,
        limit=1000,
    )

    # 过滤出没有答案的题目，且只处理 knowledge 和 scenario 类型
    unanswered = [
        r for r in results
        if not r.question_answer
        and r.question_type in (QuestionType.KNOWLEDGE, QuestionType.SCENARIO)
    ]

    if not unanswered:
        logger.info("没有需要重新处理的 knowledge/scenario 题目")
        return

    logger.info(f"找到 {len(unanswered)} 条没有答案的 knowledge/scenario 题目")

    # 显示要重发的题目
    print("\n将重发的题目:")
    print("-" * 60)
    for r in unanswered:
        print(f"  [{r.company}] {r.question_text[:50]}...")
    print("-" * 60)
    print(f"共 {len(unanswered)} 条\n")

    if dry_run:
        logger.info("这是 dry-run 模式，没有实际发送。去掉 --dry-run 参数实际发送。")
        return

    # 发送到队列
    logger.info("正在发送消息到队列...")
    producer = AsyncRabbitMQProducer()
    await producer.connect()

    try:
        for r in unanswered:
            task = MQTaskMessage(
                question_id=r.question_id,
                question_text=r.question_text,
                company=r.company or "",
                position=r.position or "",
                core_entities=r.core_entities or [],
            )
            await producer.publish_task(task)
            logger.info(f"已发送: {r.question_id}")

        logger.info(f"成功发送 {len(unanswered)} 条消息到队列")
    finally:
        await producer.close()


def main():
    parser = argparse.ArgumentParser(description="将没有答案的题目重新加入队列")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="只显示不发送",
    )
    args = parser.parse_args()

    asyncio.run(resend_unanswered_questions(dry_run=args.dry_run))


if __name__ == "__main__":
    main()