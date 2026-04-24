"""Position Normalization Worker - 岗位归一化定时任务

使用 APScheduler 每周日凌晨 3 点执行岗位名称归一化任务。

运行方式：
    # 定时执行
    PYTHONPATH=. uv run python -m app.application.workers.position_normalization_worker

    # 立即执行一次
    PYTHONPATH=. uv run python -m app.application.workers.position_normalization_worker --run-now
"""

import argparse
import asyncio
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from app.application.services.position_normalization_service import (
    get_position_normalization_service,
)
from app.infrastructure.common.logger import logger


async def run_normalization_job():
    """执行归一化任务"""
    logger.info("Starting scheduled position normalization job...")

    try:
        service = get_position_normalization_service()
        stats = await service.run_pipeline()

        logger.info(
            f"Position normalization job completed: "
            f"{len(stats)} positions migrated"
        )
        return stats

    except Exception as e:
        logger.error(f"Position normalization job failed: {e}", exc_info=True)
        return None


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="岗位归一化 Worker")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="立即执行一次归一化，不启动定时任务",
    )
    args = parser.parse_args()

    logger.info("Starting position normalization worker...")

    if args.run_now:
        logger.info("Running position normalization immediately...")
        asyncio.run(run_normalization_job())
        return

    scheduler = BlockingScheduler()

    # 每周日凌晨 3 点执行
    scheduler.add_job(
        lambda: asyncio.run(run_normalization_job()),
        "cron",
        day_of_week="sun",
        hour=3,
        minute=0,
        id="position_normalization_job",
        name="岗位归一化任务",
    )

    logger.info(
        "Position normalization worker started. "
        "Next run at Sunday 3:00 AM."
    )
    logger.info("Use --run-now to execute normalization immediately")

    def signal_handler(signum, frame):
        logger.info("Shutting down position normalization worker...")
        scheduler.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Position normalization worker stopped.")


if __name__ == "__main__":
    main()