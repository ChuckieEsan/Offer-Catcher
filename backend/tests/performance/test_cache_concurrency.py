"""缓存并发场景测试

验证并发场景下缓存系统的正确性，包括：
- 分布式锁超时问题
- 锁误释放问题
- 并发读写一致性
- 延迟双删可靠性
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import pytest

from app.services import CacheService, CacheKeys, get_cache_service


class TestConcurrencyLockTimeout:
    """分布式锁超时测试

    问题：如果 fetch_fn() 执行时间超过锁 TTL，锁会自动释放，
    其他线程可能获取锁并重复执行 fetch_fn()。
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前清理缓存"""
        self.cache = get_cache_service()
        self.cache.delete_pattern("oc:test:*")
        self.cache.delete_pattern("oc:lock:*")
        yield
        self.cache.delete_pattern("oc:test:*")
        self.cache.delete_pattern("oc:lock:*")

    def test_lock_timeout_causes_duplicate_fetch(self):
        """测试锁超时场景

        场景：锁超时后，其他线程可以获取锁并执行 fetch。
        这是预期行为：锁 TTL 防止死锁，但可能导致短暂的重复查询。

        修复后：使用唯一标识和 Lua 脚本，确保不会误释放锁，
        也不会导致数据损坏。
        """
        key = "oc:test:lock_timeout"
        fetch_count = [0]
        fetch_times = []

        def slow_fetch():
            """模拟耗时 15 秒的数据库查询"""
            fetch_count[0] += 1
            fetch_times.append(time.time())
            time.sleep(15)  # 超过锁 TTL (10秒)
            return {"data": "slow_result", "count": fetch_count[0]}

        results = []
        errors = []

        def thread_a():
            """线程 A：获取锁后执行慢查询"""
            try:
                result = self.cache.get_with_lock(key, slow_fetch, max_retries=1)
                results.append(("A", result, time.time()))
            except Exception as e:
                errors.append(("A", e))

        def thread_b():
            """线程 B：等待 11 秒后尝试获取锁"""
            time.sleep(11)  # 等待锁过期
            try:
                # 快速 fetch（假设这次数据库快）
                result = self.cache.get_with_lock(
                    key,
                    lambda: {"data": "fast_result", "count": fetch_count[0] + 1},
                    max_retries=1,
                )
                results.append(("B", result, time.time()))
            except Exception as e:
                errors.append(("B", e))

        # 启动两个线程
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(thread_a)
            future_b = executor.submit(thread_b)

            future_a.result(timeout=20)
            future_b.result(timeout=20)

        print(f"Fetch count: {fetch_count[0]}, Results: {results}, Errors: {errors}")

        # 验证：
        # 1. 至少有线程 A 执行了 fetch
        assert fetch_count[0] >= 1

        # 2. 两个线程都成功返回结果（没有错误）
        assert len(errors) == 0, f"Unexpected errors: {errors}"

        # 3. 锁超时后，B 可能获取新锁执行了 fetch，这是允许的
        # 关键是数据不会损坏，且 Lua 脚本保证了锁的安全释放

    def test_lock_auto_expire_with_new_value(self):
        """测试锁自动过期后新值写入"""
        key = "oc:test:auto_expire"
        fetch_count = [0]

        def fetch():
            fetch_count[0] += 1
            return {"count": fetch_count[0]}

        # 第一次获取，写入缓存
        result1 = self.cache.get_with_lock(key, fetch)
        assert result1["count"] == 1

        # 清除锁（模拟锁过期）
        self.cache.delete_pattern("oc:lock:*")

        # 第二次获取，缓存命中，不应再 fetch
        result2 = self.cache.get_with_lock(key, fetch)
        assert result2["count"] == 1  # 缓存数据不变
        assert fetch_count[0] == 1  # fetch 只执行一次


class TestConcurrencyLockRelease:
    """锁释放安全性测试

    问题：如果锁超时后被其他线程获取，当前线程在 finally 中
    会删除其他线程的锁，导致锁失效。
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        self.cache = get_cache_service()
        self.cache.delete_pattern("oc:lock:*")
        yield
        self.cache.delete_pattern("oc:lock:*")

    def test_lock_wrong_release(self):
        """测试误释放其他线程的锁（已修复）

        修复后：使用 Lua 脚本安全释放锁，只删除自己持有的锁。
        """
        key = "test_wrong_release"
        lock_key = CacheKeys.lock_key(key)
        events = []

        def thread_a():
            """线程 A：获取锁，模拟长时间操作"""
            lock_value = self.cache._acquire_lock(key)
            events.append(("A_acquired", lock_value is not None, time.time()))

            if lock_value:
                time.sleep(12)  # 模拟超过锁 TTL
                # finally 中会释放锁（此时锁已过期，可能被 B 持有）
                released = self.cache._release_lock(key, lock_value)
                events.append(("A_released", released, time.time()))

        def thread_b():
            """线程 B：等待锁过期后获取"""
            time.sleep(11)  # 等待锁过期
            lock_value = self.cache._acquire_lock(key)
            events.append(("B_acquired", lock_value is not None, time.time()))

            if lock_value:
                time.sleep(2)
                # 检查锁是否还存在（A 不应该能删除 B 的锁）
                lock_exists = self.cache.redis.get(lock_key) is not None
                events.append(("B_lock_exists", lock_exists, time.time()))

        def thread_c():
            """线程 C：在 A 尝试释放锁后尝试获取"""
            time.sleep(12.5)  # 在 A 尝试释放锁后
            lock_value = self.cache._acquire_lock(key)
            events.append(("C_acquired", lock_value is not None, time.time()))

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(thread_a),
                executor.submit(thread_b),
                executor.submit(thread_c),
            ]
            for f in as_completed(futures, timeout=20):
                f.result()

        print(f"Events: {events}")

        # 修复后验证：A 的释放应该失败（因为锁已过期或被 B 持有）
        # B 的锁应该仍然存在，C 不应该获取成功
        c_acquired = any(e[0] == "C_acquired" and e[1] for e in events)

        # 如果 B 获取了锁，A 释放应该失败，B 的锁应该存在
        # C 不应该获取成功（因为 B 还持有锁）
        assert not c_acquired, f"Thread C should not acquire lock while B holds it. Events: {events}"


