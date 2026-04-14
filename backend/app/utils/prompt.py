"""Prompt 模板加载工具

提供统一的 Prompt 加载和构建功能，所有模块应复用此逻辑。

设计要点：
- 核心逻辑在 utils/prompt.py（高内聚）
- 各模块的 prompts/__init__.py 注入 PROMPTS_DIR 参数
- 使用 jinja2 模板格式，避免 JSON 大括号转义问题
"""

from pathlib import Path
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from app.utils.cache import cached
from app.utils.logger import logger


@cached
def load_prompt_template(
    prompt_filename: str,
    prompts_dir: Path,
) -> ChatPromptTemplate:
    """加载 Prompt 模板为 ChatPromptTemplate（带缓存）

    使用 jinja2 模板格式，模板文件使用 {{ variable }} 语法进行变量插值。

    Args:
        prompt_filename: Prompt 文件名（如 "memory_agent.md"）
        prompts_dir: Prompt 文件目录（由各模块传入）

    Returns:
        ChatPromptTemplate 实例

    Example:
        from app.memory.prompts import PROMPTS_DIR
        template = load_prompt_template("memory_agent.md", PROMPTS_DIR)
    """
    prompt_path = prompts_dir / prompt_filename

    if not prompt_path.exists():
        logger.warning(f"Prompt file not found: {prompt_path}")
        return ChatPromptTemplate.from_messages([("system", "")])

    content = prompt_path.read_text(encoding="utf-8")

    return ChatPromptTemplate.from_messages(
        [("system", content)],
        template_format="jinja2",
    )


def build_prompt(
    template_name: str,
    prompts_dir: Path,
    **kwargs: Any,
) -> str:
    """构建格式化的 Prompt 内容

    加载模板并格式化，返回第一条消息的内容。

    Args:
        template_name: 模板文件名（如 "memory_agent.md"）
        prompts_dir: Prompt 文件目录
        **kwargs: 模板变量

    Returns:
        格式化后的 Prompt 字符串

    Example:
        from app.memory.prompts import PROMPTS_DIR
        prompt = build_prompt("memory_agent.md", PROMPTS_DIR, user_id="xxx")
    """
    template = load_prompt_template(template_name, prompts_dir)

    # 过滤 None 值，避免模板渲染错误
    filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None}

    messages = template.format_messages(**filtered_kwargs)

    if messages:
        return messages[0].content
    return ""


def load_prompt_content(
    prompt_filename: str,
    prompts_dir: Path,
) -> str:
    """加载 Prompt 文件的原始内容（不转换为模板）

    用于 create_agent 的 system_prompt 参数。

    Args:
        prompt_filename: Prompt 文件名
        prompts_dir: Prompt 文件目录

    Returns:
        Prompt 文件的原始文本内容
    """
    prompt_path = prompts_dir / prompt_filename

    if not prompt_path.exists():
        logger.warning(f"Prompt file not found: {prompt_path}")
        return ""

    return prompt_path.read_text(encoding="utf-8")


__all__ = [
    "load_prompt_template",
    "build_prompt",
    "load_prompt_content",
]