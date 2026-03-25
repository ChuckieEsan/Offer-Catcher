"""Answer Worker 入口脚本

支持两种消费模式：
1. 异步模式（默认）：基于协程的异步消费
2. 线程池模式：基于 ThreadPoolExecutor，每个线程独立 channel

可通过环境变量 WORKER_MODE 选择：
- async: 异步协程模式（默认）
- thread_pool: 线程池模式
"""

import asyncio
import os

from app.agents.answer_specialist import get_answer_specialist
from app.db.qdrant_client import get_qdrant_manager
from app.mq.consumer import get_consumer
from app.mq.thread_pool_consumer import get_thread_pool_consumer
from app.models.schemas import MQTaskMessage
from app.models.schemas import QuestionItem, QuestionType, MasteryLevel
from app.utils.logger import logger


async def process_answer_task(task: MQTaskMessage) -> bool:
    """处理答案生成任务

    Args:
        task: MQ 消息

    Returns:
        是否成功
    """
    try:
        # 0. 幂等性检查：先判断答案是否已存在
        qdrant = get_qdrant_manager()
        existing = qdrant.get_question(task.question_id)
        if existing and existing.question_answer:
            logger.info(f"Answer already exists for: {task.question_id}, skipping")
            return True

        # 1. 创建 QuestionItem 对象
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

        # 2. 生成答案
        agent = get_answer_specialist(provider="dashscope")
        answer = agent.generate_answer(question)

        # 3. 写入 Qdrant
        qdrant.update_question(task.question_id, question_answer=answer)

        logger.info(f"Answer generated and saved for: {task.question_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to process task {task.question_id}: {e}")
        return False


async def main():
    """主函数"""
    worker_mode = os.getenv("WORKER_MODE", "async").lower()

    logger.info(f"Starting Answer Worker in {worker_mode} mode...")

    if worker_mode == "thread_pool":
        await run_thread_pool_mode()
    else:
        await run_async_mode()


async def run_async_mode():
    """异步协程模式（默认）"""
    logger.info("Using async coroutine consumer (prefetch=5)")
    consumer = await get_consumer(prefetch_count=5)
    logger.info("Worker started, waiting for messages...")
    await consumer.consume(process_answer_task)


async def run_thread_pool_mode():
    """线程池模式"""
    num_threads = int(os.getenv("WORKER_THREADS", "4"))
    logger.info(f"Using thread pool consumer ({num_threads} threads)")

    consumer = await get_thread_pool_consumer(
        num_threads=num_threads, prefetch_count=1
    )
    await consumer.start(process_answer_task)
    logger.info(f"Thread pool worker started with {num_threads} threads, waiting for messages...")

    # 保持主线程运行
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        logger.info("Worker cancelled, stopping...")
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(main())