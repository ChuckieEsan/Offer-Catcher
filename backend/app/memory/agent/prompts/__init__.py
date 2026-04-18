"""Memory Agent Prompts 模块

提供 Memory Agent 专用的 Prompt 模板加载功能。
复用 utils/prompt.py 的统一逻辑，注入 PROMPTS_DIR 参数。
"""

from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.prompts import ChatPromptTemplate

from app.infrastructure.common.prompt import load_prompt_template as _load_prompt_template
from app.infrastructure.common.prompt import build_prompt as _build_prompt
from app.infrastructure.common.prompt import load_prompt_content


if TYPE_CHECKING:
    pass


PROMPTS_DIR = Path(__file__).parent


def load_memory_prompt(prompt_filename: str) -> ChatPromptTemplate:
    """加载 Memory Agent Prompt 模板

    Args:
        prompt_filename: Prompt 文件名（如 "memory_agent.md"）

    Returns:
        ChatPromptTemplate 实例
    """
    return _load_prompt_template(prompt_filename, PROMPTS_DIR)


def build_memory_prompt(template_name: str, **kwargs) -> str:
    """构建 Memory Agent Prompt 内容

    Args:
        template_name: 模板文件名
        **kwargs: 模板变量

    Returns:
        格式化后的 Prompt 字符串
    """
    return _build_prompt(template_name, PROMPTS_DIR, **kwargs)


def get_memory_agent_system_prompt() -> str:
    """获取 Memory Agent 的 system_prompt（原始内容）

    用于 create_agent 的 system_prompt 参数。

    Returns:
        memory_agent.md 的原始内容
    """
    return load_prompt_content("memory_agent.md", PROMPTS_DIR)


__all__ = [
    "PROMPTS_DIR",
    "load_memory_prompt",
    "build_memory_prompt",
    "get_memory_agent_system_prompt",
]