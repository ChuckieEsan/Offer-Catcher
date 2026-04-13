"""记忆模块 Tool

提供用户记忆的加载和语义检索功能。
使用 ToolRuntime 注入 user_id，支持多用户场景。

Tool 设计：
- load_memory_reference: 加载 preferences/behaviors 详情
- search_session_history: 语义检索会话历史

遵循设计方案：
- MEMORY.md 始终加载（注入到 System Prompt）
- references 按需查询（通过 Tool）
- session_summaries 支持语义检索
"""

from typing import Annotated

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel, Field

from app.db.postgres_client import get_postgres_client
from app.memory.io import (
    read_memory_reference,
    memory_exists,
)
from app.memory.init import ensure_user_memory
from app.memory.store import get_memory_store
from app.tools.embedding_tool import get_embedding_tool
from app.tools.context import UserContext
from app.utils.logger import logger


# ==================== 输入模型 ====================

class LoadMemoryReferenceInput(BaseModel):
    """load_memory_reference 工具的输入参数"""
    reference_name: str = Field(
        description="Reference 名称：'preferences' 或 'behaviors'"
    )


class SearchSessionHistoryInput(BaseModel):
    """search_session_history 工具的输入参数"""
    query: str = Field(
        description="查询文本，用于语义检索相关会话"
    )
    top_k: int = Field(
        default=3,
        description="返回的会话数量，默认 3"
    )


# ==================== Tool 实现 ====================

@tool(args_schema=LoadMemoryReferenceInput)
def load_memory_reference(
    reference_name: str,
    runtime: Annotated[ToolRuntime[UserContext], InjectedToolArg] = None,
) -> str:
    """加载用户记忆的详细信息。

    当 MEMORY.md 中的概要信息不足以回答问题时，使用此工具查询详情。

    Args:
        reference_name: Reference 名称，可选值：
            - 'preferences': 用户偏好详情（响应风格、话题偏好、反馈历史）
            - 'behaviors': 用户行为模式详情（提问序列、关注焦点、追问风格）

    Returns:
        Reference 文件的完整内容（Markdown 格式）
    """
    user_id = runtime.context.user_id

    # 确保 memory 存在
    if not memory_exists(user_id):
        store = get_memory_store()
        if store.initialized:
            ensure_user_memory(user_id)

    # 读取 reference（不带 .md 扩展名）
    content = read_memory_reference(user_id, reference_name)

    if not content:
        return f"未找到 reference '{reference_name}'。可用 references：preferences, behaviors"

    return content


@tool(args_schema=SearchSessionHistoryInput)
def search_session_history(
    query: str,
    top_k: int = 3,
    runtime: Annotated[ToolRuntime[UserContext], InjectedToolArg] = None,
) -> str:
    """语义检索会话历史。

    当需要查找过去对话中的特定话题或问题时使用。

    Args:
        query: 查询文本，如 "RAG 原理讨论"、"面试模拟复盘"
        top_k: 返回的会话数量，默认 3

    Returns:
        相关会话的摘要内容（Markdown 格式），包含会话标题、时间和摘要
    """
    user_id = runtime.context.user_id

    try:
        # 1. 计算 query embedding
        embedding_tool = get_embedding_tool()
        query_embedding = embedding_tool.embed_text(query)

        # 2. 语义检索 session_summaries
        pg_client = get_postgres_client()
        results = pg_client.search_session_summaries(
            user_id=user_id,
            query_embedding=query_embedding,
            top_k=top_k,
        )

        if not results:
            return "未找到相关的历史会话。"

        # 3. 格式化输出
        output_lines = ["### 相关会话历史\n"]

        for r in results:
            # 获取对话标题
            conv = pg_client.get_conversation(user_id, r.conversation_id)
            title = conv.title if conv else "未知对话"
            created_at = conv.created_at.strftime("%Y-%m-%d") if conv else ""

            output_lines.append(f"#### {title} ({created_at})")
            output_lines.append(f"相似度：{r.similarity:.2f}")
            output_lines.append(f"类型：{r.session_type}")
            output_lines.append(f"\n摘要：\n{r.summary}\n")
            output_lines.append("---\n")

        return "\n".join(output_lines)

    except Exception as e:
        logger.error(f"search_session_history failed: {e}")
        return f"检索会话历史失败：{e}"


# ==================== Phase 3: 用户自定义 Skill Tool ====================

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
        SKILL.md + references 的完整内容（Markdown 格式）
    """
    user_id = runtime.context.user_id

    # 确保 memory 存在
    if not memory_exists(user_id):
        store = get_memory_store()
        if store.initialized:
            ensure_user_memory(user_id)

    # 读取 SKILL（存储键名不带 .md）
    skill_content = read_memory_reference(user_id, f"skills/{skill_name}/SKILL")

    if not skill_content:
        return f"未找到 Skill '{skill_name}'。请检查 Skill 名称或通过 UI 创建。"

    # TODO: Phase 3 完成后，加载 references 目录下的文件
    # 目前只返回 SKILL.md 内容

    return skill_content


__all__ = [
    "load_memory_reference",
    "search_session_history",
    "load_skill",
    "LoadMemoryReferenceInput",
    "SearchSessionHistoryInput",
    "LoadSkillInput",
    "UserContext",
]