"""PostgreSQL 客户端测试

注意：测试在 test 数据库中进行，避免影响业务数据
"""

import os
import sys
sys.path.insert(0, ".")

# 设置测试环境变量，使用测试数据库
os.environ["POSTGRES_DB"] = "offer_catcher_test"

from app.infrastructure.persistence.postgres import get_postgres_client


def test_connection():
    """测试连接"""
    print("=== 测试 1: 连接 ===")
    client = get_postgres_client()
    print(f"✅ 连接成功: {client.host}:{client.port}/{client.database}")
    return client


def test_create_conversation(client):
    """测试创建对话"""
    print("\n=== 测试 2: 创建对话 ===")
    user_id = "test_user_001"

    # 创建第一个对话
    conv1 = client.create_conversation(user_id, "测试对话1")
    print(f"✅ 创建对话1: {conv1.id}, {conv1.title}")

    # 创建第二个对话
    conv2 = client.create_conversation(user_id, "测试对话2")
    print(f"✅ 创建对话2: {conv2.id}, {conv2.title}")

    return conv1.id, conv2.id


def test_get_conversations(client, user_id):
    """测试获取对话列表"""
    print("\n=== 测试 3: 获取对话列表 ===")
    conversations = client.get_conversations(user_id)
    print(f"✅ 获取到 {len(conversations)} 个对话")
    for conv in conversations:
        print(f"   - {conv.id}: {conv.title} (updated: {conv.updated_at})")


def test_add_messages(client, user_id, conversation_id):
    """测试添加消息"""
    print("\n=== 测试 4: 添加消息 ===")

    # 添加用户消息
    msg1 = client.add_message(user_id, conversation_id, "user", "你好，请帮我梳理一下字节跳动的常考知识点")
    print(f"✅ 添加用户消息: {msg1.id}")

    # 添加 AI 回复
    msg2 = client.add_message(
        user_id,
        conversation_id,
        "assistant",
        "好的，我来帮你梳理字节跳动的常考知识点..."
    )
    print(f"✅ 添加 AI 回复: {msg2.id}")


def test_get_messages(client, user_id, conversation_id):
    """测试获取消息"""
    print("\n=== 测试 5: 获取消息 ===")
    messages = client.get_messages(user_id, conversation_id)
    print(f"✅ 获取到 {len(messages)} 条消息")
    for msg in messages:
        print(f"   - [{msg.role}]: {msg.content[:50]}...")


def test_update_title(client, user_id, conversation_id):
    """测试更新标题"""
    print("\n=== 测试 6: 更新标题 ===")
    client.update_conversation_title(user_id, conversation_id, "字节跳动面试梳理")
    print("✅ 标题更新成功")

    # 验证
    conv = client.get_conversation(user_id, conversation_id)
    print(f"   新标题: {conv.title}")


def test_delete_conversation(client, user_id, conversation_id):
    """测试删除对话"""
    print("\n=== 测试 7: 删除对话 ===")
    client.delete_conversation(user_id, conversation_id)
    print("✅ 对话删除成功")

    # 验证
    conversations = client.get_conversations(user_id)
    print(f"   剩余对话数: {len(conversations)}")


def test_multi_user_isolation(client):
    """测试多租户隔离"""
    print("\n=== 测试 8: 多租户隔离 ===")
    user1 = "user_001"
    user2 = "user_002"

    # 用户1 创建对话
    conv1 = client.create_conversation(user1, "用户1的对话")
    print(f"✅ 用户1 创建对话: {conv1.id}")

    # 用户2 创建对话
    conv2 = client.create_conversation(user2, "用户2的对话")
    print(f"✅ 用户2 创建对话: {conv2.id}")

    # 用户1 只能看到自己的对话
    convs1 = client.get_conversations(user1)
    print(f"✅ 用户1 看到 {len(convs1)} 个对话")

    # 用户2 只能看到自己的对话
    convs2 = client.get_conversations(user2)
    print(f"✅ 用户2 看到 {len(convs2)} 个对话")

    # 清理
    client.delete_conversation(user1, conv1.id)
    client.delete_conversation(user2, conv2.id)


def main():
    print("=" * 50)
    print("PostgreSQL 客户端测试（测试数据库）")
    print("=" * 50)

    try:
        client = test_connection()

        # 测试用户 ID
        test_user_id = "test_user_001"

        # 基础 CRUD 测试
        conv1_id, conv2_id = test_create_conversation(client)
        test_get_conversations(client, test_user_id)
        test_add_messages(client, test_user_id, conv1_id)
        test_get_messages(client, test_user_id, conv1_id)
        test_update_title(client, test_user_id, conv1_id)

        # 多租户隔离测试
        test_multi_user_isolation(client)

        # 清理
        test_delete_conversation(client, test_user_id, conv1_id)
        test_delete_conversation(client, test_user_id, conv2_id)

        print("\n" + "=" * 50)
        print("✅ 所有测试通过!")
        print("=" * 50)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 关闭连接
        try:
            client.close()
        except:
            pass


if __name__ == "__main__":
    main()