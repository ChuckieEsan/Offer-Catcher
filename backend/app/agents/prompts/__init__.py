"""Prompt 模板管理模块

提供统一的 Prompt 加载和构建功能，所有 Agent 应复用此模块。
"""

from pathlib import Path
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from app.utils.cache import cached
from app.utils.logger import logger


PROMPTS_DIR = Path(__file__).parent


@cached
def load_prompt_template(prompt_filename: str) -> ChatPromptTemplate:
    """加载 Prompt 模板为 ChatPromptTemplate（带缓存）

    使用 jinja2 模板格式，避免 JSON 大括号转义问题。
    模板文件使用 {{ variable }} 语法进行变量插值。

    Args:
        prompt_filename: Prompt 文件名（如 "router.md"）

    Returns:
        ChatPromptTemplate 实例

    Example:
        template = load_prompt_template("router.md")
        messages = template.format_messages(user_input="你好")
    """
    prompt_path = PROMPTS_DIR / prompt_filename

    if not prompt_path.exists():
        logger.warning(f"Prompt file not found: {prompt_path}")
        return ChatPromptTemplate.from_messages([("system", "")])

    content = prompt_path.read_text(encoding="utf-8")

    return ChatPromptTemplate.from_messages(
        [("system", content)],
        template_format="jinja2",
    )


def build_prompt(template_name: str, **kwargs: Any) -> str:
    """构建格式化的 Prompt 内容

    加载模板并格式化，返回第一条消息的内容。
    所有 Agent 应使用此函数统一构建 Prompt。

    Args:
        template_name: 模板文件名（如 "interviewer_system.md"）
        **kwargs: 模板变量

    Returns:
        格式化后的 Prompt 字符串

    Example:
        prompt = build_prompt("scorer.md", question_text="什么是微服务?", score=85)
    """
    template = load_prompt_template(template_name)

    # 过滤 None 值，避免模板渲染错误
    filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None}

    messages = template.format_messages(**filtered_kwargs)

    if messages:
        return messages[0].content
    return ""


__all__ = ["load_prompt_template", "build_prompt", "PROMPTS_DIR"]