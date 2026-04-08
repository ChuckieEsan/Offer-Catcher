"""LangGraph PostgreSQL Checkpointer 管理模块

提供 AsyncPostgresSaver 管理，用于 LangGraph 工作流持久化。
使用 psycopg 异步驱动，与现有 postgres_client（psycopg2）共存。

AsyncPostgresSaver 会创建以下表（与现有 conversations/messages 表共存）：
- checkpoints: 存储工作流状态快照
- checkpoint_blobs: 存储大型状态数据
- checkpoint_writes: 存储中间写入

Note:
    AsyncPostgresSaver.from_conn_string() 返回异步上下文管理器，
    需要使用 async with 进入上下文获取 checkpointer 实例。
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config.settings import get_settings
from app.utils.logger import logger


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

    logger.debug(f"Creating AsyncPostgresSaver: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}")

    # from_conn_string 返回异步上下文管理器
    # 使用 pipeline=False 避免 psycopg3 generator 退出时的连接清理问题
    # 参考: https://github.com/psycopg/psycopg/issues/XXX
    async with AsyncPostgresSaver.from_conn_string(db_uri, pipeline=False) as checkpointer:
        # 初始化表结构（首次需要）
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


__all__ = ["get_checkpointer", "init_checkpointer"]