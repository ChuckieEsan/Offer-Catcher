"""Memory Tools for Main Agent

定义主 Agent（Chat Agent）可用的记忆工具。
使用 @tool 装饰器定义 LangChain Tools。

工具列表：
- load_memory_reference: 加载 preferences/behaviors 详情
- search_session_history: 语义检索历史会话
- load_skill: 加载用户自定义 Skill
- update_preferences: 更新用户偏好设置
- update_behaviors: 更新用户行为模式

写入记忆时返回 <memory_write> 标记，后台 Agent 检测到后会跳过处理。

使用 ToolRuntime.context 获取 UserContext 中的 user_id。
"""

from langchain.tools import tool, ToolRuntime
from typing import TYPE_CHECKING

from app.infrastructure.common.logger import logger
from app.infrastructure.adapters.embedding_adapter import get_embedding_adapter

if TYPE_CHECKING:
    from app.application.agents.chat.runtime import UserContext


@tool
def load_memory_reference(reference_name: str, runtime: ToolRuntime) -> str:
    """加载用户记忆的详细信息

    Args:
        reference_name: "preferences" 或 "behaviors"

    Returns:
        reference 文件的完整内容（Markdown 格式）
    """
    user_id = runtime.context.user_id

    from app.infrastructure.persistence.postgres import get_memory_repository

    with get_memory_repository() as repo:
        content = repo.read_reference(user_id, reference_name)

    if content:
        logger.info(f"Reference '{reference_name}' loaded for user {user_id}")
        return content
    else:
        return f"未找到 reference: {reference_name}"


@tool
def search_session_history(query: str, runtime: ToolRuntime, top_k: int = 3) -> str:
    """语义检索会话历史

    Args:
        query: 查询文本
        top_k: 返回数量（默认 3）

    Returns:
        相关会话的摘要内容（Markdown 格式）
    """
    from app.infrastructure.persistence.postgres import get_session_summary_repository
    from app.infrastructure.persistence.postgres.conversation_repository import get_conversation_repository

    user_id = runtime.context.user_id

    # 计算 embedding
    embedding_adapter = get_embedding_adapter()
    query_embedding = embedding_adapter.embed(query)

    # 检索摘要
    repo = get_session_summary_repository()
    results = repo.search_by_embedding(user_id, query_embedding, top_k)

    if not results:
        return "未找到相关历史会话"

    # 获取对话标题
    conv_repo = get_conversation_repository()

    output_lines = ["### 相关历史会话\n"]

    for r in results:
        conv = conv_repo.find_by_id(user_id, r.conversation_id)
        title = conv.title if conv else "未知对话"
        created_at = r.created_at.strftime("%Y-%m-%d")

        output_lines.append(f"#### {title} ({created_at})")
        output_lines.append(r.summary)
        output_lines.append("")

    return "\n".join(output_lines)


@tool
def load_skill(skill_name: str, runtime: ToolRuntime) -> str:
    """加载用户自定义 Skill

    Args:
        skill_name: Skill 名称

    Returns:
        SKILL.md 内容（Markdown 格式）
    """
    from app.infrastructure.persistence.postgres import get_memory_repository

    user_id = runtime.context.user_id

    with get_memory_repository() as repo:
        skill_md = repo.read_skill(user_id, skill_name)

        if not skill_md:
            return f"未找到 Skill: {skill_name}"

        logger.info(f"Skill '{skill_name}' loaded for user {user_id}")
        return skill_md


@tool
def update_preferences(content: str, runtime: ToolRuntime) -> str:
    """更新用户偏好设置

    Args:
        content: 完整的 preferences.md 内容（整合现有内容和新反馈）

    Returns:
        操作结果（包含 memory_write 标记，后台 Agent 会跳过处理）
    """
    from app.application.services.memory_service import get_memory_service

    user_id = runtime.context.user_id

    # 使用 MemoryService 更新（包含同步 MEMORY.md）
    service = get_memory_service()
    service.update_preferences(user_id, content)

    logger.info(f"preferences.md updated by Main Agent for user {user_id}")

    # 返回带标记的结果（后台 Agent 检测到此标记后跳过处理）
    return "<memory_write>preferences</memory_write>\n偏好设置已更新"


@tool
def update_behaviors(content: str, runtime: ToolRuntime) -> str:
    """更新用户行为模式

    Args:
        content: 完整的 behaviors.md 内容（整合现有内容和新观察）

    Returns:
        操作结果（包含 memory_write 标记，后台 Agent 会跳过处理）
    """
    from app.application.services.memory_service import get_memory_service

    user_id = runtime.context.user_id

    # 使用 MemoryService 更新（包含同步 MEMORY.md）
    service = get_memory_service()
    service.update_behaviors(user_id, content)

    logger.info(f"behaviors.md updated by Main Agent for user {user_id}")

    # 返回带标记的结果（后台 Agent 检测到此标记后跳过处理）
    return "<memory_write>behaviors</memory_write>\n行为模式已更新"


def get_memory_tools() -> list:
    """获取记忆工具列表

    Returns:
        记忆工具列表（读取 + 写入）
    """
    return [
        load_memory_reference,
        search_session_history,
        load_skill,
        update_preferences,
        update_behaviors,
    ]


__all__ = [
    "load_memory_reference",
    "search_session_history",
    "load_skill",
    "update_preferences",
    "update_behaviors",
    "get_memory_tools",
]