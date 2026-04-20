"""Memory Tools for Main Agent

定义主 Agent（Chat Agent）可用的记忆工具。
使用 @tool 装饰器定义 LangChain Tools。

工具列表：
- load_memory_reference: 加载 preferences/behaviors 详情
- search_session_history: 语义检索历史会话
- load_skill: 加载用户自定义 Skill
"""

from langchain_core.tools import tool

from app.infrastructure.common.logger import logger
from app.infrastructure.adapters.embedding_adapter import get_embedding_adapter


@tool
def load_memory_reference(reference_name: str) -> str:
    """加载用户记忆的详细信息

    Args:
        reference_name: "preferences" 或 "behaviors"

    Returns:
        reference 文件的完整内容（Markdown 格式）
    """
    # 从 ToolRuntime 获取 user_id（需要在 Agent 中配置 context_schema）
    # 这里使用临时方案：从全局上下文获取
    user_id = "default_user"  # 临时默认值

    from app.infrastructure.persistence.postgres import get_memory_repository

    with get_memory_repository() as repo:
        content = repo.read_reference(user_id, reference_name)

    if content:
        logger.info(f"Reference '{reference_name}' loaded for user {user_id}")
        return content
    else:
        return f"未找到 reference: {reference_name}"


@tool
def search_session_history(query: str, top_k: int = 3) -> str:
    """语义检索会话历史

    Args:
        query: 查询文本
        top_k: 返回数量（默认 3）

    Returns:
        相关会话的摘要内容（Markdown 格式）
    """
    from app.infrastructure.persistence.postgres import get_session_summary_repository
    from app.infrastructure.persistence.postgres.conversation_repository import get_conversation_repository

    user_id = "default_user"  # 临时默认值

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
def load_skill(skill_name: str) -> str:
    """加载用户自定义 Skill

    Args:
        skill_name: Skill 名称

    Returns:
        SKILL.md 内容（Markdown 格式）
    """
    from app.infrastructure.persistence.postgres import get_memory_repository

    user_id = "default_user"  # 临时默认值

    with get_memory_repository() as repo:
        skill_md = repo.read_skill(user_id, skill_name)

        if not skill_md:
            return f"未找到 Skill: {skill_name}"

        logger.info(f"Skill '{skill_name}' loaded for user {user_id}")
        return skill_md


def get_memory_tools() -> list:
    """获取记忆工具列表

    Returns:
        记忆工具列表
    """
    return [
        load_memory_reference,
        search_session_history,
        load_skill,
    ]


__all__ = [
    "load_memory_reference",
    "search_session_history",
    "load_skill",
    "get_memory_tools",
]