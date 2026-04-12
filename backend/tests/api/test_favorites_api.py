"""Favorites API 测试

测试收藏功能的 API 端点。
注意：测试在 offer_catcher_test 数据库中进行，需要启动后端服务。
"""

import os
import sys

sys.path.insert(0, ".")

# 设置测试环境变量，使用测试数据库
os.environ["POSTGRES_DB"] = "offer_catcher_test"

import httpx
import asyncio


BASE_URL = "http://localhost:8000/api/v1"
USER_ID = "test_api_favorites_user"

# 测试用的 question_id（模拟 UUID 格式）
TEST_QUESTION_IDS = [
    "api-test-0001-abcd-ef12-3456",
    "api-test-0002-abcd-ef12-3456",
    "api-test-0003-abcd-ef12-3456",
    "api-test-0004-abcd-ef12-3456",
]


async def test_add_favorite():
    """测试添加收藏"""
    print("\n=== 测试 1: 添加收藏 ===")

    url = f"{BASE_URL}/favorites"
    headers = {"X-User-ID": USER_ID}
    payload = {"question_id": TEST_QUESTION_IDS[0]}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=headers)

        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"响应: {data}")

        if response.status_code == 200:
            print(f"✅ 添加收藏成功: id={data['id']}")
            return data
        else:
            print(f"❌ 添加失败: {data}")
            return None


async def test_add_duplicate_favorite():
    """测试重复添加收藏"""
    print("\n=== 测试 2: 重复添加收藏（应返回 400）===")

    url = f"{BASE_URL}/favorites"
    headers = {"X-User-ID": USER_ID}
    payload = {"question_id": TEST_QUESTION_IDS[0]}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=headers)

        print(f"状态码: {response.status_code}")

        if response.status_code == 400:
            print(f"✅ 正确返回 400: {response.json()['detail']}")
        else:
            print(f"❌ 应返回 400，实际返回 {response.status_code}")


async def test_list_favorites():
    """测试获取收藏列表"""
    print("\n=== 测试 3: 获取收藏列表 ===")

    # 先添加几个收藏
    url = f"{BASE_URL}/favorites"
    headers = {"X-User-ID": USER_ID}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 添加更多收藏
        for qid in TEST_QUESTION_IDS[1:3]:
            await client.post(url, json={"question_id": qid}, headers=headers)

        # 获取列表
        response = await client.get(url, params={"page": 1, "page_size": 10}, headers=headers)

        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"总数: {data['total']}")
        print(f"返回数量: {len(data['items'])}")

        for item in data["items"]:
            print(f"   - question_id: {item['question_id']}, created_at: {item['created_at']}")

        if response.status_code == 200 and data["total"] >= 3:
            print("✅ 获取列表成功")
        else:
            print("❌ 获取列表失败")


async def test_check_favorites():
    """测试批量检查收藏状态"""
    print("\n=== 测试 4: 批量检查收藏状态 ===")

    url = f"{BASE_URL}/favorites/check"
    headers = {"X-User-ID": USER_ID}

    # 包含已收藏和未收藏的题目
    question_ids = TEST_QUESTION_IDS[:3] + ["not-favored-1234"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            json={"question_ids": question_ids},
            headers=headers,
        )

        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"状态映射:")
        for qid, is_favored in data["status"].items():
            print(f"   - {qid}: {is_favored}")

        # 验证
        assert data["status"][TEST_QUESTION_IDS[0]] == True
        assert data["status"][TEST_QUESTION_IDS[1]] == True
        assert data["status"][TEST_QUESTION_IDS[2]] == True
        assert data["status"]["not-favored-1234"] == False

        print("✅ 状态检查正确")


async def test_remove_favorite():
    """测试取消收藏"""
    print("\n=== 测试 5: 取消收藏 ===")

    url = f"{BASE_URL}/favorites/{TEST_QUESTION_IDS[0]}"
    headers = {"X-User-ID": USER_ID}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.delete(url, headers=headers)

        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"响应: {data}")

        if response.status_code == 200 and data["success"]:
            print("✅ 取消收藏成功")
        else:
            print("❌ 取消收藏失败")


async def test_remove_nonexistent_favorite():
    """测试取消不存在的收藏"""
    print("\n=== 测试 6: 取消不存在的收藏（应返回 404）===")

    url = f"{BASE_URL}/favorites/not-exist-1234"
    headers = {"X-User-ID": USER_ID}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.delete(url, headers=headers)

        print(f"状态码: {response.status_code}")

        if response.status_code == 404:
            print(f"✅ 正确返回 404: {response.json()['detail']}")
        else:
            print(f"❌ 应返回 404，实际返回 {response.status_code}")


