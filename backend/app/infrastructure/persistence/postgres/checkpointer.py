"""LangGraph PostgreSQL Checkpointer 管理模块

提供 AsyncPostgresSaver 管理，用于 LangGraph 工作流持久化。
作为基础设施层持久化组件，为应用层提供 LangGraph 状态持久化服务。
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger


@asynccontextmanager
async def get_checkpointer() -> AsyncGenerator[AsyncPostgresSaver, None]:
    """获取 AsyncPostgresSaver 上下文管理器

    使用方式：
        async with get_checkpointer() as checkpointer:
            workflow = create_workflow(checkpointer=checkpointer)
            result = await workflow.ainvoke(state, config)

    Yields:
        AsyncPostgresSaver 实例
    """
    settings = get_settings()
    db_uri = settings.postgres_url

    logger.debug(
        f"Creating AsyncPostgresSaver: "
        f"{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )

    async with AsyncPostgresSaver.from_conn_string(db_uri, pipeline=False) as checkpointer:
        await checkpointer.setup()
        yield checkpointer


async def init_checkpointer() -> bool:
    """初始化 checkpointer 表结构

    用于应用启动时预初始化表结构。

    Returns:
        是否成功
    """
    try:
        async with get_checkpointer() as checkpointer:
            logger.info("AsyncPostgresSaver tables initialized")
            return True
    except Exception as e:
        logger.error(f"Failed to initialize checkpointer: {e}")
        return False


__all__ = [
    "get_checkpointer",
    "init_checkpointer",
]