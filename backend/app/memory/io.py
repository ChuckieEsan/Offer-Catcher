"""记忆读写接口

提供用户记忆文件的读写操作。

命名空间结构（LangGraph PostgresStore 不允许命名空间标签包含点号）：
    ("memory", user_id) → MEMORY（对应 MEMORY.md）
    ("memory", user_id, "references", "preferences") → preferences（对应 preferences.md）
    ("memory", user_id, "references", "behaviors") → behaviors（对应 behaviors.md）
    ("memory", user_id, "references", "skills", skill_name, "SKILL") → SKILL（对应 SKILL.md）
"""

from app.memory.store import get_memory_store
from app.infrastructure.common.logger import logger


# 键名转换函数（LangGraph PostgresStore 不允许命名空间标签包含点号）
def _to_store_key(filename: str) -> str:
    """将文件名转换为存储键名（去掉 .md 扩展名）

    Args:
        filename: 文件名（如 "MEMORY.md", "SKILL.md"）

    Returns:
        存储键名（如 "MEMORY", "SKILL"）
    """
    if filename.endswith(".md"):
        return filename[:-3]
    return filename


def _from_store_key(store_key: str) -> str:
    """将存储键名转换回文件名（添加 .md 扩展名）

    Args:
        store_key: 存储键名（如 "MEMORY", "SKILL"）

    Returns:
        文件名（如 "MEMORY.md", "SKILL.md")
    """
    if not store_key.endswith(".md"):
        return store_key + ".md"
    return store_key


def read_memory(user_id: str) -> str:
    """读取用户 MEMORY.md 主文档

    Args:
        user_id: 用户 ID

    Returns:
        MEMORY.md 内容，不存在时返回空字符串
    """
    store = get_memory_store()
    if not store.initialized:
        logger.warning("MemoryStore not initialized, returning empty content")
        return ""

    try:
        with store._get_store() as pg_store:
            # 使用不带点号的键名
            result = pg_store.get(
                ("memory", user_id),
                "MEMORY",
            )
            if result and result.value:
                return result.value.get("content", "")
            return ""
    except Exception as e:
        logger.error(f"Failed to read MEMORY.md for user {user_id}: {e}")
        return ""


def write_memory(user_id: str, content: str) -> None:
    """写入用户 MEMORY.md 主文档

    Args:
        user_id: 用户 ID
        content: MEMORY.md 内容
    """
    store = get_memory_store()
    if not store.initialized:
        logger.warning("MemoryStore not initialized, skipping write_memory")
        return

    try:
        with store._get_store() as pg_store:
            # 使用不带点号的键名
            pg_store.put(
                ("memory", user_id),
                "MEMORY",
                {"content": content},
            )
        logger.info(f"Written MEMORY.md for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to write MEMORY.md for user {user_id}: {e}")


def read_memory_reference(user_id: str, reference_name: str) -> str:
    """读取用户记忆 reference 文件

    Args:
        user_id: 用户 ID
        reference_name: reference 名称（如 "preferences", "behaviors", "skills/interview_tips/SKILL.md"）

    Returns:
        reference 文件内容，不存在时返回空字符串
    """
    store = get_memory_store()
    if not store.initialized:
        logger.warning("MemoryStore not initialized, returning empty content")
        return ""

    try:
        with store._get_store() as pg_store:
            # 构建命名空间，将各部分的 .md 扩展名去掉
            # reference_name 可能是 "preferences" 或 "skills/interview_tips/SKILL.md"
            parts = reference_name.split("/")
            namespace_parts = [_to_store_key(p) for p in parts]
            namespace = ("memory", user_id, "references", *namespace_parts)
            # 键名也需要去掉 .md 扩展名
            store_key = _to_store_key(reference_name)

            result = pg_store.get(namespace, store_key)
            if result and result.value:
                return result.value.get("content", "")
            return ""
    except Exception as e:
        logger.error(f"Failed to read reference {reference_name} for user {user_id}: {e}")
        return ""


def write_memory_reference(user_id: str, reference_name: str, content: str) -> None:
    """写入用户记忆 reference 文件

    Args:
        user_id: 用户 ID
        reference_name: reference 名称（如 "preferences", "behaviors", "skills/interview_tips/SKILL.md"）
        content: reference 文件内容
    """
    store = get_memory_store()
    if not store.initialized:
        logger.warning("MemoryStore not initialized, skipping write_memory_reference")
        return

    try:
        with store._get_store() as pg_store:
            # 构建命名空间，将各部分的 .md 扩展名去掉
            parts = reference_name.split("/")
            namespace_parts = [_to_store_key(p) for p in parts]
            namespace = ("memory", user_id, "references", *namespace_parts)
            # 键名也需要去掉 .md 扩展名
            store_key = _to_store_key(reference_name)

            pg_store.put(
                namespace,
                store_key,
                {"content": content},
            )
        logger.info(f"Written reference {reference_name} for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to write reference {reference_name} for user {user_id}: {e}")


def delete_memory_reference(user_id: str, reference_name: str) -> bool:
    """删除用户记忆 reference 文件

    Args:
        user_id: 用户 ID
        reference_name: reference 名称

    Returns:
        是否成功删除
    """
    store = get_memory_store()
    if not store.initialized:
        logger.warning("MemoryStore not initialized, skipping delete_memory_reference")
        return False

    try:
        with store._get_store() as pg_store:
            # 构建命名空间，将各部分的 .md 扩展名去掉
            parts = reference_name.split("/")
            namespace_parts = [_to_store_key(p) for p in parts]
            namespace = ("memory", user_id, "references", *namespace_parts)
            store_key = _to_store_key(reference_name)

            # PostgresStore 没有 delete 方法，需要通过 put 写入空值或 None
            # 实际上 LangGraph PostgresStore 没有直接的 delete API
            # 这里我们写入空内容作为"删除"标记
            pg_store.put(
                namespace,
                store_key,
                {"content": ""},
            )
        logger.info(f"Deleted reference {reference_name} for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete reference {reference_name} for user {user_id}: {e}")
        return False


def list_memory_references(user_id: str) -> list[str]:
    """列出用户所有 reference 文件

    Args:
        user_id: 用户 ID

    Returns:
        reference 名称列表（带 .md 扩展名）
    """
    store = get_memory_store()
    if not store.initialized:
        logger.warning("MemoryStore not initialized, returning empty list")
        return []

    try:
        with store._get_store() as pg_store:
            results = pg_store.search(
                ("memory", user_id, "references"),
                limit=100,
            )
            references = []
            for r in results:
                if r.value and r.value.get("content"):
                    # 将存储键名转换回文件名格式
                    references.append(_from_store_key(r.key))
            return references
    except Exception as e:
        logger.error(f"Failed to list references for user {user_id}: {e}")
        return []


def memory_exists(user_id: str) -> bool:
    """检查用户记忆是否存在

    Args:
        user_id: 用户 ID

    Returns:
        MEMORY.md 是否存在
    """
    return read_memory(user_id) != ""


__all__ = [
    "read_memory",
    "write_memory",
    "read_memory_reference",
    "write_memory_reference",
    "delete_memory_reference",
    "list_memory_references",
    "memory_exists",
]