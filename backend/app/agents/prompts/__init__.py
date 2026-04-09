"""Prompt 模板加载器

提供 Prompt 模板的加载和渲染功能。
"""

from pathlib import Path
from typing import Dict, Any

# Prompt 模板目录
PROMPTS_DIR = Path(__file__).parent

# 模板缓存
_template_cache: Dict[str, str] = {}


def load_prompt(name: str) -> str:
    """加载 Prompt 模板

    Args:
        name: 模板名称（不含 .md 后缀）

    Returns:
        模板内容
    """
    if name in _template_cache:
        return _template_cache[name]

    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {name}")

    content = path.read_text(encoding="utf-8")
    _template_cache[name] = content
    return content


def render_prompt(name: str, **kwargs: Any) -> str:
    """渲染 Prompt 模板

    Args:
        name: 模板名称（不含 .md 后缀）
        **kwargs: 模板变量

    Returns:
        渲染后的内容
    """
    template = load_prompt(name)
    return template.format(**kwargs)


__all__ = ["load_prompt", "render_prompt", "PROMPTS_DIR"]