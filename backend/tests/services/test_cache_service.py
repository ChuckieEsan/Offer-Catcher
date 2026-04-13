"""缓存服务功能测试

验证 Redis 缓存的各项功能是否正常工作：
- TTL 随机化（防雪崩）
- 分布式锁（防击穿）
- 缓存空值（防穿透）
- 缓存失效
- 延迟双删
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.services.cache_service import CacheService, CacheKeys, get_cache_service
from app.models import QdrantQuestionPayload
from app.models.question import QuestionType, MasteryLevel


class TestCacheKeys:
    """CacheKeys 测试"""

    def test_key_prefix(self):
        """测试 Key 前缀"""
        assert CacheKeys.PREFIX == "oc"

    def test_stats_keys(self):
        """测试统计 Key 生成"""
        assert CacheKeys.stats_overview() == "oc:stats:overview"
        assert CacheKeys.stats_clusters() == "oc:stats:clusters"
        assert CacheKeys.stats_companies() == "oc:stats:companies"

    def test_questions_keys(self):
        """测试题目 Key 生成"""
        assert CacheKeys.questions_list("abc123") == "oc:questions:list:abc123"
        assert CacheKeys.questions_item("q1") == "oc:questions:item:q1"
        assert CacheKeys.lock_key("test") == "oc:lock:test"

    def test_ttl_randomization(self):
        """测试 TTL 随机化（防雪崩）"""
        ttls = [CacheKeys.get_ttl() for _ in range(100)]

        # 基础 TTL 是 300 秒（5 分钟）
        base_ttl = CacheKeys.BASE_TTL
        random_range = CacheKeys.RANDOM_RANGE

        # 验证所有 TTL 在合理范围内
        for ttl in ttls:
            assert base_ttl - random_range <= ttl <= base_ttl + random_range

        # 验证存在随机性（不全是同一个值）
        unique_ttls = set(ttls)
        assert len(unique_ttls) > 1, "TTL should have randomness"

        # 验证分布相对均匀（避免极端偏斜）
        avg_ttl = sum(ttls) / len(ttls)
        expected_avg = base_ttl
        deviation = abs(avg_ttl - expected_avg) / random_range
        assert deviation < 0.3, f"TTL distribution too skewed: avg={avg_ttl}"


class TestCacheServiceBasic:
    """CacheService 基础操作测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前清理缓存"""
        self.cache = get_cache_service()
        # 清理测试用的 keys
        self.cache.delete_pattern("oc:test:*")
        yield
        # 测试后清理
        self.cache.delete_pattern("oc:test:*")

    def test_set_and_get(self):
        """测试基础读写"""
        key = "oc:test:simple"

        # 写入
        self.cache.set(key, {"data": "test_value"})

        # 读取
        hit, value = self.cache.get(key)
        assert hit is True
        assert value["data"] == "test_value"

    def test_set_and_get_list(self):
        """测试列表读写"""
        key = "oc:test:list"
        data = [1, 2, 3, "test"]

        self.cache.set(key, data)

        hit, value = self.cache.get(key)
        assert hit is True
        assert value == data

    def test_set_with_custom_ttl(self):
        """测试自定义 TTL"""
        key = "oc:test:ttl"
        custom_ttl = 10  # 10 秒

        self.cache.set(key, {"data": "ttl_test"}, ttl=custom_ttl)

        hit, value = self.cache.get(key)
        assert hit is True
        assert value["data"] == "ttl_test"

        # 验证 TTL 设置正确
        actual_ttl = self.cache.redis.ttl(key)
        assert 0 < actual_ttl <= custom_ttl

    def test_get_nonexistent_key(self):
        """测试读取不存在的 Key"""
        key = "oc:test:nonexistent"

        hit, value = self.cache.get(key)
        assert hit is False
        assert value is None

    def test_delete_single_key(self):
        """测试删除单个 Key"""
        key = "oc:test:delete"

        self.cache.set(key, {"data": "to_delete"})
        hit, _ = self.cache.get(key)
        assert hit is True

        self.cache.delete(key)
        hit, value = self.cache.get(key)
        assert hit is False

    def test_delete_multiple_keys(self):
        """测试删除多个 Key"""
        keys = ["oc:test:del1", "oc:test:del2", "oc:test:del3"]

        for key in keys:
            self.cache.set(key, {"data": key})

        self.cache.delete(*keys)

        for key in keys:
            hit, _ = self.cache.get(key)
            assert hit is False

    def test_delete_pattern(self):
        """测试模式删除"""
        # 创建多个匹配模式的 Key
        for i in range(5):
            self.cache.set(f"oc:test:pattern:{i}", {"index": i})

        # 创建一个不匹配的 Key
        self.cache.set("oc:test:other", {"data": "other"})

        # 删除匹配模式的 Key
        self.cache.delete_pattern("oc:test:pattern:*")

        # 验证匹配的 Key 已删除
        for i in range(5):
            hit, _ = self.cache.get(f"oc:test:pattern:{i}")
            assert hit is False

        # 验证不匹配的 Key 仍然存在
        hit, value = self.cache.get("oc:test:other")
        assert hit is True
        assert value["data"] == "other"


class TestCacheNullValue:
    """缓存空值测试（防穿透）"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前清理缓存"""
        self.cache = get_cache_service()
        self.cache.delete_pattern("oc:test:null:*")
        yield
        self.cache.delete_pattern("oc:test:null:*")

    def test_set_null_value(self):
        """测试缓存空值"""
        key = "oc:test:null:value"

        # 缓存 None 值
        self.cache.set(key, None)

        # 读取应返回 (True, None)，表示缓存命中空值
        hit, value = self.cache.get(key)
        assert hit is True
        assert value is None

    def test_null_value_ttl(self):
        """测试空值使用较短 TTL"""
        key = "oc:test:null:ttl"

        self.cache.set(key, None)

        # 验证 TTL 是 NULL_TTL（60秒）
        actual_ttl = self.cache.redis.ttl(key)
        assert 0 < actual_ttl <= CacheKeys.NULL_TTL

    def test_null_value_stored_as_marker(self):
        """测试空值实际存储为 NULL_MARKER"""
        key = "oc:test:null:marker"

        self.cache.set(key, None)

        # 直接读取 Redis，验证存储的是标记
        raw_value = self.cache.redis.get(key)
        assert raw_value == CacheKeys.NULL_MARKER


