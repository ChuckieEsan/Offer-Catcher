"""聚类定时任务 Worker

使用 APScheduler 每天凌晨 2 点执行聚类任务。

运行方式：
    # 定时执行（每天凌晨 2 点）
    PYTHONPATH=. uv run python workers/clustering_worker.py

    # 立即执行一次聚类
    PYTHONPATH=. uv run python workers/clustering_worker.py --run-now

    # 显示帮助
    PYTHONPATH=. uv run python workers/clustering_worker.py --help
"""

import signal
import sys
import argparse

from apscheduler.schedulers.blocking import BlockingScheduler

from app.services.clustering_service import get_clustering_service
from app.utils.logger import logger


def run_clustering_job():
    """执行聚类任务"""
    logger.info("Starting scheduled clustering job...")

    try:
        service = get_clustering_service(min_cluster_size=5, auto_k=True)
        result = service.run_clustering()

        logger.info(
            f"Clustering job completed: total={result.total_questions}, "
            f"clustered={result.clustered_count}, clusters={result.cluster_count}, "
            f"silhouette={result.silhouette_score:.4f}"
        )
        return result
    except Exception as e:
        logger.error(f"Clustering job failed: {e}", exc_info=True)
        return None


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="聚类 Worker")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="立即执行一次聚类，不启动定时任务",
    )
    parser.add_argument(
        "--min-cluster-size",
        type=int,
        default=5,
        help="最小簇大小 (默认: 5)",
    )
    parser.add_argument(
        "--max-clusters",
        type=int,
        default=30,
        help="最大簇数量 (默认: 30)",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=None,
        help="预设簇数 (默认: 自动选择)",
    )
    parser.add_argument(
        "--no-auto-k",
        action="store_true",
        help="禁用自动 K 选择，使用计算的 K 值",
    )
    args = parser.parse_args()

    logger.info("Starting clustering worker...")

    # 如果指定了 --run-now，立即执行一次聚类
    if args.run_now:
        auto_k = not args.no_auto_k
        logger.info(
            f"Running clustering immediately (min_cluster_size={args.min_cluster_size}, "
            f"max_clusters={args.max_clusters}, auto_k={auto_k})..."
        )

        # 清除单例缓存以使用新参数
        from app.application.services.clustering_service import get_clustering_service as get_service
        get_service.clear_cache()

        service = get_clustering_service(
            min_cluster_size=args.min_cluster_size,
            max_clusters=args.max_clusters,
            auto_k=auto_k,
        )
        result = service.run_clustering(k=args.k)

        if result:
            logger.info(
                f"Clustering completed: {result.cluster_count} clusters, "
                f"{result.clustered_count}/{result.total_questions} questions, "
                f"silhouette={result.silhouette_score:.4f}"
            )
        else:
            logger.error("Clustering failed")
            sys.exit(1)

        return

    # 创建调度器
    scheduler = BlockingScheduler()

    # 添加定时任务：每天凌晨 2 点执行
    scheduler.add_job(
        run_clustering_job,
        "cron",
        hour=2,
        minute=0,
        id="clustering_job",
        name="题目聚类任务",
    )

    logger.info("Clustering worker started. Next run at 2:00 AM daily.")
    logger.info("Use --run-now to execute clustering immediately")

    # 设置信号处理器Graceful shutdown
    def signal_handler(signum, frame):
        logger.info("Shutting down clustering worker...")
        scheduler.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Clustering worker stopped.")


if __name__ == "__main__":
    main()