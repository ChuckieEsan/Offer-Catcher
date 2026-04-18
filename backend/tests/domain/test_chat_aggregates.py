"""Chat Domain Aggregates Tests

测试 Conversation 聚合根和 Message 实体的业务逻辑。
"""

import uuid
from datetime import datetime

from app.domain.chat.aggregates import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
)


def test_create_conversation():
    """测试创建对话聚合"""
    conv_id = str(uuid.uuid4())
    user_id = "test_user_001"

    conv = Conversation.create(
        conversation_id=conv_id,
        user_id=user_id,
        title="测试对话",
    )

    assert conv.conversation_id == conv_id
    assert conv.user_id == user_id
    assert conv.title == "测试对话"
    assert conv.status == ConversationStatus.ACTIVE
    assert len(conv.messages) == 0
    assert conv.created_at is not None
    assert conv.updated_at is not None
    print("✅ test_create_conversation passed")


def test_create_conversation_default_title():
    """测试默认标题"""
    conv = Conversation.create(
        conversation_id=str(uuid.uuid4()),
        user_id="user",
    )

    assert conv.title == "新对话"
    print("✅ test_create_conversation_default_title passed")


def test_add_user_message():
    """测试追加用户消息"""
    conv = Conversation.create(
        conversation_id=str(uuid.uuid4()),
        user_id="user",
    )

    msg_id = str(uuid.uuid4())
    msg = conv.add_message(
        message_id=msg_id,
        role=MessageRole.USER,
        content="你好",
    )

    assert msg.message_id == msg_id
    assert msg.role == MessageRole.USER
    assert msg.content == "你好"
    assert len(conv.messages) == 1
    assert conv.updated_at > conv.created_at
    print("✅ test_add_user_message passed")


def test_add_assistant_message():
    """测试追加 AI 回复"""
    conv = Conversation.create(
        conversation_id=str(uuid.uuid4()),
        user_id="user",
    )

    conv.add_message(
        message_id=str(uuid.uuid4()),
        role=MessageRole.USER,
        content="你好",
    )

    conv.add_message(
        message_id=str(uuid.uuid4()),
        role=MessageRole.ASSISTANT,
        content="你好！有什么可以帮助你的？",
    )

    assert len(conv.messages) == 2
    assert conv.messages[0].role == MessageRole.USER
    assert conv.messages[1].role == MessageRole.ASSISTANT
    print("✅ test_add_assistant_message passed")


def test_update_title():
    """测试更新标题"""
    conv = Conversation.create(
        conversation_id=str(uuid.uuid4()),
        user_id="user",
        title="新对话",
    )

    old_updated_at = conv.updated_at
    conv.update_title("面试准备")

    assert conv.title == "面试准备"
    assert conv.updated_at >= old_updated_at
    print("✅ test_update_title passed")


def test_end_conversation():
    """测试结束对话"""
    conv = Conversation.create(
        conversation_id=str(uuid.uuid4()),
        user_id="user",
    )

    conv.add_message(
        message_id=str(uuid.uuid4()),
        role=MessageRole.USER,
        content="问题1",
    )

    conv.end()

    assert conv.status == ConversationStatus.ENDED
    print("✅ test_end_conversation passed")


def test_get_last_message():
    """测试获取最后一条消息"""
    conv = Conversation.create(
        conversation_id=str(uuid.uuid4()),
        user_id="user",
    )

    # 无消息时返回 None
    assert conv.get_last_message() is None

    conv.add_message(
        message_id="msg1",
        role=MessageRole.USER,
        content="消息1",
    )

    conv.add_message(
        message_id="msg2",
        role=MessageRole.ASSISTANT,
        content="消息2",
    )

    last = conv.get_last_message()
    assert last.message_id == "msg2"
    assert last.content == "消息2"
    print("✅ test_get_last_message passed")


def test_get_user_messages():
    """测试获取所有用户消息"""
    conv = Conversation.create(
        conversation_id=str(uuid.uuid4()),
        user_id="user",
    )

    conv.add_message(
        message_id="msg1",
        role=MessageRole.USER,
        content="用户问题",
    )

    conv.add_message(
        message_id="msg2",
        role=MessageRole.ASSISTANT,
        content="AI回复",
    )

    conv.add_message(
        message_id="msg3",
        role=MessageRole.USER,
        content="用户追问",
    )

    user_msgs = conv.get_user_messages()
    assert len(user_msgs) == 2
    assert user_msgs[0].content == "用户问题"
    assert user_msgs[1].content == "用户追问"
    print("✅ test_get_user_messages passed")


def test_get_assistant_messages():
    """测试获取所有 AI 回复"""
    conv = Conversation.create(
        conversation_id=str(uuid.uuid4()),
        user_id="user",
    )

    conv.add_message(
        message_id="msg1",
        role=MessageRole.USER,
        content="问题",
    )

    conv.add_message(
        message_id="msg2",
        role=MessageRole.ASSISTANT,
        content="回复1",
    )

    conv.add_message(
        message_id="msg3",
        role=MessageRole.USER,
        content="追问",
    )

    conv.add_message(
        message_id="msg4",
        role=MessageRole.ASSISTANT,
        content="回复2",
    )

    assistant_msgs = conv.get_assistant_messages()
    assert len(assistant_msgs) == 2
    assert assistant_msgs[0].content == "回复1"
    assert assistant_msgs[1].content == "回复2"
    print("✅ test_get_assistant_messages passed")


def test_message_count():
    """测试消息计数"""
    conv = Conversation.create(
        conversation_id=str(uuid.uuid4()),
        user_id="user",
    )

    assert conv.message_count() == 0

    conv.add_message(
        message_id="msg1",
        role=MessageRole.USER,
        content="问题",
    )

    assert conv.message_count() == 1

    conv.add_message(
        message_id="msg2",
        role=MessageRole.ASSISTANT,
        content="回复",
    )

    assert conv.message_count() == 2
    print("✅ test_message_count passed")


def test_to_dict():
    """测试序列化为字典"""
    conv = Conversation.create(
        conversation_id="conv-001",
        user_id="user-001",
        title="测试对话",
    )

    conv.add_message(
        message_id="msg-001",
        role=MessageRole.USER,
        content="你好",
    )

    data = conv.to_dict()

    assert data["conversation_id"] == "conv-001"
    assert data["user_id"] == "user-001"
    assert data["title"] == "测试对话"
    assert data["status"] == "active"
    assert len(data["messages"]) == 1
    assert data["messages"][0]["message_id"] == "msg-001"
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "你好"
    print("✅ test_to_dict passed")


def test_message_create():
    """测试创建消息实体"""
    msg = Message.create(
        message_id="msg-001",
        role=MessageRole.USER,
        content="测试内容",
    )

    assert msg.message_id == "msg-001"
    assert msg.role == MessageRole.USER
    assert msg.content == "测试内容"
    assert msg.created_at is not None
    print("✅ test_message_create passed")


def test_message_create_with_timestamp():
    """测试带时间戳创建消息"""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0)

    msg = Message.create(
        message_id="msg-001",
        role=MessageRole.USER,
        content="测试内容",
        created_at=fixed_time,
    )

    assert msg.created_at == fixed_time
    print("✅ test_message_create_with_timestamp passed")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("Chat Domain Aggregates Tests")
    print("=" * 60)

    test_create_conversation()
    test_create_conversation_default_title()
    test_add_user_message()
    test_add_assistant_message()
    test_update_title()
    test_end_conversation()
    test_get_last_message()
    test_get_user_messages()
    test_get_assistant_messages()
    test_message_count()
    test_to_dict()
    test_message_create()
    test_message_create_with_timestamp()

    print("=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()