class TestDistributedLock:
    """分布式锁测试（防击穿）"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前清理缓存"""
        self.cache = get_cache_service()
        self.cache.delete_pattern("oc:lock:*")
        yield
        self.cache.delete_pattern("oc:lock:*")

    def test_acquire_lock_success(self):
        """测试成功获取锁"""
        key = "test_lock"

        lock_value = self.cache._acquire_lock(key)
        assert lock_value is not None  # 返回锁值表示成功

        # 验证锁 Key 存在
        lock_key = CacheKeys.lock_key(key)
        raw_value = self.cache.redis.get(lock_key)
        assert raw_value == lock_value  # 存储的是锁值

    def test_acquire_lock_already_exists(self):
        """测试锁已存在时无法获取"""
        key = "test_lock_existing"

        # 第一次获取成功
        lock_value1 = self.cache._acquire_lock(key)
        assert lock_value1 is not None

        # 第二次获取失败（返回 None）
        lock_value2 = self.cache._acquire_lock(key)
        assert lock_value2 is None

    def test_release_lock(self):
        """测试释放锁"""
        key = "test_lock_release"

        # 获取锁
        lock_value = self.cache._acquire_lock(key)
        lock_key = CacheKeys.lock_key(key)

        # 验证锁存在
        assert self.cache.redis.get(lock_key) == lock_value

        # 释放锁
        released = self.cache._release_lock(key, lock_value)
        assert released is True

        # 验证锁已删除
        assert self.cache.redis.get(lock_key) is None

    def test_lock_has_ttl(self):
        """测试锁有过期时间"""
        key = "test_lock_ttl"

        self.cache._acquire_lock(key)
        lock_key = CacheKeys.lock_key(key)

        # 验证 TTL 存在
        ttl = self.cache.redis.ttl(lock_key)
        assert 0 < ttl <= CacheKeys.LOCK_TTL

    def test_concurrent_lock_acquisition(self):
        """测试并发获取锁"""
        key = "test_lock_concurrent"
        results = []
        lock_key = CacheKeys.lock_key(key)

        def try_acquire():
            lock_value = self.cache._acquire_lock(key)
            results.append(lock_value is not None)
            if lock_value:
                # 获取成功，等待一下再释放
                time.sleep(0.5)
                self.cache._release_lock(key, lock_value)

        # 创建多个线程并发获取锁
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(try_acquire) for _ in range(5)]
            for f in futures:
                f.result()

        # 验证只有一个线程获取成功
        success_count = sum(1 for r in results if r)
        assert success_count == 1


