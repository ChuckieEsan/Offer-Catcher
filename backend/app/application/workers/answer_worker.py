"""Answer Worker - 答案生成后台任务

使用线程池模式消费 RabbitMQ 消息，每个线程独立连接和 channel。
适用于 LLM 调用等阻塞型任务，实现真正的并发处理。

运行方式：
    # 默认 4 个工作线程
    PYTHONPATH=. uv run python -m app.application.workers.answer_worker

    # 指定线程数
    WORKER_THREADS=8 PYTHONPATH=. uv run python -m app.application.workers.answer_worker
"""

import asyncio
import os
import signal

from app.application.agents.factory import get_answer_specialist
from app.infrastructure.persistence.qdrant.question_repository import get_question_repository
from app.infrastructure.messaging import get_thread_pool_consumer
from app.models import MQTaskMessage, QuestionItem, QuestionType, MasteryLevel
from app.infrastructure.common.logger import logger


def process_answer_task(task: MQTaskMessage) -> bool:
    """处理答案生成任务（同步函数）

    Args:
        task: MQ 消息

    Returns:
        是否成功
    """
    try:
        question_repo = get_question_repository()

        # 幂等性检查：先判断答案是否已存在
        existing = question_repo.find_by_id(task.question_id)
        if existing and existing.answer:
            logger.info(f"Answer already exists for: {task.question_id}, skipping")
            return True

        # 创建 QuestionItem 对象
        question = QuestionItem(
            question_id=task.question_id,
            question_text=task.question_text,
            question_type=QuestionType.KNOWLEDGE,
            requires_async_answer=True,
            core_entities=task.core_entities,
            mastery_level=MasteryLevel.LEVEL_0,
            company=task.company,
            position=task.position,
        )

        # 使用 factory 获取 Agent（已注入依赖）
        agent = get_answer_specialist()
        answer = agent.generate_answer(question)

        # 写入 Qdrant
        question_repo.update_answer(task.question_id, answer)

        logger.info(f"Answer generated and saved for: {task.question_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to process task {task.question_id}: {e}")
        return False


async def main():
    """主函数"""
    num_threads = int(os.getenv("WORKER_THREADS", "4"))
    prefetch_count = int(os.getenv("PREFETCH_COUNT", "1"))

    logger.info(f"Starting Answer Worker (thread pool mode, {num_threads} threads, prefetch={prefetch_count})")

    consumer = await get_thread_pool_consumer(
        num_threads=num_threads,
        prefetch_count=prefetch_count,
    )

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("Received shutdown signal, stopping worker...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    await consumer.start(process_answer_task)
    logger.info(f"Worker started with {num_threads} threads, waiting for messages...")

    await stop_event.wait()

    await consumer.stop()
    logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())