"""Agent 工具函数模块

提供 Agent 共用的工具函数。
"""

import json
from pathlib import Path
from typing import Any, Optional

from langchain_core.prompts import ChatPromptTemplate

from app.utils.cache import cached
from app.utils.logger import logger


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
        formatted = template.format(user_input="你好")
    """
    prompt_path = Path(__file__).parent.parent / "prompts" / prompt_filename

    if not prompt_path.exists():
        logger.warning(f"Prompt file not found: {prompt_path}")
        return ChatPromptTemplate.from_messages([("system", "")])

    content = prompt_path.read_text(encoding="utf-8")

    return ChatPromptTemplate.from_messages(
        [("system", content)],
        template_format="jinja2",
    )


def parse_json_response(
    response: str,
    required_fields: Optional[list[str]] = None,
    default_values: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """解析 LLM 返回的 JSON 响应（降级方案）

    从文本中提取 JSON 并解析，支持缺失字段的默认值处理。

    Args:
        response: LLM 原始响应文本
        required_fields: 必须存在的字段列表，用于验证
        default_values: 缺失字段的默认值

    Returns:
        解析后的字典

    Raises:
        ValueError: JSON 解析失败或缺少必需字段
    """
    if default_values is None:
        default_values = {}

    try:
        # 提取 JSON
        json_start = response.find("{")
        json_end = response.rfind("}") + 1

        if json_start == -1 or json_end == 0:
            raise ValueError("No JSON found in response")

        json_str = response[json_start:json_end]
        data = json.loads(json_str)

        # 检查必需字段
        if required_fields:
            missing = [f for f in required_fields if f not in data]
            if missing:
                raise ValueError(f"Missing required fields: {missing}")

        # 填充默认值
        for key, default_value in default_values.items():
            if key not in data:
                data[key] = default_value

        return data

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        logger.error(f"Response: {response}")
        raise
    except Exception as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.error(f"Response: {response}")
        raise


__all__ = ["load_prompt_template", "parse_json_response"]