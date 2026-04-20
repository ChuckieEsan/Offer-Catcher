"""pytest 配置文件补充 - 记忆模块 Fixtures

为记忆模块测试提供共享 fixtures。
"""

import os
import uuid
import pytest
from unittest.mock import MagicMock, AsyncMock


# ============================================================================
# Memory Fixtures
# ============================================================================


@pytest.fixture
def test_user_id():
    """测试用户 ID"""
    return f"test_memory_user_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_conversation_id():
    """测试对话 ID"""
    return f"test_conv_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def mock_embedding_adapter():
    """Mock Embedding 适配器"""
    mock = MagicMock()
    mock.embed.return_value = [0.1] * 1024
    return mock


@pytest.fixture
def mock_redis_client():
    """Mock Redis 客户端"""
    mock = MagicMock()
    mock.get.return_value = None
    mock.set.return_value = True
    return mock


@pytest.fixture
def mock_postgres_store():
    """Mock PostgresStore"""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.put = AsyncMock()
    mock.setup = AsyncMock()
    return mock


@pytest.fixture
def sample_memory_content(test_user_id):
    """样本 MEMORY.md 内容"""
    return f"""---
name: user-memory-{test_user_id}
description: 用户特定的偏好和行为规则。
---

# 用户记忆

## 偏好概要
- 语言：中文
- 解释深度：适中
- 代码示例：根据问题需要

## 行为模式概要
（暂无观察到的行为模式）

## 会话历史概要
（暂无历史会话）

## 可用 References
| Reference | 描述 | 建议调用时机 |
|-----------|------|-------------|
| `preferences` | 完整的用户偏好设置 | 用户表达反馈 |
| `behaviors` | 观察到的行为模式详情 | Agent 调整响应策略 |
"""


@pytest.fixture
def sample_preferences_content():
    """样本 preferences.md 内容"""
    return """# 用户偏好详情

## 响应风格
- 语言：中文
- 解释深度：适中
- 响应长度：适中
- 代码示例：根据问题需要

## 话题偏好
（暂无话题特定偏好）

## 反馈历史
（暂无反馈记录）
"""


@pytest.fixture
def sample_behaviors_content():
    """样本 behaviors.md 内容"""
    return """# 用户行为模式详情

（暂无观察到的行为模式）

系统会根据对话自动分析以下方面：
- 提问序列模式
- 关注焦点偏好
- 追问风格
- 知识背景推测
"""


@pytest.fixture
def sample_session_summary(test_user_id, test_conversation_id):
    """样本 SessionSummary 实体"""
    from app.domain.memory.aggregates import SessionSummary

    return SessionSummary.create(
        id=str(uuid.uuid4()),
        conversation_id=test_conversation_id,
        user_id=test_user_id,
        summary="用户询问了 RAG 的召回阈值设置，讨论了 0.7-0.85 的推荐范围。",
        embedding=[0.1] * 1024,
    )