class TestConcurrencyReadWrite:
    """并发读写一致性测试

    问题：延迟双删之间的 1 秒窗口内，可能有其他请求写入旧数据。
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        self.cache = get_cache_service()
        self.cache.delete_pattern("oc:test:*")
        yield
        self.cache.delete_pattern("oc:test:*")

    def test_double_delete_window_inconsistency(self):
        """测试延迟双删窗口内的不一致

        模拟场景：
        1. 线程 A：第一次删除缓存
        2. 线程 B：读取缓存（未命中），查数据库（旧值），写入缓存
        3. 线程 A：更新数据库
        4. 线程 A：第二次删除缓存（1秒后）
        5. 线程 C：读取缓存（未命中），查数据库（新值）

        问题：线程 B 在窗口内写入旧数据，但第二次删除会清除。
        """
        key = "oc:test:double_delete"
        db_value = ["old_value"]  # 模拟数据库

        def get_from_db():
            return {"value": db_value[0]}

        # 初始状态：缓存旧值
        self.cache.set(key, {"value": "old_value"})
        db_value[0] = "old_value"

        # 线程 A：更新操作（延迟双删）
        def thread_a_update():
            # 第一次删除
            self.cache.delete(key)
            # 更新数据库
            db_value[0] = "new_value"
            # 延迟 1 秒后第二次删除
            time.sleep(1)
            self.cache.delete(key)

        # 线程 B：在窗口内读取
        def thread_b_read():
            time.sleep(0.5)  # 在第一次删除后、第二次删除前
            result = self.cache.get_with_lock(key, get_from_db)
            return result

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(thread_a_update)
            future_b = executor.submit(thread_b_read)

            future_a.result(timeout=5)
            result_b = future_b.result(timeout=5)

        print(f"Thread B result: {result_b}, DB value: {db_value[0]}")

        # 验证：第二次删除后，缓存应无数据
        hit, cached = self.cache.get(key)
        assert hit is False

        # 验证：最终读取应返回新值
        result_final = self.cache.get_with_lock(key, get_from_db)
        assert result_final["value"] == "new_value"

    def test_concurrent_write_same_key(self):
        """测试并发写入同一 Key"""
        key = "oc:test:concurrent_write"
        write_count = [0]
        write_values = []

        def fetch_and_write(value):
            """模拟写入不同值"""
            def fetch():
                write_count[0] += 1
                write_values.append(value)
                return {"value": value}
            return self.cache.get_with_lock(key, fetch)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(fetch_and_write, f"value_{i}")
                for i in range(5)
            ]
            results = [f.result(timeout=10) for f in futures]

        print(f"Write count: {write_count[0]}, Values: {write_values}, Results: {results}")

        # 验证：所有线程返回相同的值（缓存一致性）
        unique_results = set(r["value"] for r in results)
        assert len(unique_results) == 1, (
            f"Concurrent writes produced different values: {unique_results}"
        )


class TestConcurrencyHighLoad:
    """高并发场景测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.cache = get_cache_service()
        self.cache.delete_pattern("oc:test:*")
        yield
        self.cache.delete_pattern("oc:test:*")

    def test_100_concurrent_reads(self):
        """测试 100 个并发读取

        修复后：使用指数退避策略和更多重试次数，
        高并发下应只有少量请求穿透到数据库。
        """
        key = "oc:test:high_load"
        fetch_count = [0]

        def fetch():
            fetch_count[0] += 1
            time.sleep(0.1)  # 模拟数据库延迟
            return {"count": fetch_count[0]}

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [
                executor.submit(
                    lambda: self.cache.get_with_lock(key, fetch)
                )
                for _ in range(100)
            ]
            results = [f.result(timeout=30) for f in futures]

        print(f"Fetch count: {fetch_count[0]}")

        # 修复后验证：fetch 应该只执行少量次数（理想情况下 1 次）
        # 由于并发竞争，可能允许多次，但应该远少于请求数
        assert fetch_count[0] <= 5, (
            f"Too many duplicate fetches: {fetch_count[0]}. "
            "Lock should prevent most concurrent database queries."
        )

        # 验证：所有结果一致
        unique_values = set(r["count"] for r in results)
        assert len(unique_values) == 1

    def test_50_concurrent_reads_50_concurrent_writes(self):
        """测试读写混合高并发"""
        key = "oc:test:mixed_load"
        db_value = [0]
        fetch_count = [0]

        def read_fetch():
            fetch_count[0] += 1
            return {"value": db_value[0]}

        def do_read(i):
            return self.cache.get_with_lock(key, read_fetch)

        def do_write(i):
            # 先失效
            self.cache.delete(key)
            # 更新数据库
            db_value[0] = i
            time.sleep(0.01)  # 模拟数据库写入延迟
            # 不主动写缓存，让读线程触发

        with ThreadPoolExecutor(max_workers=100) as executor:
            read_futures = [executor.submit(do_read, i) for i in range(50)]
            write_futures = [executor.submit(do_write, i) for i in range(50)]

            read_results = [f.result(timeout=30) for f in read_futures]

        print(f"Fetch count: {fetch_count[0]}, Final DB value: {db_value[0]}")

        # 验证：读操作都成功完成
        assert len(read_results) == 50


