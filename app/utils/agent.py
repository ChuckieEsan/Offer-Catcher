"""Agent 工具函数模块

提供 Agent 共用的工具函数。
"""

import json
from pathlib import Path
from typing import Any, Optional

from app.utils.logger import logger


def load_prompt(prompt_filename: str) -> str:
    """加载 Prompt 模板

    Args:
        prompt_filename: Prompt 文件名（如 "router.md"）

    Returns:
        Prompt 模板内容
    """
    prompt_path = Path(__file__).parent.parent / "prompts" / prompt_filename
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    logger.warning(f"Prompt file not found: {prompt_path}")
    return ""


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