class TestGetWithLock:
    """带锁缓存读取测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前清理缓存"""
        self.cache = get_cache_service()
        self.cache.delete_pattern("oc:test:lock:*")
        self.cache.delete_pattern("oc:lock:*")
        yield
        self.cache.delete_pattern("oc:test:lock:*")
        self.cache.delete_pattern("oc:lock:*")

    def test_get_with_lock_cache_hit(self):
        """测试缓存命中时不获取锁"""
        key = "oc:test:lock:hit"
        call_count = [0]  # 使用列表避免闭包问题

        def fetch_fn():
            call_count[0] += 1
            return {"data": "from_db"}

        # 先写入缓存
        self.cache.set(key, {"data": "cached"})

        # 获取数据
        result = self.cache.get_with_lock(key, fetch_fn)

        # 验证返回缓存数据，未调用 fetch_fn
        assert result["data"] == "cached"
        assert call_count[0] == 0

    def test_get_with_lock_cache_miss(self):
        """测试缓存未命中时查数据库并缓存"""
        key = "oc:test:lock:miss"

        def fetch_fn():
            return {"data": "from_db"}

        result = self.cache.get_with_lock(key, fetch_fn)

        # 验证返回数据库数据
        assert result["data"] == "from_db"

        # 验证数据已缓存
        hit, cached = self.cache.get(key)
        assert hit is True
        assert cached["data"] == "from_db"

    def test_get_with_lock_null_result(self):
        """测试数据库返回空值时缓存空值"""
        key = "oc:test:lock:null"

        def fetch_fn():
            return None

        result = self.cache.get_with_lock(key, fetch_fn)

        # 验证返回 None
        assert result is None

        # 验证空值已缓存（命中返回 True）
        hit, value = self.cache.get(key)
        assert hit is True
        assert value is None

    def test_get_with_lock_double_check(self):
        """测试双重检查机制"""
        key = "oc:test:lock:double"
        call_count = [0]  # 使用列表避免闭包问题

        def fetch_fn():
            call_count[0] += 1
            return {"count": call_count[0]}

        # 第一个调用：缓存未命中，获取锁，查数据库
        result1 = self.cache.get_with_lock(key, fetch_fn)

        # 第二个调用：缓存命中，直接返回
        result2 = self.cache.get_with_lock(key, fetch_fn)

        # 验证两次返回相同数据
        assert result1["count"] == 1
        assert result2["count"] == 1

        # 验证 fetch_fn 只调用一次
        assert call_count[0] == 1

    def test_get_with_lock_lock_failure_degradation(self):
        """测试锁获取失败时的降级策略"""
        key = "oc:test:lock:degrade"

        def fetch_fn():
            return {"data": "fallback"}

        # 预先设置锁（阻止获取）
        lock_key = CacheKeys.lock_key(key)
        self.cache.redis.set(lock_key, 1, ex=CacheKeys.LOCK_TTL)

        # 调用 get_with_lock，锁获取失败
        result = self.cache.get_with_lock(key, fetch_fn, max_retries=1)

        # 验证降级策略：直接查数据库
        assert result["data"] == "fallback"


