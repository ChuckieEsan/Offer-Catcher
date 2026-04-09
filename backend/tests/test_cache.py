"""测试 cache 模块的装饰器"""

import threading
import time

import pytest

from app.utils.cache import cached, singleton


class Counter:
    """简单计数器类，用于在闭包中追踪调用次数"""
    def __init__(self):
        self.count = 0


class TestCached:
    """测试 @cached 装饰器"""

    def test_basic_caching(self):
        """测试基本缓存功能"""
        counter = Counter()

        @cached
        def get_value(key: str) -> str:
            counter.count += 1
            return f"value_{key}"

        # 第一次调用
        result1 = get_value("a")
        assert result1 == "value_a"
        assert counter.count == 1

        # 相同参数，应返回缓存
        result2 = get_value("a")
        assert result2 == "value_a"
        assert counter.count == 1  # 未增加

        # 不同参数，应重新调用
        result3 = get_value("b")
        assert result3 == "value_b"
        assert counter.count == 2

    def test_kwargs_caching(self):
        """测试关键字参数缓存"""
        counter = Counter()

        @cached
        def compute(x: int, y: int = 0) -> int:
            counter.count += 1
            return x + y

        assert compute(1) == 1
        assert counter.count == 1

        assert compute(1) == 1  # 缓存
        assert counter.count == 1

        assert compute(1, y=2) == 3  # 不同参数
        assert counter.count == 2

        # 注意：(1, y=2) 和 (x=1, y=2) 生成不同的键
        # 这是预期行为：位置参数和关键字参数的键不同
        assert compute(1, y=2) == 3  # 缓存（与上一个调用相同）
        assert counter.count == 2

    def test_clear_cache(self):
        """测试清除缓存"""
        counter = Counter()

        @cached
        def get_value() -> int:
            counter.count += 1
            return counter.count

        assert get_value() == 1
        assert get_value() == 1  # 缓存

        # 清除缓存
        get_value.clear_cache()

        assert get_value() == 2  # 重新调用


class TestSingleton:
    """测试 @singleton 装饰器"""

    def test_basic_singleton(self):
        """测试基本单例功能"""
        @singleton
        def create_object() -> object:
            return object()

        obj1 = create_object()
        obj2 = create_object()

        # 应返回同一个实例
        assert obj1 is obj2

    def test_ignores_arguments(self):
        """测试忽略参数（文档警告的行为）"""
        counter = Counter()

        @singleton
        def create_with_arg(arg: str) -> str:
            counter.count += 1
            return arg

        # 第一次调用
        result1 = create_with_arg("first")
        assert result1 == "first"
        assert counter.count == 1

        # 第二次调用（不同参数）
        result2 = create_with_arg("second")
        # 返回的是第一次创建的实例
        assert result2 == "first"
        assert counter.count == 1  # 未重新调用

    def test_clear_cache(self):
        """测试 clear_cache 正确工作"""
        @singleton
        def create_object() -> object:
            return object()

        obj1 = create_object()
        assert obj1 is not None

        # 清除缓存
        create_object.clear_cache()

        # 应创建新实例
        obj2 = create_object()
        assert obj1 is not obj2  # 不同实例

        # 再次清除
        create_object.clear_cache()
        obj3 = create_object()
        assert obj2 is not obj3

    def test_thread_safety(self):
        """测试线程安全"""
        counter = Counter()
        results = []

        @singleton
        def create_slow() -> int:
            counter.count += 1
            time.sleep(0.01)  # 模拟慢初始化
            return counter.count

        def worker():
            result = create_slow()
            results.append(result)

        # 启动多个线程
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有线程应得到相同结果
        assert len(set(results)) == 1  # 只有一个唯一值

        # 只调用了一次（双重检查锁生效）
        assert counter.count == 1

    def test_thread_safety_with_clear_cache(self):
        """测试 clear_cache 在多线程环境下安全"""
        results = []

        @singleton
        def create_object() -> int:
            return len(results)  # 返回创建次数

        def worker_create():
            results.append(create_object())

        def worker_clear():
            create_object.clear_cache()

        # 先创建一个实例
        obj1 = create_object()
        assert obj1 == 0

        # 清除并多线程创建
        create_object.clear_cache()

        threads = [threading.Thread(target=worker_create) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有实例应该相同
        assert len(set(results)) == 1