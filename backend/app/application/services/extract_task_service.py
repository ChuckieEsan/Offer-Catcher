"""ExtractTask Application Service - 提取任务应用服务

提供提取任务管理的用例编排：
- 创建任务（提交）
- 查询任务列表
- 获取任务详情
- 编辑任务结果
- 确认入库（编排 IngestionService）
- 删除任务

职责边界：
- 任务生命周期管理：创建、查询、编辑、删除、状态更新
- 入库编排：调用 IngestionService 入库题目，但不实现具体入库逻辑
- 不直接操作 Qdrant，只协调各服务

与 IngestionService 的分工：
- ExtractTaskService: 任务状态管理 + 入库流程编排
- IngestionService: 题目入库实现（Qdrant + MQ）
"""

from __future__ import annotations

from typing import List, Optional

from app.domain.question.aggregates import ExtractTask
from app.domain.question.repositories import ExtractTaskRepository
from app.infrastructure.common.logger import logger


class ExtractTaskApplicationService:
    """提取任务应用服务

    任务生命周期管理：
    - submit: 创建提取任务（pending）
    - list: 查询任务列表
    - get: 获取任务详情
    - edit: 编辑任务结果（completed 状态）
    - confirm: 确认入库 → 调用 IngestionService → 更新为 confirmed
    - delete: 删除任务
    """

    def __init__(self, task_repository: ExtractTaskRepository):
        self._task_repository = task_repository

    def submit(
        self,
        user_id: str,
        source_type: str,
        source_content: Optional[str] = None,
        source_images: Optional[List[str]] = None,
    ) -> ExtractTask:
        """提交提取任务

        Args:
            user_id: 用户 ID
            source_type: 来源类型（text/image）
            source_content: 文本内容
            source_images: 图片列表

        Returns:
            ExtractTask 聚合根
        """
        logger.info(f"Submit extract task: user={user_id}, type={source_type}")

        # 使用 Repository 创建任务
        task = self._task_repository.create(
            user_id=user_id,
            source_type=source_type,
            source_content=source_content,
            source_images=source_images,
        )

        return task

    def list(
        self,
        user_id: str,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[dict], int]:
        """查询任务列表

        Args:
            user_id: 用户 ID
            status: 状态过滤
            page: 页码
            page_size: 每页数量

        Returns:
            (items, total) 元组
        """
        logger.info(f"List extract tasks: user={user_id}, status={status}")

        from app.infrastructure.persistence.postgres import get_postgres_client

        pg = get_postgres_client()
        offset = (page - 1) * page_size
        items = pg.get_extract_tasks(user_id, status, page_size, offset)
        total = pg.count_extract_tasks(user_id, status)

        return items, total

    def get(self, task_id: str, user_id: str) -> dict | None:
        """获取任务详情

        Args:
            task_id: 任务 ID
            user_id: 用户 ID

        Returns:
            任务数据（dict）
        """
        logger.info(f"Get extract task: task_id={task_id}")

        from app.infrastructure.persistence.postgres import get_postgres_client

        pg = get_postgres_client()
        return pg.get_extract_task(task_id, user_id)

    def edit(
        self,
        task_id: str,
        user_id: str,
        company: str,
        position: str,
        questions: List[dict],
    ) -> dict | None:
        """编辑任务结果

        Args:
            task_id: 任务 ID
            user_id: 用户 ID
            company: 公司名称
            position: 岗位名称
            questions: 题目列表

        Returns:
            更新后的任务数据
        """
        logger.info(f"Edit extract task: task_id={task_id}")

        from app.infrastructure.persistence.postgres import get_postgres_client

        pg = get_postgres_client()

        # 验证任务状态
        task_data = pg.get_extract_task(task_id, user_id)
        if not task_data:
            return None

        if task_data.status != "completed":
            raise ValueError("仅可编辑已完成的任务")

        # 更新编辑
        return pg.update_extract_task_edit(
            task_id=task_id,
            user_id=user_id,
            company=company,
            position=position,
            questions=questions,
        )

    async def confirm(self, task_id: str, user_id: str) -> dict:
        """确认入库

        流程：
        1. 验证任务状态（必须 completed）
        2. 获取提取结果
        3. 调用 IngestionService 入库题目
        4. 更新任务状态为 confirmed

        Args:
            task_id: 任务 ID
            user_id: 用户 ID

        Returns:
            入库结果
        """
        logger.info(f"Confirm extract task: task_id={task_id}")

        from app.infrastructure.persistence.postgres import get_postgres_client
        from app.application.services.ingestion_service import get_ingestion_service

        pg = get_postgres_client()

        # 1. 验证任务
        task_data = pg.get_extract_task(task_id, user_id)
        if not task_data:
            raise ValueError("任务不存在")

        if task_data.status != "completed":
            raise ValueError("仅可确认已完成的任务")

        if not task_data.result:
            raise ValueError("任务无解析结果")

        # 2. 调用 IngestionService 入库题目
        ingestion_service = get_ingestion_service()
        result = await ingestion_service.ingest_from_interview_data(
            task_data.result.model_dump()
        )

        # 3. 更新任务状态为 confirmed（ExtractTaskService 负责状态管理）
        pg.update_extract_task_status(task_id, "confirmed")

        logger.info(f"Task {task_id} confirmed, processed={result.processed}")

        return {
            "processed": result.processed,
            "async_tasks": result.async_tasks,
            "question_ids": result.question_ids,
        }

    def delete(self, task_id: str, user_id: str) -> bool:
        """删除任务

        Args:
            task_id: 任务 ID
            user_id: 用户 ID

        Returns:
            是否成功删除
        """
        logger.info(f"Delete extract task: task_id={task_id}")

        from app.infrastructure.persistence.postgres import get_postgres_client

        pg = get_postgres_client()
        return pg.delete_extract_task(task_id, user_id)


def get_extract_task_service() -> ExtractTaskApplicationService:
    """获取提取任务应用服务实例"""
    from app.infrastructure.persistence.postgres.extract_task_repository import (
        get_extract_task_repository,
    )

    repository = get_extract_task_repository()
    return ExtractTaskApplicationService(repository)


__all__ = [
    "ExtractTaskApplicationService",
    "get_extract_task_service",
]