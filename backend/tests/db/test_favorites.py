"""收藏功能测试

测试 PostgreSQL 客户端的收藏操作方法。
注意：测试在 offer_catcher_test 数据库中进行。
"""

import os
import sys

sys.path.insert(0, ".")

# 设置测试环境变量，使用测试数据库
os.environ["POSTGRES_DB"] = "offer_catcher_test"

from app.db import get_postgres_client


def test_connection():
    """测试连接"""
    print("=== 测试 1: 连接测试数据库 ===")
    client = get_postgres_client()
    print(f"✅ 连接成功: {client.host}:{client.port}/{client.database}")
    return client


def test_add_favorite(client):
    """测试添加收藏"""
    print("\n=== 测试 2: 添加收藏 ===")
    user_id = "test_favorites_user"
    question_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    favorite_id = client.add_favorite(user_id, question_id)
    print(f"✅ 添加收藏成功: id={favorite_id}, user={user_id}, question={question_id}")

    return favorite_id, user_id, question_id


def test_add_duplicate_favorite(client, user_id, question_id):
    """测试重复收藏"""
    print("\n=== 测试 3: 重复收藏（应抛出异常）===")
    try:
        client.add_favorite(user_id, question_id)
        print("❌ 未抛出异常，测试失败")
        return False
    except ValueError as e:
        print(f"✅ 正确抛出异常: {e}")
        return True


def test_get_favorites(client, user_id):
    """测试获取收藏列表"""
    print("\n=== 测试 4: 获取收藏列表 ===")
    items = client.get_favorites(user_id, limit=10, offset=0)
    print(f"✅ 获取到 {len(items)} 个收藏")
    for item in items:
        print(f"   - id: {item['id']}, question_id: {item['question_id']}, created_at: {item['created_at']}")

    return items


def test_count_favorites(client, user_id):
    """测试统计收藏数量"""
    print("\n=== 测试 5: 统计收藏数量 ===")
    count = client.count_favorites(user_id)
    print(f"✅ 收藏数量: {count}")
    return count


def test_check_favorites(client, user_id, question_id):
    """测试批量检查收藏状态"""
    print("\n=== 测试 6: 批量检查收藏状态 ===")

    # 测试已收藏的题目
    another_question_id = "xyz12345-6789-abcd-ef12-34567890abcd"
    # 先添加另一个收藏
    client.add_favorite(user_id, another_question_id)

    # 检查状态
    question_ids = [question_id, another_question_id, "not-favored-1234-5678-9abc-def0"]
    status = client.check_favorites(user_id, question_ids)

    print(f"✅ 检查结果:")
    for qid, is_favored in status.items():
        print(f"   - {qid}: {is_favored}")

    # 验证
    assert status[question_id] == True, "已收藏的题目应返回 True"
    assert status[another_question_id] == True, "已收藏的题目应返回 True"
    assert status["not-favored-1234-5678-9abc-def0"] == False, "未收藏的题目应返回 False"
    print("✅ 状态检查正确")

    return another_question_id


def test_remove_favorite(client, user_id, question_id):
    """测试取消收藏"""
    print("\n=== 测试 7: 取消收藏 ===")
    deleted = client.remove_favorite(user_id, question_id)
    print(f"✅ 取消收藏: {deleted}")

    # 验证
    count = client.count_favorites(user_id)
    print(f"   剩余收藏数: {count}")

    return deleted


def test_remove_nonexistent_favorite(client, user_id):
    """测试取消不存在的收藏"""
    print("\n=== 测试 8: 取消不存在的收藏 ===")
    fake_question_id = "not-exist-1234-5678-9abc-def0"
    deleted = client.remove_favorite(user_id, fake_question_id)
    print(f"✅ 返回 False（未找到）: {deleted}")
    assert deleted == False, "取消不存在的收藏应返回 False"


