"""ExtractTask 仓库的 PostgreSQL 实现

实现 ExtractTaskRepository Protocol，基于 PostgreSQL 持久化 ExtractTask 聚合。
复用 PostgresClient 的现有操作，封装为 Repository 模式。
"""

from __future__ import annotations

import gzip
import json
from datetime import datetime
from typing import List, Optional

from app.domain.question.aggregates import ExtractTask, ExtractTaskStatus

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

    def create(
        self,
        user_id: str,
        source_type: str,
        source_content: str | None = None,
        source_images: list[str] | None = None,
    ) -> ExtractTask:
        """创建提取任务

        Args:
            user_id: 用户 ID
            source_type: 来源类型（text/image）
            source_content: 文本内容
            source_images: 图片列表

        Returns:
            新创建的 ExtractTask 聚合
        """
        import uuid
        task_id = str(uuid.uuid4())
        now = datetime.now()

        source_images_gz = None
        if source_images:
            images_json = json.dumps(source_images)
            source_images_gz = gzip.compress(images_json.encode())

        with self._client.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO extract_tasks
                (task_id, user_id, source_type, source_content, source_images_gz, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (task_id, user_id, source_type, source_content,
                 source_images_gz, ExtractTaskStatus.PENDING, now, now),
            )
            self._client.conn.commit()

        logger.info(f"Created extract task: task_id={task_id}, user={user_id}")

        return ExtractTask(
            task_id=task_id,
            user_id=user_id,
            source_type=source_type,
            source_content=source_content or "",
            source_images=source_images,
            status=ExtractTaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

    def find_by_id(self, task_id: str) -> ExtractTask | None:
        """根据 ID 查找提取任务

        Args:
            task_id: 任务唯一标识

        Returns:
            ExtractTask 实例或 None
        """
        try:
            with self._client.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT task_id, user_id, source_type, source_content,
                           source_images_gz, status, error_message, result,
                           created_at, updated_at
                    FROM extract_tasks WHERE task_id = %s
                    """,
                    (task_id,),
                )
                row = cur.fetchone()

            if row is None:
                return None

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
            return self._row_dict_to_domain(row_dict)

        except Exception as e:
            logger.error(f"Failed to find extract task {task_id}: {e}")
            raise

    def save(self, task: ExtractTask) -> None:
        """保存提取任务

        Args:
            task: ExtractTask 实例
        """
        try:
            now = datetime.now()

            # 更新任务
            if task.extracted_interview is not None:
                # 有结果，更新 result 和状态
                self.update_result(task.task_id, task.extracted_interview)
            else:
                # 只更新状态
                self.update_status(task.task_id, task.status)

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

    def find_by_user(
        self,
        user_id: str,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[ExtractTask]:
        """查找用户的任务列表

        Args:
            user_id: 用户 ID
            status: 状态过滤
            limit: 返回数量
            offset: 偏移量

        Returns:
            ExtractTask 列表
        """
        try:
            tasks = []
            with self._client.conn.cursor() as cur:
                if status:
                    cur.execute(
                        """
                        SELECT task_id, user_id, source_type, source_content,
                               source_images_gz, status, error_message, result,
                               created_at, updated_at
                        FROM extract_tasks WHERE user_id = %s AND status = %s
                        ORDER BY updated_at DESC LIMIT %s OFFSET %s
                        """,
                        (user_id, status, limit, offset),
                    )
                else:
                    cur.execute(
                        """
                        SELECT task_id, user_id, source_type, source_content,
                               source_images_gz, status, error_message, result,
                               created_at, updated_at
                        FROM extract_tasks WHERE user_id = %s
                        ORDER BY updated_at DESC LIMIT %s OFFSET %s
                        """,
                        (user_id, limit, offset),
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

            logger.info(f"Found {len(tasks)} tasks for user={user_id}")
            return tasks

        except Exception as e:
            logger.error(f"Failed to find tasks by user: {e}")
            raise

    def update_status(self, task_id: str, status: str) -> None:
        """更新任务状态

        Args:
            task_id: 任务 ID
            status: 新状态
        """
        try:
            now = datetime.now()
            with self._client.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE extract_tasks SET status = %s, updated_at = %s
                    WHERE task_id = %s
                    """,
                    (status, now, task_id),
                )
                self._client.conn.commit()
            logger.info(f"Updated task status: task_id={task_id}, status={status}")
        except Exception as e:
            logger.error(f"Failed to update task status: {e}")
            raise

    def update_result(self, task_id: str, result: dict) -> None:
        """更新任务结果

        Args:
            task_id: 任务 ID
            result: 提取结果（ExtractedInterview 字典）
        """
        try:
            now = datetime.now()
            with self._client.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE extract_tasks SET result = %s, status = %s, updated_at = %s
                    WHERE task_id = %s
                    """,
                    (json.dumps(result), ExtractTaskStatus.COMPLETED, now, task_id),
                )
                self._client.conn.commit()
            logger.info(f"Updated task result: task_id={task_id}")
        except Exception as e:
            logger.error(f"Failed to update task result: {e}")
            raise

    def count_by_user(self, user_id: str, status: str | None = None) -> int:
        """统计用户任务数量

        Args:
            user_id: 用户 ID
            status: 状态过滤

        Returns:
            任务数量
        """
        try:
            with self._client.conn.cursor() as cur:
                if status:
                    cur.execute(
                        "SELECT COUNT(*) FROM extract_tasks WHERE user_id = %s AND status = %s",
                        (user_id, status),
                    )
                else:
                    cur.execute(
                        "SELECT COUNT(*) FROM extract_tasks WHERE user_id = %s",
                        (user_id,),
                    )
                return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to count tasks: {e}")
            raise

    def find_by_id_with_user(self, task_id: str, user_id: str) -> ExtractTask | None:
        """根据 ID 和用户 ID 查找提取任务

        Args:
            task_id: 任务唯一标识
            user_id: 用户 ID（用于验证归属）

        Returns:
            ExtractTask 实例或 None
        """
        try:
            with self._client.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT task_id, user_id, source_type, source_content,
                           source_images_gz, status, error_message, result,
                           created_at, updated_at
                    FROM extract_tasks WHERE task_id = %s AND user_id = %s
                    """,
                    (task_id, user_id),
                )
                row = cur.fetchone()

            if row is None:
                return None

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
            return self._row_dict_to_domain(row_dict)

        except Exception as e:
            logger.error(f"Failed to find extract task {task_id}: {e}")
            raise

    def update_edit(
        self,
        task_id: str,
        user_id: str,
        company: str,
        position: str,
        questions: list[dict],
    ) -> ExtractTask | None:
        """编辑任务结果

        Args:
            task_id: 任务 ID
            user_id: 用户 ID
            company: 公司名称
            position: 岗位名称
            questions: 题目列表

        Returns:
            更新后的 ExtractTask 或 None
        """
        try:
            now = datetime.now()

            # 构建新的 result
            result = {
                "company": company,
                "position": position,
                "questions": questions,
            }

            with self._client.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE extract_tasks
                    SET result = %s, updated_at = %s
                    WHERE task_id = %s AND user_id = %s AND status = 'completed'
                    RETURNING task_id, user_id, source_type, source_content,
                              source_images_gz, status, error_message, result,
                              created_at, updated_at
                    """,
                    (json.dumps(result), now, task_id, user_id),
                )
                row = cur.fetchone()
                self._client.conn.commit()

            if row is None:
                return None

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
            logger.info(f"Edited extract task: task_id={task_id}")
            return self._row_dict_to_domain(row_dict)

        except Exception as e:
            logger.error(f"Failed to edit extract task {task_id}: {e}")
            raise

    def delete_with_user(self, task_id: str, user_id: str) -> bool:
        """删除任务（带用户验证）

        Args:
            task_id: 任务唯一标识
            user_id: 用户 ID

        Returns:
            是否成功删除
        """
        try:
            with self._client.conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM extract_tasks WHERE task_id = %s AND user_id = %s",
                    (task_id, user_id),
                )
                self._client.conn.commit()
                deleted = cur.rowcount > 0
            if deleted:
                logger.info(f"Deleted extract task: {task_id}")
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete extract task {task_id}: {e}")
            raise

    def _row_dict_to_domain(self, row_dict: dict) -> ExtractTask:
        """将数据库行字典转换为 domain ExtractTask

        Args:
            row_dict: 数据库行字典

        Returns:
            domain ExtractTask 聚合
        """
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

        source_images = None
        source_images_gz = row_dict.get("source_images_gz")
        if source_images_gz:
            try:
                decompressed = gzip.decompress(source_images_gz).decode()
                source_images = json.loads(decompressed)
            except Exception as e:
                logger.warning(f"Failed to decompress images: {e}")

        return ExtractTask(
            task_id=row_dict["task_id"],
            user_id=row_dict["user_id"],
            source_type=row_dict["source_type"],
            source_content=row_dict.get("source_content") or "",
            source_images=source_images,
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