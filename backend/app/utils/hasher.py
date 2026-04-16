"""哈希工具模块

底层服务由 infrastructure/common/hasher 提供。
此模块仅提供向后兼容的导入转发。
"""

from app.domain.question.utils import (
    generate_question_id,
    generate_short_id,
    verify_question_id,
)

__all__ = [
    "generate_question_id",
    "generate_short_id",
    "verify_question_id",
]