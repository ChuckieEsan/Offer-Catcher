"""Extract Worker - 面经解析后台任务

处理面经解析任务，从 PostgreSQL 获取待处理任务并执行解析。

运行方式：
    # 默认轮询间隔 5 秒
    PYTHONPATH=. uv run python -m app.application.workers.extract_worker

    # 指定轮询间隔（秒）
    POLL_INTERVAL=5 PYTHONPATH=. uv run python -m app.application.workers.extract_worker
"""

import asyncio
import gzip
import json
import os
import signal

from app.application.agents.factory import get_vision_extractor
from app.domain.question import ExtractTaskStatus
from app.infrastructure.persistence.postgres import get_postgres_client
from app.infrastructure.common.logger import logger


async def process_extract_task(task_id: str) -> bool:
    """处理单个面经解析任务

    Args:
        task_id: 任务 ID

    Returns:
        是否成功
    """
    pg = get_postgres_client()

    try:
        # 获取任务
        task = pg.get_extract_task(task_id)
        if not task:
            logger.warning(f"Task not found: {task_id}")
            return False

        # 检查状态
        if task.status != ExtractTaskStatus.PENDING:
            logger.info(f"Task {task_id} already processed: {task.status}")
            return True

        # 更新状态为处理中
        pg.update_extract_task_status(task_id, ExtractTaskStatus.PROCESSING)
        logger.info(f"Processing task: {task_id}")

        # 使用 factory 获取 Agent（已注入依赖）
        extractor = get_vision_extractor()

        if task.source_type == "text":
            result = extractor.extract(task.source_content, source_type="text")
        else:
            # 图片解析：解压 gzip 压缩的图片数据
            if task.source_images_gz:
                if isinstance(task.source_images_gz, list):
                    images = task.source_images_gz
                else:
                    images = json.loads(gzip.decompress(task.source_images_gz).decode())
            else:
                images = []

            result = extractor.extract(images, source_type="image", use_ocr=True)

        # 更新结果
        pg.update_extract_task_result(task_id, result)
        logger.info(f"Task completed: {task_id}, company={result.company}, questions={len(result.questions)}")

        return True

    except Exception as e:
        logger.error(f"Failed to process task {task_id}: {e}")
        pg.update_extract_task_status(task_id, ExtractTaskStatus.FAILED, str(e))
        return False


async def poll_and_process(poll_interval: int = 5):
    """轮询并处理待处理任务

    Args:
        poll_interval: 轮询间隔（秒）
    """
    pg = get_postgres_client()

    logger.info(f"Starting poll loop with interval {poll_interval}s")

    while True:
        try:
            with pg.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT task_id FROM extract_tasks
                    WHERE status = %s
                    ORDER BY created_at ASC
                    LIMIT 10
                    """,
                    (ExtractTaskStatus.PENDING,),
                )
                rows = cur.fetchall()

            if rows:
                logger.info(f"Found {len(rows)} pending tasks")

                for (task_id,) in rows:
                    await process_extract_task(task_id)

            await asyncio.sleep(poll_interval)

        except Exception as e:
            logger.error(f"Poll error: {e}")
            await asyncio.sleep(poll_interval)


async def main():
    """主函数"""
    poll_interval = int(os.getenv("POLL_INTERVAL", "5"))

    logger.info(f"Starting Extract Worker (poll interval: {poll_interval}s)")

    pg = get_postgres_client()
    pg.init_tables()
    logger.info("Database tables initialized")

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("Received shutdown signal, stopping worker...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    poll_task = asyncio.create_task(poll_and_process(poll_interval))

    await stop_event.wait()

    poll_task.cancel()
    try:
        await poll_task
    except asyncio.CancelledError:
        pass

    logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())