"""Extract Worker 入口脚本

处理面经解析任务，从 PostgreSQL 获取待处理任务并执行解析。

运行方式：
    # 默认 2 个工作线程
    PYTHONPATH=. uv run python workers/extract_worker.py

    # 指定轮询间隔（秒）
    POLL_INTERVAL=5 PYTHONPATH=. uv run python workers/extract_worker.py
"""

import asyncio
import os
import signal
import gzip
import json

from app.agents.vision_extractor import get_vision_extractor
from app.db.postgres_client import get_postgres_client, ExtractTaskStatus
from app.models.schemas import ExtractTaskCreate
from app.utils.logger import logger


async def process_extract_task(task_id: str) -> bool:
    """处理单个面经解析任务

    Args:
        task_id: 任务 ID

    Returns:
        是否成功
    """
    pg = get_postgres_client()

    try:
        # 1. 获取任务
        task = pg.get_extract_task(task_id)
        if not task:
            logger.warning(f"Task not found: {task_id}")
            return False

        # 2. 检查状态
        if task.status != ExtractTaskStatus.PENDING:
            logger.info(f"Task {task_id} already processed: {task.status}")
            return True

        # 3. 更新状态为处理中
        pg.update_extract_task_status(task_id, ExtractTaskStatus.PROCESSING)
        logger.info(f"Processing task: {task_id}")

        # 4. 执行解析
        extractor = get_vision_extractor()

        if task.source_type == "text":
            # 文本解析
            result = extractor.extract(task.source_content, source_type="text")
        else:
            # 图片解析
            # 解压 gzip 压缩的图片数据
            if task.source_images_gz:
                if isinstance(task.source_images_gz, list):
                    images = task.source_images_gz
                else:
                    # 如果是 gzip 压缩的字节，需要解压
                    images = json.loads(gzip.decompress(task.source_images_gz).decode())
            else:
                images = []

            result = extractor.extract(images, source_type="image", use_ocr=True)

        # 5. 更新结果
        pg.update_extract_task_result(task_id, result)
        logger.info(f"Task completed: {task_id}, company={result.company}, questions={len(result.questions)}")

        return True

    except Exception as e:
        logger.error(f"Failed to process task {task_id}: {e}")
        # 更新失败状态
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
            # 查询待处理任务
            # 这里简化处理，直接查询 status=pending 的任务
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

            # 等待下一轮
            await asyncio.sleep(poll_interval)

        except Exception as e:
            logger.error(f"Poll error: {e}")
            await asyncio.sleep(poll_interval)


async def main():
    """主函数"""
    poll_interval = int(os.getenv("POLL_INTERVAL", "5"))

    logger.info(f"Starting Extract Worker (poll interval: {poll_interval}s)")

    # 初始化数据库连接
    pg = get_postgres_client()
    pg.init_tables()
    logger.info("Database tables initialized")

    # 设置信号处理器（优雅关闭）
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("Received shutdown signal, stopping worker...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    # 启动轮询
    poll_task = asyncio.create_task(poll_and_process(poll_interval))

    # 等待停止信号
    await stop_event.wait()

    # 取消轮询任务
    poll_task.cancel()
    try:
        await poll_task
    except asyncio.CancelledError:
        pass

    logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())