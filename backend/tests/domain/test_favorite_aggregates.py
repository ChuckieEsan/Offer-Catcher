"""Favorite Domain Aggregates Tests

测试 Favorite 聚合根的业务逻辑。
"""

from datetime import datetime

from app.domain.favorite.aggregates import Favorite


def test_create_favorite():
    """测试创建收藏聚合"""
    user_id = "test_user_001"
    question_id = "test_question_001"

    favorite = Favorite.create(user_id=user_id, question_id=question_id)

    assert favorite.favorite_id is not None
    assert favorite.user_id == user_id
    assert favorite.question_id == question_id
    assert favorite.created_at is not None
    print("✅ test_create_favorite passed")


def test_create_favorite_with_id():
    """测试指定 ID 创建收藏"""
    favorite_id = "custom-favorite-id"
    user_id = "test_user"
    question_id = "test_question"

    favorite = Favorite.create(
        user_id=user_id,
        question_id=question_id,
        favorite_id=favorite_id,
    )

    assert favorite.favorite_id == favorite_id
    print("✅ test_create_favorite_with_id passed")


def test_to_payload():
    """测试序列化为 payload"""
    favorite = Favorite.create(
        user_id="user_001",
        question_id="question_001",
        favorite_id="fav_001",
    )

    payload = favorite.to_payload()

    assert payload["favorite_id"] == "fav_001"
    assert payload["user_id"] == "user_001"
    assert payload["question_id"] == "question_001"
    assert "created_at" in payload
    print("✅ test_to_payload passed")


def test_from_payload():
    """测试从 payload 恢复聚合"""
    payload = {
        "favorite_id": "fav_001",
        "user_id": "user_001",
        "question_id": "question_001",
        "created_at": "2026-01-01T12:00:00",
    }

    favorite = Favorite.from_payload(payload)

    assert favorite.favorite_id == "fav_001"
    assert favorite.user_id == "user_001"
    assert favorite.question_id == "question_001"
    assert favorite.created_at == datetime(2026, 1, 1, 12, 0, 0)
    print("✅ test_from_payload passed")


def test_payload_roundtrip():
    """测试 payload 序列化/反序列化往返"""
    original = Favorite.create(
        user_id="user_roundtrip",
        question_id="question_roundtrip",
    )

    payload = original.to_payload()
    restored = Favorite.from_payload(payload)

    assert restored.favorite_id == original.favorite_id
    assert restored.user_id == original.user_id
    assert restored.question_id == original.question_id
    print("✅ test_payload_roundtrip passed")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("Favorite Domain Aggregates Tests")
    print("=" * 60)

    test_create_favorite()
    test_create_favorite_with_id()
    test_to_payload()
    test_from_payload()
    test_payload_roundtrip()

    print("=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()