async def test_pagination():
    """测试分页"""
    print("\n=== 测试 7: 分页 ===")

    url = f"{BASE_URL}/favorites"
    headers = {"X-User-ID": USER_ID}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 获取总数
        response = await client.get(url, params={"page": 1, "page_size": 100}, headers=headers)
        total = response.json()["total"]
        print(f"总收藏数: {total}")

        if total < 2:
            print("⚠️ 收藏数不足，跳过分页测试")
            return

        # 第1页
        response = await client.get(url, params={"page": 1, "page_size": 1}, headers=headers)
        page1 = response.json()
        print(f"第1页: {len(page1['items'])} 个收藏")

        # 第2页
        response = await client.get(url, params={"page": 2, "page_size": 1}, headers=headers)
        page2 = response.json()
        print(f"第2页: {len(page2['items'])} 个收藏")

        # 验证两个页面的题目不同
        if len(page1["items"]) > 0 and len(page2["items"]) > 0:
            qid1 = page1["items"][0]["question_id"]
            qid2 = page2["items"][0]["question_id"]
            if qid1 != qid2:
                print("✅ 分页正确，不同页面的题目不同")
            else:
                print("❌ 分页问题：两个页面的题目相同")


async def test_user_isolation():
    """测试用户隔离"""
    print("\n=== 测试 8: 用户隔离 ===")

    user1 = "api_user_001"
    user2 = "api_user_002"
    shared_question = "shared-api-test-1234"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 用户1 收藏
        response = await client.post(
            f"{BASE_URL}/favorites",
            json={"question_id": shared_question},
            headers={"X-User-ID": user1},
        )
        print(f"用户1 收藏: 状态码 {response.status_code}")

        # 用户2 收藏同一题目
        response = await client.post(
            f"{BASE_URL}/favorites",
            json={"question_id": shared_question},
            headers={"X-User-ID": user2},
        )
        print(f"用户2 收藏同一题目: 状态码 {response.status_code}")

        # 检查用户1的收藏状态
        response = await client.post(
            f"{BASE_URL}/favorites/check",
            json={"question_ids": [shared_question]},
            headers={"X-User-ID": user1},
        )
        status1 = response.json()["status"][shared_question]
        print(f"用户1 收藏状态: {status1}")

        # 检查用户2的收藏状态
        response = await client.post(
            f"{BASE_URL}/favorites/check",
            json={"question_ids": [shared_question]},
            headers={"X-User-ID": user2},
        )
        status2 = response.json()["status"][shared_question]
        print(f"用户2 收藏状态: {status2}")

        assert status1 == True and status2 == True
        print("✅ 用户隔离正确：两个用户都可以收藏同一题目")

        # 用户1 取消收藏
        await client.delete(
            f"{BASE_URL}/favorites/{shared_question}",
            headers={"X-User-ID": user1},
        )

        # 验证用户2的收藏仍然存在
        response = await client.post(
            f"{BASE_URL}/favorites/check",
            json={"question_ids": [shared_question]},
            headers={"X-User-ID": user2},
        )
        status2_after = response.json()["status"][shared_question]
        print(f"用户1 取消后，用户2 收藏状态: {status2_after}")

        assert status2_after == True
        print("✅ 用户隔离正确：用户1取消不影响用户2")

        # 清理用户2
        await client.delete(
            f"{BASE_URL}/favorites/{shared_question}",
            headers={"X-User-ID": user2},
        )


async def cleanup():
    """清理测试数据"""
    print("\n=== 清理测试数据 ===")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 获取所有收藏
        response = await client.get(
            f"{BASE_URL}/favorites",
            params={"page": 1, "page_size": 100},
            headers={"X-User-ID": USER_ID},
        )

        items = response.json()["items"]
        for item in items:
            await client.delete(
                f"{BASE_URL}/favorites/{item['question_id']}",
                headers={"X-User-ID": USER_ID},
            )

        print(f"✅ 清理了 {len(items)} 个收藏")


async def main():
    print("=" * 60)
    print("Favorites API 测试")
    print("注意：需要启动后端服务（uvicorn app.main:app）")
    print("=" * 60)

    try:
        await test_add_favorite()
        await test_add_duplicate_favorite()
        await test_list_favorites()
        await test_check_favorites()
        await test_remove_favorite()
        await test_remove_nonexistent_favorite()
        await test_pagination()
        await test_user_isolation()
        await cleanup()

        print("\n" + "=" * 60)
        print("✅ 所有 API 测试通过!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())