class TestCacheInvalidation:
    """缓存失效测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前清理缓存"""
        self.cache = get_cache_service()
        self.cache.delete_pattern("oc:test:*")
        self.cache.delete_pattern("oc:questions:*")
        self.cache.delete_pattern("oc:stats:*")
        yield
        self.cache.delete_pattern("oc:test:*")
        self.cache.delete_pattern("oc:questions:*")
        self.cache.delete_pattern("oc:stats:*")

    def test_invalidate_question_deletes_lists(self):
        """测试失效题目时删除列表缓存"""
        # 创建多个列表缓存
        self.cache.set("oc:questions:list:abc", {"items": []})
        self.cache.set("oc:questions:list:def", {"items": []})
        self.cache.set("oc:questions:count:abc", 10)

        # 失效题目
        self.cache.invalidate_question("q1")

        # 验证列表缓存已删除
        hit1, _ = self.cache.get("oc:questions:list:abc")
        hit2, _ = self.cache.get("oc:questions:list:def")
        hit3, _ = self.cache.get("oc:questions:count:abc")

        assert hit1 is False
        assert hit2 is False
        assert hit3 is False

    def test_invalidate_question_deletes_stats(self):
        """测试失效题目时删除统计缓存"""
        # 创建统计缓存
        self.cache.set(CacheKeys.stats_overview(), {"total": 100})
        self.cache.set(CacheKeys.stats_clusters(), [{"cluster_id": "c1"}])
        self.cache.set(CacheKeys.stats_companies(), [{"company": "字节"}])

        # 失效题目
        self.cache.invalidate_question()

        # 验证统计缓存已删除
        hit1, _ = self.cache.get(CacheKeys.stats_overview())
        hit2, _ = self.cache.get(CacheKeys.stats_clusters())
        hit3, _ = self.cache.get(CacheKeys.stats_companies())

        assert hit1 is False
        assert hit2 is False
        assert hit3 is False

    def test_invalidate_question_with_id(self):
        """测试失效指定题目"""
        question_id = "test_q_123"
        key = CacheKeys.questions_item(question_id)

        # 缓存单个题目
        self.cache.set(key, {"question_id": question_id})

        # 失效指定题目
        self.cache.invalidate_question(question_id)

        # 验证题目缓存已删除
        hit, _ = self.cache.get(key)
        assert hit is False

    def test_invalidate_question_delayed(self):
        """测试延迟双删"""
        question_id = "test_q_delayed"
        key = CacheKeys.questions_item(question_id)

        # 缓存题目
        self.cache.set(key, {"question_id": question_id})

        # 第一次失效
        self.cache.invalidate_question(question_id)
        hit1, _ = self.cache.get(key)
        assert hit1 is False

        # 在延迟期间，假设有并发写入，重新缓存
        self.cache.set(key, {"question_id": question_id, "updated": True})

        # 执行延迟双删（异步）
        async def run_delayed():
            await self.cache.invalidate_question_delayed(question_id)

        asyncio.run(run_delayed())

        # 验证第二次删除生效
        hit2, _ = self.cache.get(key)
        assert hit2 is False


class TestPydanticSerialization:
    """Pydantic 模型序列化测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前清理缓存"""
        self.cache = get_cache_service()
        self.cache.delete_pattern("oc:test:pydantic:*")
        yield
        self.cache.delete_pattern("oc:test:pydantic:*")

    def test_serialize_single_pydantic_model(self):
        """测试序列化单个 Pydantic 模型"""
        key = "oc:test:pydantic:single"

        model = QdrantQuestionPayload(
            question_id="q1",
            question_text="什么是RAG?",
            company="字节跳动",
            position="AI开发",
            question_type="knowledge",
            mastery_level=0,
            core_entities=["RAG"],
            vector=[0.1, 0.2, 0.3],
        )

        self.cache.set(key, model)

        # 读取并验证
        hit, value = self.cache.get(key)
        assert hit is True
        assert value["question_id"] == "q1"
        assert value["question_text"] == "什么是RAG?"

    def test_serialize_pydantic_list(self):
        """测试序列化 Pydantic 模型列表"""
        key = "oc:test:pydantic:list"

        models = [
            QdrantQuestionPayload(
                question_id=f"q{i}",
                question_text=f"题目{i}",
                company="字节跳动",
                position="AI开发",
                question_type="knowledge",
                mastery_level=0,
                core_entities=[],
                vector=[0.1] * 10,
            )
            for i in range(3)
        ]

        self.cache.set(key, models)

        # 读取并验证
        hit, value = self.cache.get(key)
        assert hit is True
        assert len(value) == 3
        assert value[0]["question_id"] == "q0"
        assert value[2]["question_text"] == "题目2"


