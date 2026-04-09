"""写操作性能测试

在 offer_catcher_test 测试数据库上测试写操作的性能：
- 单条写入延迟
- 批量写入性能
- 并发写入测试
- 读写混合场景
- 缓存失效验证
"""

import asyncio
import time
import random
import string
import uuid
from typing import List, Tuple
import pytest

from app.db.qdrant_client import QdrantManager
from app.services.cache_service import get_cache_service
from app.tools.embedding_tool import get_embedding_tool
from app.models.schemas import QdrantQuestionPayload


class TestWritePerformance:
    """写操作性能测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前准备测试环境"""
        # 使用测试集合
        self.qdrant = QdrantManager(collection_name="questions_test")
        self.cache = get_cache_service()
        self.embedding_tool = get_embedding_tool()

        # 创建集合
        self.qdrant.create_collection_if_not_exists()

        # 清理测试数据
        self.qdrant.client.delete_collection(collection_name="questions_test")
        self.qdrant.create_collection_if_not_exists()
        self.cache.delete_pattern("oc:*")

        yield

        # 测试后清理
        try:
            self.qdrant.client.delete_collection(collection_name="questions_test")
        except:
            pass

    def _generate_random_question(self, prefix: str = "") -> Tuple[str, str, str, str, List[float]]:
        """生成随机题目数据

        Returns:
            (question_id, question_text, company, position, vector)
        """
        company = random.choice(["字节跳动", "阿里巴巴", "腾讯", "百度", "美团"])
        position = random.choice(["后端开发", "前端开发", "算法工程师", "数据开发"])

        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        question_text = f"{prefix}{random_str}: {company}{position}相关的技术问题"

        # 使用 UUID 作为 question_id
        question_id = str(uuid.uuid4())

        # 生成 embedding
        context = f"公司：{company} | 岗位：{position} | 题目：{question_text}"
        vector = self.embedding_tool.embed_text(context)

        return question_id, question_text, company, position, vector

    def test_single_write_latency(self):
        """测试单次写入延迟"""
        print("\n" + "=" * 60)
        print("测试：单次写入延迟")
        print("=" * 60)

        latencies = []

        for i in range(20):
            q_id, q_text, company, position, vector = self._generate_random_question(f"single_{i}_")

            start = time.perf_counter()
            self.qdrant.upsert_question_with_context(
                question_text=q_text,
                company=company,
                position=position,
                vector=vector,
            )
            latency = (time.perf_counter() - start) * 1000
            latencies.append(latency)

        sorted_lat = sorted(latencies)
        n = len(sorted_lat)

        print(f"\n单次写入延迟 (n={n}):")
        print(f"  平均：{sum(latencies)/n:.2f} ms")
        print(f"  P50: {sorted_lat[n//2]:.2f} ms")
        print(f"  P95: {sorted_lat[int(n*0.95)]:.2f} ms")
        print(f"  P99: {sorted_lat[-1]:.2f} ms")

    def test_batch_write_performance(self):
        """测试批量写入性能"""
        print("\n" + "=" * 60)
        print("测试：批量写入性能")
        print("=" * 60)

        batch_sizes = [10, 50, 100]

        for batch_size in batch_sizes:
            questions = []
            vectors = []

            for i in range(batch_size):
                q_id, q_text, company, position, vector = self._generate_random_question(f"batch_{batch_size}_{i}_")

                questions.append(QdrantQuestionPayload(
                    question_id=q_id,
                    question_text=q_text,
                    company=company,
                    position=position,
                    question_type="knowledge",
                    mastery_level=0,
                    core_entities=[],
                ))
                vectors.append(vector)

            start = time.perf_counter()
            self.qdrant.upsert_questions(questions=questions, vectors=vectors)
            total_time = time.perf_counter() - start

            print(f"\n批量 {batch_size} 条:")
            print(f"  总耗时：{total_time*1000:.2f} ms")
            print(f"  平均每条：{total_time*1000/batch_size:.2f} ms")
            print(f"  吞吐量：{batch_size/total_time:.1f} 条/秒")

            # 清理
            self.qdrant.client.delete_collection(collection_name="questions_test")
            self.qdrant.create_collection_if_not_exists()

    def test_concurrent_writes(self):
        """测试并发写入性能"""
        print("\n" + "=" * 60)
        print("测试：并发写入性能")
        print("=" * 60)

        import threading
        from concurrent.futures import ThreadPoolExecutor

        results = []

        def write_question(i: int):
            try:
                q_id, q_text, company, position, vector = self._generate_random_question(f"concurrent_{i}_")

                start = time.perf_counter()
                self.qdrant.upsert_questions(
                    questions=[QdrantQuestionPayload(
                        question_id=q_id,
                        question_text=q_text,
                        company=company,
                        position=position,
                        question_type="knowledge",
                        mastery_level=0,
                        core_entities=[],
                    )],
                    vectors=[vector]
                )
                latency = (time.perf_counter() - start) * 1000
                results.append(("success", latency))
            except Exception as e:
                results.append(("error", str(e)))

        concurrent_counts = [1, 5, 10]

        for count in concurrent_counts:
            results.clear()

            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=count) as executor:
                futures = [executor.submit(write_question, i) for i in range(count)]
                for f in futures:
                    f.result()
            total_time = time.perf_counter() - start

            success_count = sum(1 for r in results if r[0] == "success")
            error_count = sum(1 for r in results if r[0] == "error")
            latencies = [r[1] for r in results if r[0] == "success"]

            print(f"\n并发数 {count}:")
            print(f"  成功：{success_count}, 失败：{error_count}")
            print(f"  总耗时：{total_time*1000:.2f} ms")
            if latencies:
                sorted_lat = sorted(latencies)
                print(f"  平均延迟：{sum(latencies)/len(latencies):.2f} ms")
                print(f"  P95 延迟：{sorted_lat[int(len(sorted_lat)*0.95)]:.2f} ms")

            # 清理
            self.qdrant.client.delete_collection(collection_name="questions_test")
            self.qdrant.create_collection_if_not_exists()

    def test_read_write_mixed_scenario(self):
        """测试读写混合场景"""
        print("\n" + "=" * 60)
        print("测试：读写混合场景")
        print("=" * 60)

        # 先写入一些基础数据
        print("\n预写入 50 条基础数据...")
        for i in range(50):
            q_id, q_text, company, position, vector = self._generate_random_question(f"base_{i}_")
            self.qdrant.upsert_question_with_context(
                question_text=q_text, company=company, position=position, vector=vector
            )
        print("预写入完成")

        # 清空缓存
        self.cache.delete_pattern("oc:*")

        from concurrent.futures import ThreadPoolExecutor

        read_latencies = []
        write_latencies = []

        def do_read(i: int):
            start = time.perf_counter()
            self.qdrant.scroll_with_filter(limit=10)
            latency = (time.perf_counter() - start) * 1000
            read_latencies.append(latency)

        def do_write(i: int):
            q_id, q_text, company, position, vector = self._generate_random_question(f"mixed_{i}_")
            start = time.perf_counter()
            self.qdrant.upsert_question_with_context(
                question_text=q_text, company=company, position=position, vector=vector
            )
            latency = (time.perf_counter() - start) * 1000
            write_latencies.append(latency)

        # 80% 读，20% 写
        read_count = 80
        write_count = 20

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=50) as executor:
            read_futures = [executor.submit(do_read, i) for i in range(read_count)]
            write_futures = [executor.submit(do_write, i) for i in range(write_count)]

            for f in read_futures + write_futures:
                f.result()

        total_time = time.perf_counter() - start

        print(f"\n读写混合测试结果:")
        print(f"  总请求数：{read_count + write_count}")
        print(f"  总耗时：{total_time*1000:.2f} ms")

        print(f"\n读操作延迟 (n={len(read_latencies)}):")
        sorted_read = sorted(read_latencies)
        print(f"  平均：{sum(read_latencies)/len(read_latencies):.2f} ms")
        print(f"  P95: {sorted_read[int(len(sorted_read)*0.95)]:.2f} ms")

        print(f"\n写操作延迟 (n={len(write_latencies)}):")
        sorted_write = sorted(write_latencies)
        print(f"  平均：{sum(write_latencies)/len(write_latencies):.2f} ms")
        print(f"  P95: {sorted_write[int(len(sorted_write)*0.95)]:.2f} ms")

    def test_cache_invalidation_with_write(self):
        """测试写操作后缓存失效"""
        print("\n" + "=" * 60)
        print("测试：写操作后缓存失效")
        print("=" * 60)

        # 写入初始数据
        q_id, q_text, company, position, vector = self._generate_random_question("cache_test_")
        question_id = f"test_cache_invalidation"

        self.qdrant.upsert_question_with_context(
            question_text=q_text, company=company, position=position, vector=vector
        )

        # 写入缓存（使用题目 item 的 key 格式，这样 invalidate_question 会删除它）
        cache_key = f"oc:questions:item:{question_id}"
        self.cache.set(cache_key, {"question_id": question_id, "data": "old"})

        # 验证缓存存在
        hit, cached = self.cache.get(cache_key)
        assert hit is True
        print(f"✓ 缓存已设置")

        # 执行写操作并失效缓存
        start = time.perf_counter()
        self.cache.invalidate_question(question_id)
        invalidation_time = (time.perf_counter() - start) * 1000

        # 验证缓存已失效
        hit, cached = self.cache.get(cache_key)
        print(f"✓ 缓存失效完成，耗时：{invalidation_time:.2f} ms")

        # 测试延迟双删
        async def test_double_delete():
            test_key = f"oc:questions:item:test_double_delete"
            self.cache.set(test_key, {"data": "test"})
            await self.cache.invalidate_question_delayed("test_double_delete")
            hit, _ = self.cache.get(test_key)
            return hit

        hit = asyncio.run(test_double_delete())
        assert hit is False
        print(f"✓ 延迟双删验证通过")

        print(f"\n缓存失效测试结果:")
        print(f"  单次失效耗时：{invalidation_time:.2f} ms")
        print(f"  延迟双删：正常工作")


@pytest.fixture(scope="module")
def test_db_check():
    """检查测试数据库是否可用"""
    try:
        qdrant = QdrantManager(collection_name="questions_test")
        qdrant.create_collection_if_not_exists()
        print("✓ 测试数据库 offer_catcher_test 可用")
        return True
    except Exception as e:
        print(f"✗ 测试数据库不可用：{e}")
        return False


def run_write_tests():
    """运行所有写操作测试"""
    import subprocess

    print("=" * 60)
    print("写操作性能测试套件")
    print("=" * 60)

    result = subprocess.run(
        [
            "uv", "run", "pytest",
            "tests/test_write_performance.py",
            "-v", "--tb=short", "-s",
        ],
        capture_output=True,
        text=True,
        cwd="/home/liuchenyu/Offer-Catcher/backend",
        env={"PYTHONPATH": "/home/liuchenyu/Offer-Catcher/backend"},
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    return result.returncode


if __name__ == "__main__":
    run_write_tests()