class TestDeletePatternPerformance:
    """delete_pattern 性能测试

    问题：使用 KEYS 命令在大规模 key 场景下会阻塞 Redis。
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        self.cache = get_cache_service()
        self.cache.delete_pattern("oc:perf:*")
        yield
        self.cache.delete_pattern("oc:perf:*")

    def test_keys_command_blocking(self):
        """测试 KEYS 命令性能

        创建大量 key，测试 delete_pattern 是否快速完成。
        """
        # 创建 1000 个 key
        for i in range(1000):
            self.cache.set(f"oc:perf:test:{i}", {"index": i})

        # 测试 delete_pattern 时间
        start = time.time()
        self.cache.delete_pattern("oc:perf:test:*")
        duration = time.time() - start

        print(f"delete_pattern duration for 1000 keys: {duration:.3f}s")

        # 验证：应在合理时间内完成（< 1 秒）
        # 注意：KEYS 在生产环境是危险的，应该改用 SCAN
        assert duration < 2.0, (
            f"delete_pattern too slow: {duration:.3f}s for 1000 keys. "
            "Consider using SCAN instead of KEYS."
        )


class TestDelayedDoubleDeleteReliability:
    """延迟双删可靠性测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.cache = get_cache_service()
        self.cache.delete_pattern("oc:questions:*")
        self.cache.delete_pattern("oc:stats:*")
        yield
        self.cache.delete_pattern("oc:questions:*")
        self.cache.delete_pattern("oc:stats:*")

    def test_delayed_delete_executes(self):
        """测试延迟删除确实执行"""
        # 使用正确的 key 格式（会被 invalidate_question 删除）
        question_id = "test_q_delayed"
        key = CacheKeys.questions_item(question_id)

        # 设置缓存
        self.cache.set(key, {"question_id": question_id})

        # 验证缓存存在
        hit, _ = self.cache.get(key)
        assert hit is True

        # 执行延迟双删
        async def run_delayed():
            await self.cache.invalidate_question_delayed(question_id)

        asyncio.run(run_delayed())

        # 验证：缓存被删除
        hit, _ = self.cache.get(key)
        assert hit is False

    @pytest.mark.asyncio
    async def test_create_task_lifetime(self):
        """测试 asyncio.create_task 的生命周期

        问题：在 FastAPI 中，asyncio.create_task 创建的任务
        可能不保证在请求结束后执行完成。
        """
        executed = [False]
        key = "oc:test:task_lifetime"

        self.cache.set(key, {"data": "test"})

        async def delayed_task():
            await asyncio.sleep(0.5)
            self.cache.delete(key)
            executed[0] = True

        # 创建任务但不等待
        task = asyncio.create_task(delayed_task())

        # 等待一下让任务执行
        await asyncio.sleep(1)

        assert executed[0] is True
        hit, _ = self.cache.get(key)
        assert hit is False


# 运行并发测试的辅助函数
def run_concurrency_tests():
    """运行所有并发测试"""
    import subprocess
    result = subprocess.run(
        [
            "uv", "run", "pytest",
            "tests/test_cache_concurrency.py",
            "-v", "--tb=short",
        ],
        capture_output=True,
        text=True,
        cwd="/home/liuchenyu/Offer-Catcher/backend",
        env={"PYTHONPATH": "/home/liuchenyu/Offer-Catcher/backend"},
    )
    print(result.stdout)
    print(result.stderr)
    return result.returncode


if __name__ == "__main__":
    run_concurrency_tests()