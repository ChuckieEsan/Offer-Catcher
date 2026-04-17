#!/usr/bin/env python
"""将没有答案的题目重新加入 RabbitMQ 队列

用法:
    PYTHONPATH=. uv run python scripts/resend_to_queue.py [--dry-run]

选项:
    --dry-run  只显示要重发的题目，不实际发送
"""

import argparse
import asyncio

from app.application.services.question_service import get_question_service
from app.infrastructure.messaging import get_producer
from app.domain.shared.enums import QuestionType
from app.models.question import MQTaskMessage
from app.infrastructure.common.logger import logger


async def resend_unanswered_questions(dry_run: bool = True):
    """将没有答案的题目重新加入队列

    Args:
        dry_run: 如果为 True，只显示不发送
    """
    question_service = get_question_service()

    # 获取所有题目
    logger.info("正在获取所有题目...")
    questions, total = question_service.list_questions()

    # 过滤出没有答案的题目，且只处理 knowledge、scenario 和 algorithm 类型
    async_types = (QuestionType.KNOWLEDGE, QuestionType.SCENARIO, QuestionType.ALGORITHM)
    unanswered = [
        q for q in questions
        if not q.answer and q.question_type in async_types
    ]

    if not unanswered:
        logger.info("没有需要重新处理的 knowledge/scenario/algorithm 题目")
        return

    logger.info(f"找到 {len(unanswered)} 条没有答案的 knowledge/scenario/algorithm 题目")

    # 显示要重发的题目
    print("\n将重发的题目:")
    print("-" * 60)
    for q in unanswered[:20]:  # 只显示前20条
        print(f"  [{q.company}] {q.question_text[:50]}...")
    if len(unanswered) > 20:
        print(f"  ... 还有 {len(unanswered) - 20} 条")
    print("-" * 60)
    print(f"共 {len(unanswered)} 条\n")

    if dry_run:
        logger.info("这是 dry-run 模式，没有实际发送。去掉 --dry-run 参数实际发送。")
        return

    # 发送到队列
    logger.info("正在发送消息到队列...")
    producer = await get_producer()

    sent = 0
    for q in unanswered:
        task = MQTaskMessage(
            question_id=q.question_id,
            question_text=q.question_text,
            company=q.company,
            position=q.position,
            core_entities=q.core_entities,
        )
        await producer.publish_task(task)
        sent += 1
        if sent % 50 == 0:
            logger.info(f"已发送 {sent} 条消息...")

    logger.info(f"成功发送 {sent} 条消息到队列")


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