def test_multi_user_isolation(client):
    """测试多用户隔离"""
    print("\n=== 测试 9: 多用户隔离 ===")

    user1 = "favorites_user_001"
    user2 = "favorites_user_002"
    shared_question_id = "shared-question-abcd-ef12-3456"

    # 用户1 收藏
    client.add_favorite(user1, shared_question_id)
    print(f"✅ 用户1 收藏题目: {shared_question_id}")

    # 用户2 收藏同一题目（应该可以，因为每个用户独立）
    client.add_favorite(user2, shared_question_id)
    print(f"✅ 用户2 收藏同一题目: {shared_question_id}")

    # 检查用户1的收藏
    status1 = client.check_favorites(user1, [shared_question_id])
    assert status1[shared_question_id] == True
    print(f"✅ 用户1 可以看到自己的收藏")

    # 检查用户2的收藏
    status2 = client.check_favorites(user2, [shared_question_id])
    assert status2[shared_question_id] == True
    print(f"✅ 用户2 可以看到自己的收藏")

    # 用户1 取消收藏，不影响用户2
    client.remove_favorite(user1, shared_question_id)
    status2_after = client.check_favorites(user2, [shared_question_id])
    assert status2_after[shared_question_id] == True
    print(f"✅ 用户1 取消后，用户2 的收藏仍然存在")

    # 清理
    client.remove_favorite(user2, shared_question_id)


def test_pagination(client):
    """测试分页"""
    print("\n=== 测试 10: 分页 ===")

    user_id = "pagination_test_user"

    # 添加多个收藏
    for i in range(5):
        question_id = f"page-test-{i:04d}-abcd-ef12-3456"
        client.add_favorite(user_id, question_id)

    print(f"✅ 添加了 5 个收藏")

    # 测试分页
    page1 = client.get_favorites(user_id, limit=2, offset=0)
    print(f"✅ 第1页: {len(page1)} 个收藏")

    page2 = client.get_favorites(user_id, limit=2, offset=2)
    print(f"✅ 第2页: {len(page2)} 个收藏")

    page3 = client.get_favorites(user_id, limit=2, offset=4)
    print(f"✅ 第3页: {len(page3)} 个收藏")

    assert len(page1) == 2, "第1页应有 2 个"
    assert len(page2) == 2, "第2页应有 2 个"
    assert len(page3) == 1, "第3页应有 1 个"

    # 清理
    items = client.get_favorites(user_id, limit=100)
    for item in items:
        client.remove_favorite(user_id, item["question_id"])
    print(f"✅ 清理完成")


def cleanup(client, user_id):
    """清理测试数据"""
    print("\n=== 清理测试数据 ===")
    items = client.get_favorites(user_id, limit=100)
    for item in items:
        client.remove_favorite(user_id, item["question_id"])

    # 清理其他测试用户
    for test_user in ["favorites_user_001", "favorites_user_002", "pagination_test_user"]:
        items = client.get_favorites(test_user, limit=100)
        for item in items:
            client.remove_favorite(test_user, item["question_id"])

    print(f"✅ 清理完成")


def main():
    print("=" * 60)
    print("收藏功能单元测试（测试数据库: offer_catcher_test）")
    print("=" * 60)

    client = None
    try:
        client = test_connection()

        # 测试用户 ID
        favorite_id, user_id, question_id = test_add_favorite(client)

        # 各项测试
        test_add_duplicate_favorite(client, user_id, question_id)
        test_get_favorites(client, user_id)
        test_count_favorites(client, user_id)
        another_question_id = test_check_favorites(client, user_id, question_id)
        test_remove_favorite(client, user_id, question_id)
        test_remove_nonexistent_favorite(client, user_id)
        test_multi_user_isolation(client)
        test_pagination(client)

        # 清理
        cleanup(client, user_id)

        print("\n" + "=" * 60)
        print("✅ 所有测试通过!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if client:
            try:
                client.close()
            except:
                pass


if __name__ == "__main__":
    main()