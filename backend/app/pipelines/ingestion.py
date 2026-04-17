"""入库流水线模块

底层服务由 application/services/ingestion_service 提供。
此模块仅提供向后兼容的导入转发。
"""

from app.application.services.ingestion_service import (
    IngestionApplicationService,
    IngestionResult,
    get_ingestion_service,
)

# 向后兼容：IngestionPipeline 转发到 IngestionApplicationService
class IngestionPipeline(IngestionApplicationService):
    """向后兼容的入库流水线类

    转发所有方法到 IngestionApplicationService。
    保留 process 方法名作为 ingest_interview 的别名。
    """

    async def process(self, interview) -> IngestionResult:
        """处理入库流水线（向后兼容别名）

        Args:
            interview: 面试经验数据

        Returns:
            入库结果
        """
        return await self.ingest_interview(interview)


def get_ingestion_pipeline() -> IngestionPipeline:
    """获取入库流水线单例（向后兼容）

    Returns:
        IngestionPipeline 实例
    """
    return IngestionPipeline()


__all__ = [
    "IngestionPipeline",
    "IngestionResult",
    "get_ingestion_pipeline",
]