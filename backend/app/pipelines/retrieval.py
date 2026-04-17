"""检索流水线模块

底层服务由 application/services/retrieval_service 提供。
此模块仅提供向后兼容的导入转发。
"""

from app.application.services.retrieval_service import (
    RetrievalApplicationService,
    get_retrieval_service,
)


# 向后兼容：RetrievalPipeline 转发到 RetrievalApplicationService
class RetrievalPipeline(RetrievalApplicationService):
    """向后兼容的检索流水线类

    转发所有方法到 RetrievalApplicationService。
    """

    pass


def get_retrieval_pipeline() -> RetrievalPipeline:
    """获取检索流水线单例（向后兼容）

    Returns:
        RetrievalPipeline 实例
    """
    return RetrievalPipeline()


__all__ = [
    "RetrievalPipeline",
    "get_retrieval_pipeline",
]