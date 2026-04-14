"""用户自定义 Skill 模块

Skill 是用户创建的知识片段，用于指导 Agent 在特定场景下的行为。
遵循 Agent Skills 标准（https://agentskills.io/specification）。

结构：
    skills/{skill_name}/
    ├── SKILL.md              # 必须：包含 name + description + 指令
    └── references/           # 可选：详情文档

存储：
    通过 memory.io 访问，命名空间：
    ("memory", user_id, "references", "skills", skill_name, "SKILL")

使用方式：
    from app.skills import load_skill, list_skills
    skill_content = load_skill(user_id, "interview_tips")
"""

from typing import Annotated

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel, Field

from app.memory.io import read_memory_reference, memory_exists
from app.memory.init import ensure_user_memory
from app.memory.store import get_memory_store
from app.tools.context import UserContext
from app.utils.logger import logger


# ==================== Skill 加载 ====================


def load_skill_content(user_id: str, skill_name: str) -> str:
    """加载用户自定义 Skill 内容

    Args:
        user_id: 用户 ID
        skill_name: Skill 名称

    Returns:
        SKILL.md 的内容，不存在时返回空字符串
    """
    # 确保 memory 存在
    if not memory_exists(user_id):
        store = get_memory_store()
        if store.initialized:
            ensure_user_memory(user_id)

    # 读取 SKILL（存储键名不带 .md）
    skill_content = read_memory_reference(user_id, f"skills/{skill_name}/SKILL")

    if not skill_content:
        logger.warning(f"Skill '{skill_name}' not found for user {user_id}")
        return ""

    return skill_content


def list_user_skills(user_id: str) -> list[str]:
    """列出用户所有 Skill

    Args:
        user_id: 用户 ID

    Returns:
        Skill 名称列表
    """
    from app.memory.io import list_memory_references

    references = list_memory_references(user_id)

    # 过滤出 skills 目录下的 SKILL.md
    skills = []
    for ref in references:
        if ref.startswith("skills/") and ref.endswith("/SKILL.md"):
            # 提取 skill_name
            parts = ref.split("/")
            if len(parts) >= 3:
                skills.append(parts[1])

    return skills


# ==================== Tool 定义 ====================


class LoadSkillInput(BaseModel):
    """load_skill 工具的输入参数"""
    skill_name: str = Field(
        description="Skill 名称，如 'interview_tips'"
    )


@tool(args_schema=LoadSkillInput)
def load_skill(
    skill_name: str,
    runtime: Annotated[ToolRuntime[UserContext], InjectedToolArg] = None,
) -> str:
    """加载用户自定义 Skill。

    当触发自定义 Skill 条件时，使用此工具加载完整的 Skill 内容。

    Args:
        skill_name: Skill 名称

    Returns:
        SKILL.md 的内容（Markdown 格式）
    """
    user_id = runtime.context.user_id
    skill_content = load_skill_content(user_id, skill_name)

    if not skill_content:
        return f"未找到 Skill '{skill_name}'。请检查 Skill 名称或通过 UI 创建。"

    return skill_content


__all__ = [
    "load_skill",
    "load_skill_content",
    "list_user_skills",
    "LoadSkillInput",
]