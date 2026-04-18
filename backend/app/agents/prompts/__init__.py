"""Prompt 模板管理模块

提供 Agent Prompt 的加载和构建功能。
复用 utils/prompt.py 的统一逻辑，注入 PROMPTS_DIR 参数。
"""

from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.prompts import ChatPromptTemplate

from app.infrastructure.common.prompt import load_prompt_template as _load_prompt_template
from app.infrastructure.common.prompt import build_prompt as _build_prompt


if TYPE_CHECKING:
    pass


PROMPTS_DIR = Path(__file__).parent


def load_prompt_template(prompt_filename: str) -> ChatPromptTemplate:
    """加载 Agent Prompt 模板（带缓存）

    复用 utils/prompt.py 的统一逻辑，注入 PROMPTS_DIR。

    Args:
        prompt_filename: Prompt 文件名（如 "react_agent.md"）

    Returns:
        ChatPromptTemplate 实例
    """
    return _load_prompt_template(prompt_filename, PROMPTS_DIR)


def build_prompt(template_name: str, **kwargs) -> str:
    """构建 Agent Prompt 内容

    Args:
        template_name: 模板文件名
        **kwargs: 模板变量

    Returns:
        格式化后的 Prompt 字符串
    """
    return _build_prompt(template_name, PROMPTS_DIR, **kwargs)


__all__ = [
    "PROMPTS_DIR",
    "load_prompt_template",
    "build_prompt",
]