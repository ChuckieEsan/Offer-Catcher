"""Prompt 模板加载工具

底层服务由 infrastructure/common/prompt 提供。
此模块仅提供向后兼容的导入转发。
"""

from app.infrastructure.common.prompt import (
    load_prompt_template,
    build_prompt,
    load_prompt_content,
)

__all__ = [
    "load_prompt_template",
    "build_prompt",
    "load_prompt_content",
]