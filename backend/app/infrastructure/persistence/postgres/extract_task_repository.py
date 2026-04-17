"""ExtractTask 仓库的 PostgreSQL 实现

实现 ExtractTaskRepository Protocol，基于 PostgreSQL 持久化 ExtractTask 聚合。
复用 PostgresClient 的现有操作，封装为 Repository 模式。
"""

from typing import Optional

from app.domain.question.aggregates import ExtractTask, ExtractTaskStatus
from app.domain.question.repositories import ExtractTaskRepository
from app.models import ExtractedInterview

from app.infrastructure.persistence.postgres.client import (
    PostgresClient,
    get_postgres_client,
)
from app.infrastructure.common.logger import logger


class PostgresExtractTaskRepository:
    """ExtractTask 仓库的 PostgreSQL 实现

    实现 ExtractTaskRepository Protocol 的所有方法。
    复用 PostgresClient 的现有 extract_tasks 表操作。

    字段映射：
    - domain.extracted_interview -> postgres.result
    - domain.status -> postgres.status
    """

    def __init__(
        self,
        client: Optional[PostgresClient] = None,
    ) -> None:
        """初始化仓库

        Args:
            client: PostgreSQL 客户端（支持依赖注入）
        """
        self._client = client or get_postgres_client()

    def find_by_id(self, task_id: str) -> ExtractTask | None:
        """根据 ID 查找提取任务

        Args:
            task_id: 任务唯一标识

        Returns:
            ExtractTask 实例或 None
        """
        try:
            # 使用 PostgresClient 的现有方法
            row = self._client.get_extract_task(task_id)
            if row is None:
                return None

            # 转换为 domain ExtractTask
            return self._row_to_domain(row)

        except Exception as e:
            logger.error(f"Failed to find extract task {task_id}: {e}")
            raise

    def save(self, task: ExtractTask) -> None:
        """保存提取任务

        Args:
            task: ExtractTask 实例
        """
        try:
            # 获取现有任务
            existing = self._client.get_extract_task(task.task_id)

            if existing is None:
                # 新任务 - 使用 PostgresClient 的创建方法
                # 注意：PostgresClient.create_extract_task 需要 ExtractTaskCreate
                # 这里简化处理，直接更新状态
                logger.warning(
                    f"ExtractTask {task.task_id} not found in DB, "
                    "creating new tasks should use create_extract_task API"
                )
                return

            # 更新现有任务
            # 根据状态更新
            if task.extracted_interview is not None:
                # 有结果，更新 result 和状态
                extracted = ExtractedInterview(**task.extracted_interview)
                self._client.update_extract_task_result(task.task_id, extracted)
            else:
                # 只更新状态
                self._client.update_extract_task_status(task.task_id, task.status)

            logger.info(f"Saved extract task: {task.task_id}, status={task.status}")

        except Exception as e:
            logger.error(f"Failed to save extract task {task.task_id}: {e}")
            raise

    def delete(self, task_id: str) -> None:
        """删除提取任务

        Args:
            task_id: 任务唯一标识
        """
        try:
            # PostgresClient 的 delete_extract_task 需要 user_id
            # 这里简化处理，使用底层 SQL
            with self._client.conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM extract_tasks WHERE task_id = %s",
                    (task_id,),
                )
                self._client.conn.commit()
            logger.info(f"Deleted extract task: {task_id}")
        except Exception as e:
            logger.error(f"Failed to delete extract task {task_id}: {e}")
            raise

    def find_by_status(self, status: str) -> list[ExtractTask]:
        """根据状态查找提取任务

        Args:
            status: 任务状态

        Returns:
            匹配的 ExtractTask 列表
        """
        try:
            tasks = []
            with self._client.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT task_id, user_id, source_type, source_content,
                           source_images_gz, status, error_message, result,
                           created_at, updated_at
                    FROM extract_tasks WHERE status = %s
                    ORDER BY created_at DESC
                    """,
                    (status,),
                )
                rows = cur.fetchall()

            for row in rows:
                row_dict = {
                    "task_id": row[0],
                    "user_id": row[1],
                    "source_type": row[2],
                    "source_content": row[3],
                    "source_images_gz": row[4],
                    "status": row[5],
                    "error_message": row[6],
                    "result": row[7],
                    "created_at": row[8],
                    "updated_at": row[9],
                }
                tasks.append(self._row_dict_to_domain(row_dict))

            logger.info(f"Found {len(tasks)} extract tasks with status={status}")
            return tasks

        except Exception as e:
            logger.error(f"Failed to find extract tasks by status: {e}")
            raise

    def find_pending_tasks(self, limit: int = 10) -> list[ExtractTask]:
        """查找待处理的任务

        Args:
            limit: 返回数量限制

        Returns:
            pending 状态的 ExtractTask 列表
        """
        try:
            tasks = []
            with self._client.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT task_id, user_id, source_type, source_content,
                           source_images_gz, status, error_message, result,
                           created_at, updated_at
                    FROM extract_tasks WHERE status = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (ExtractTaskStatus.PENDING, limit),
                )
                rows = cur.fetchall()

            for row in rows:
                row_dict = {
                    "task_id": row[0],
                    "user_id": row[1],
                    "source_type": row[2],
                    "source_content": row[3],
                    "source_images_gz": row[4],
                    "status": row[5],
                    "error_message": row[6],
                    "result": row[7],
                    "created_at": row[8],
                    "updated_at": row[9],
                }
                tasks.append(self._row_dict_to_domain(row_dict))

            logger.info(f"Found {len(tasks)} pending extract tasks")
            return tasks

        except Exception as e:
            logger.error(f"Failed to find pending extract tasks: {e}")
            raise

    def _row_to_domain(self, row: "app.models.ExtractTask") -> ExtractTask:
        """将 PostgresClient 返回的 ExtractTask 模型转换为 domain ExtractTask

        Args:
            row: PostgresClient 的 ExtractTask 模型

        Returns:
            domain ExtractTask 聚合
        """
        # row 是 app.models.ExtractTask，有 result 字段
        # 需要转换为 domain ExtractTask 的 extracted_interview
        extracted_interview = None
        if row.result:
            extracted_interview = row.result.model_dump()

        return ExtractTask(
            task_id=row.task_id,
            source_type=row.source_type,
            source_content=row.source_content or "",
            status=row.status,
            extracted_interview=extracted_interview,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _row_dict_to_domain(self, row_dict: dict) -> ExtractTask:
        """将数据库行字典转换为 domain ExtractTask

        Args:
            row_dict: 数据库行字典

        Returns:
            domain ExtractTask 聚合
        """
        import gzip
        import json
        from datetime import datetime

        extracted_interview = None
        result = row_dict.get("result")
        if result:
            if isinstance(result, dict):
                extracted_interview = result
            elif isinstance(result, str):
                try:
                    extracted_interview = json.loads(result)
                except Exception:
                    pass

        return ExtractTask(
            task_id=row_dict["task_id"],
            source_type=row_dict["source_type"],
            source_content=row_dict.get("source_content") or "",
            status=row_dict["status"],
            extracted_interview=extracted_interview,
            created_at=row_dict["created_at"],
            updated_at=row_dict["updated_at"],
        )


# 单例获取函数
_extract_task_repository: Optional[PostgresExtractTaskRepository] = None


def get_extract_task_repository() -> PostgresExtractTaskRepository:
    """获取 ExtractTask 仓库单例"""
    global _extract_task_repository
    if _extract_task_repository is None:
        _extract_task_repository = PostgresExtractTaskRepository()
    return _extract_task_repository


__all__ = [
    "PostgresExtractTaskRepository",
    "get_extract_task_repository",
]