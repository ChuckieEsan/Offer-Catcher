"""Application Workers - 后台任务处理

提供各类后台 Worker：
- answer_worker: 答案生成（消费 RabbitMQ）
- extract_worker: 面经解析（轮询 PostgreSQL）
- clustering_worker: 题目聚类定时任务
- reembed_worker: 批量重新嵌入脚本
- position_normalization_worker: 岗位归一化定时任务

运行方式：
    PYTHONPATH=. uv run python -m app.application.workers.<worker_name>
"""

__all__ = [
    "answer_worker",
    "extract_worker",
    "clustering_worker",
    "reembed_worker",
    "position_normalization_worker",
]