class TestHashParams:
    """参数哈希测试"""

    def test_hash_empty_params(self):
        """测试空参数返回 'all'"""
        cache = get_cache_service()

        assert cache._hash_params({}) == "all"

    def test_hash_all_none_params(self):
        """测试所有值为 None 返回 'all'"""
        cache = get_cache_service()

        result = cache._hash_params({"a": None, "b": None})
        assert result == "all"

    def test_hash_consistent(self):
        """测试相同参数生成相同哈希"""
        cache = get_cache_service()

        params1 = {"company": "字节", "type": "knowledge"}
        params2 = {"type": "knowledge", "company": "字节"}  # 顺序不同

        hash1 = cache._hash_params(params1)
        hash2 = cache._hash_params(params2)

        assert hash1 == hash2

    def test_hash_different_params(self):
        """测试不同参数生成不同哈希"""
        cache = get_cache_service()

        params1 = {"company": "字节"}
        params2 = {"company": "阿里"}

        hash1 = cache._hash_params(params1)
        hash2 = cache._hash_params(params2)

        assert hash1 != hash2

    def test_hash_ignores_none(self):
        """测试过滤掉 None 值"""
        cache = get_cache_service()

        params1 = {"company": "字节", "type": None}
        params2 = {"company": "字节"}

        hash1 = cache._hash_params(params1)
        hash2 = cache._hash_params(params2)

        assert hash1 == hash2


class TestCacheIntegration:
    """缓存集成测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前清理缓存"""
        self.cache = get_cache_service()
        self.cache.delete_pattern("oc:*")
        yield
        self.cache.delete_pattern("oc:*")

    def test_questions_list_caching(self):
        """测试题目列表缓存流程"""
        fetch_count = [0]  # 使用列表避免闭包问题

        def fetch_fn():
            fetch_count[0] += 1
            return [{"question_id": "q1", "text": "test"}]

        params = {"company": "字节跳动"}

        # 第一次调用：缓存未命中
        result1 = self.cache.get_questions_list(params, fetch_fn)
        assert fetch_count[0] == 1

        # 第二次调用：缓存命中
        result2 = self.cache.get_questions_list(params, fetch_fn)
        assert fetch_count[0] == 1  # 未增加

        assert result1 == result2

    def test_stats_caching(self):
        """测试统计数据缓存流程"""
        fetch_count = [0]  # 使用列表避免闭包问题

        def fetch_fn():
            fetch_count[0] += 1
            return {"total": 100}

        key = CacheKeys.stats_overview()

        # 第一次调用
        result1 = self.cache.get_stats(key, fetch_fn)
        assert fetch_count[0] == 1

        # 第二次调用
        result2 = self.cache.get_stats(key, fetch_fn)
        assert fetch_count[0] == 1

        assert result1 == result2

    def test_full_workflow(self):
        """测试完整缓存流程"""
        question_id = "workflow_test"
        params = {"company": "字节跳动"}
        fetch_count = {"list": [0], "item": [0], "stats": [0]}  # 使用列表避免闭包问题

        def fetch_list():
            fetch_count["list"][0] += 1
            return [{"question_id": question_id}]

        def fetch_item():
            fetch_count["item"][0] += 1
            return {"question_id": question_id, "text": "test"}

        def fetch_stats():
            fetch_count["stats"][0] += 1
            return {"total": 1}

        # 1. 获取列表（缓存未命中）
        self.cache.get_questions_list(params, fetch_list)
        assert fetch_count["list"][0] == 1

        # 2. 获取单个题目（缓存未命中）
        self.cache.get_question_item(question_id, fetch_item)
        assert fetch_count["item"][0] == 1

        # 3. 获取统计（缓存未命中）
        self.cache.get_stats(CacheKeys.stats_overview(), fetch_stats)
        assert fetch_count["stats"][0] == 1

        # 4. 再次获取（全部缓存命中）
        self.cache.get_questions_list(params, fetch_list)
        self.cache.get_question_item(question_id, fetch_item)
        self.cache.get_stats(CacheKeys.stats_overview(), fetch_stats)

        assert fetch_count["list"][0] == 1
        assert fetch_count["item"][0] == 1
        assert fetch_count["stats"][0] == 1

        # 5. 失效缓存
        self.cache.invalidate_question(question_id)

        # 6. 再次获取（缓存全部失效）
        self.cache.get_questions_list(params, fetch_list)
        self.cache.get_question_item(question_id, fetch_item)
        self.cache.get_stats(CacheKeys.stats_overview(), fetch_stats)

        assert fetch_count["list"][0] == 2
        assert fetch_count["item"][0] == 2
        assert fetch_count["stats"][0] == 2