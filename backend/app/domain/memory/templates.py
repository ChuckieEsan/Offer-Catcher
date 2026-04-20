"""Memory 默认模板

提供 MEMORY.md、preferences.md、behaviors.md 的默认模板。
遵循 Agent Skills 标准格式。
"""

# MEMORY.md 默认模板
MEMORY_MD_TEMPLATE = """---
name: user-memory-{user_id}
description: 用户特定的偏好和行为规则。始终加载此文档。
             当概要信息不足以回答问题时，使用 load_memory_reference Tool
             或 search_session_history Tool 查询详情。
---

# 用户记忆

## 偏好概要
- 语言：中文
- 解释深度：适中
- 代码示例：根据问题需要

## 行为模式概要
（暂无观察到的行为模式，将在对话后自动积累）

## 会话历史概要
（暂无历史会话）

## 可用 References
| Reference | 描述 | 建议调用时机 |
|-----------|------|-------------|
| `preferences` | 完整的用户偏好设置 | 用户表达反馈 |
| `behaviors` | 观察到的行为模式详情 | Agent 调整响应策略 |

## 可用自定义 Skill
（暂无自定义 Skill，可通过 UI 创建）

## 使用指南
1. 本文档始终加载，提供概要信息
2. 概要不够详细时，调用 `load_memory_reference` 加载详情
3. 需要语义检索历史时，调用 `search_session_history` 搜索
4. 触发自定义 Skill 时，调用 `load_skill` 加载
"""

# preferences.md 默认模板
PREFERENCES_TEMPLATE = """# 用户偏好详情

## 响应风格
- 语言：中文
- 解释深度：适中
- 响应长度：适中
- 代码示例：根据问题需要

## 话题偏好
（暂无话题特定偏好，将在用户反馈后自动积累）

## 反馈历史
（暂无反馈记录）
"""

# behaviors.md 默认模板
BEHAVIORS_TEMPLATE = """# 用户行为模式详情

（暂无观察到的行为模式，将在对话后自动积累）

系统会根据对话自动分析以下方面：
- 提问序列模式
- 关注焦点偏好
- 追问风格
- 知识背景推测
"""


def get_memory_template(user_id: str) -> str:
    """获取用户 MEMORY.md 模板

    Args:
        user_id: 用户唯一标识

    Returns:
        MEMORY.md 模板内容
    """
    return MEMORY_MD_TEMPLATE.replace("{user_id}", user_id)


def get_preferences_template() -> str:
    """获取 preferences.md 模板

    Returns:
        preferences.md 模板内容
    """
    return PREFERENCES_TEMPLATE


def get_behaviors_template() -> str:
    """获取 behaviors.md 模板

    Returns:
        behaviors.md 模板内容
    """
    return BEHAVIORS_TEMPLATE


__all__ = [
    "MEMORY_MD_TEMPLATE",
    "PREFERENCES_TEMPLATE",
    "BEHAVIORS_TEMPLATE",
    "get_memory_template",
    "get_preferences_template",
    "get_behaviors_template",
]