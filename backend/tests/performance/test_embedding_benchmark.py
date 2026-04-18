"""Embedding 性能基准测试

从生产 Qdrant 数据库抽样题目，用于测试 embedding 性能。

测试目标：
1. 单条 embedding 延迟
2. 批量 embedding 性能
3. 多线程并发 embedding
4. 不同 batch_size 的吞吐量对比
"""

import json
import random
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import List

import pytest


# ============================================================================
# 数据抽样工具
# ============================================================================


def sample_questions_from_qdrant(
    collection_name: str = "questions",
    sample_size: int = 100,
    output_file: str = "embedding_benchmark_data.json",
) -> List[dict]:
    """从 Qdrant 生产数据库抽样题目

    Args:
        collection_name: Qdrant 集合名称（生产库）
        sample_size: 抽样数量
        output_file: 输出 JSON 文件名

    Returns:
        抽样的题目列表
    """
    from app.infrastructure.persistence.qdrant.client import QdrantClient

    # 连接生产数据库
    client = QdrantClient(collection_name=collection_name)

    # 获取总数
    total_count = client.count()
    print(f"Qdrant 总题目数: {total_count}")

    if total_count < sample_size:
        print(f"题目数量不足，将抽取所有 {total_count} 条")
        sample_size = total_count

    # 遍历获取所有题目
    all_questions = []
    offset = None
    batch_size = 1000

    print("正在遍历数据库...")
    while len(all_questions) < total_count:
        results, offset = client.scroll(limit=batch_size, offset=offset)

        for point in results:
            if point.payload:
                all_questions.append({
                    "question_id": point.id,
                    "question_text": point.payload.get("question_text", ""),
                    "company": point.payload.get("company", ""),
                    "position": point.payload.get("position", ""),
                    "question_type": point.payload.get("question_type", ""),
                    "core_entities": point.payload.get("core_entities", []),
                })

        if offset is None:
            break

        print(f"已获取 {len(all_questions)} / {total_count}")

    # 随机抽样
    print(f"\n随机抽样 {sample_size} 条...")
    sampled = random.sample(all_questions, sample_size)

    # 构建用于 embedding 的上下文文本
    benchmark_data = []
    for q in sampled:
        entities_str = ",".join(q.get("core_entities", [])) if q.get("core_entities") else "综合"
        context = (
            f"公司：{q['company']} | "
            f"岗位：{q['position']} | "
            f"类型：{q['question_type']} | "
            f"考点：{entities_str} | "
            f"题目：{q['question_text']}"
        )
        benchmark_data.append({
            "question_id": q["question_id"],
            "context": context,
            "question_text": q["question_text"],
            "company": q["company"],
            "position": q["position"],
        })

    # 导出到 JSON
    output_path = Path(__file__).parent / output_file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, ensure_ascii=False, indent=2)

    print(f"已导出到: {output_path}")

    return benchmark_data


# ============================================================================
# Embedding 性能测试
# ============================================================================


class TestEmbeddingPerformance:
    """Embedding 性能基准测试"""

    @pytest.fixture(scope="class")
    def benchmark_data(self):
        """加载基准测试数据"""
        data_file = Path(__file__).parent / "embedding_benchmark_data.json"

        if not data_file.exists():
            print("\n基准数据文件不存在，从 Qdrant 抽样...")
            return sample_questions_from_qdrant()

        print(f"\n加载基准数据: {data_file}")
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"数据量: {len(data)} 条")
        return data

    @pytest.fixture(scope="class")
    def embedding_adapter(self):
        """加载 Embedding 模型"""
        from app.infrastructure.adapters.embedding_adapter import EmbeddingAdapter

        print("\n加载 Embedding 模型...")
        adapter = EmbeddingAdapter()
        print("模型加载完成")
        return adapter

    def test_single_embedding_latency(self, benchmark_data, embedding_adapter):
        """测试单条 embedding 延迟"""
        print("\n" + "=" * 60)
        print("测试：单条 Embedding 延迟")
        print("=" * 60)

        latencies = []

        for i, item in enumerate(benchmark_data[:20]):
            context = item["context"]

            start = time.perf_counter()
            embedding_adapter.embed(context)
            latency = (time.perf_counter() - start) * 1000
            latencies.append(latency)

            if i < 5:
                print(f"  第 {i+1} 条: {latency:.2f} ms")

        sorted_lat = sorted(latencies)
        n = len(sorted_lat)

        print(f"\n单条 Embedding 延迟 (n={n}):")
        print(f"  平均: {sum(latencies)/n:.2f} ms")
        print(f"  P50: {sorted_lat[n//2]:.2f} ms")
        print(f"  P95: {sorted_lat[int(n*0.95)]:.2f} ms")
        print(f"  P99: {sorted_lat[-1]:.2f} ms")

    def test_batch_embedding_performance(self, benchmark_data, embedding_adapter):
        """测试批量 embedding 性能"""
        print("\n" + "=" * 60)
        print("测试：批量 Embedding 性能")
        print("=" * 60)

        batch_sizes = [1, 10, 32, 50, 100]

        for batch_size in batch_sizes:
            contexts = [item["context"] for item in benchmark_data[:batch_size]]

            start = time.perf_counter()
            vectors = embedding_adapter.embed_batch(contexts)
            total_time = time.perf_counter() - start

            print(f"\n批量 {batch_size} 条:")
            print(f"  总耗时: {total_time*1000:.2f} ms")
            print(f"  平均每条: {total_time*1000/batch_size:.2f} ms")
            print(f"  吞吐量: {batch_size/total_time:.1f} 条/秒")
            print(f"  向量维度: {len(vectors[0])}")

    def test_concurrent_embedding_with_thread_pool(
        self, benchmark_data, embedding_adapter
    ):
        """测试多线程并发 embedding"""
        print("\n" + "=" * 60)
        print("测试：多线程并发 Embedding")
        print("=" * 60)

        thread_counts = [1, 2, 4, 8]
        test_count = 50  # 每次测试处理 50 条

        for thread_count in thread_counts:
            contexts = [item["context"] for item in benchmark_data[:test_count]]

            results = []
            errors = []

            def embed_one(ctx: str):
                try:
                    start = time.perf_counter()
                    embedding_adapter.embed(ctx)
                    latency = (time.perf_counter() - start) * 1000
                    results.append(latency)
                except Exception as e:
                    errors.append(str(e))

            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=thread_count) as executor:
                futures = [executor.submit(embed_one, ctx) for ctx in contexts]
                for f in futures:
                    f.result()
            total_time = time.perf_counter() - start

            success_count = len(results)
            error_count = len(errors)

            print(f"\n线程数 {thread_count}:")
            print(f"  成功: {success_count}, 失败: {error_count}")
            print(f"  总耗时: {total_time*1000:.2f} ms")
            print(f"  吞吐量: {success_count/total_time:.1f} 条/秒")

            if results:
                sorted_lat = sorted(results)
                print(f"  平均延迟: {sum(results)/len(results):.2f} ms")
                print(f"  P95 延迟: {sorted_lat[int(len(sorted_lat)*0.95)]:.2f} ms")

    def test_1000_serial_embeddings(self, benchmark_data, embedding_adapter):
        """测试 1000 次串行 embedding（100 条数据 x 10 轮）"""
        print("\n" + "=" * 60)
        print("测试：1000 次串行 Embedding")
        print("=" * 60)

        # 100 条数据重复 10 次 = 1000 次
        contexts = [item["context"] for item in benchmark_data]
        total_count = 1000
        rounds = 10

        print(f"测试配置: {len(contexts)} 条数据 x {rounds} 轮 = {total_count} 次")
        print("开始测试...")

        latencies = []
        total_start = time.perf_counter()

        for round_idx in range(rounds):
            round_start = time.perf_counter()
            for i, ctx in enumerate(contexts):
                start = time.perf_counter()
                embedding_adapter.embed(ctx)
                latency = (time.perf_counter() - start) * 1000
                latencies.append(latency)

            round_time = (time.perf_counter() - round_start) * 1000
            print(f"  第 {round_idx + 1} 轮完成: {round_time:.2f} ms")

        total_time = time.perf_counter() - total_start

        # 统计分析
        # 去掉第一轮 warmup 数据
        warmup_latencies = latencies[:len(contexts)]
        stable_latencies = latencies[len(contexts):]

        sorted_all = sorted(latencies)
        sorted_stable = sorted(stable_latencies)
        n_all = len(sorted_all)
        n_stable = len(sorted_stable)

        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)

        print(f"\n总耗时: {total_time:.2f} s ({total_time*1000:.2f} ms)")
        print(f"吞吐量: {total_count/total_time:.1f} 条/秒 (QPS)")

        print(f"\n全部数据延迟统计 (n={n_all}):")
        print(f"  平均: {sum(latencies)/n_all:.2f} ms")
        print(f"  P50: {sorted_all[n_all//2]:.2f} ms")
        print(f"  P95: {sorted_all[int(n_all*0.95)]:.2f} ms")
        print(f"  P99: {sorted_all[-1]:.2f} ms")
        print(f"  最小: {sorted_all[0]:.2f} ms")
        print(f"  最大: {sorted_all[-1]:.2f} ms")

        print(f"\n稳定阶段延迟统计 (去掉第一轮 warmup, n={n_stable}):")
        print(f"  平均: {sum(stable_latencies)/n_stable:.2f} ms")
        print(f"  P50: {sorted_stable[n_stable//2]:.2f} ms")
        print(f"  P95: {sorted_stable[int(n_stable*0.95)]:.2f} ms")
        print(f"  P99: {sorted_stable[-1]:.2f} ms")

        print(f"\nWarmup 分析:")
        warmup_avg = sum(warmup_latencies) / len(warmup_latencies)
        stable_avg = sum(stable_latencies) / len(stable_latencies)
        print(f"  第一轮平均: {warmup_avg:.2f} ms")
        print(f"  稳定阶段平均: {stable_avg:.2f} ms")
        print(f"  Warmup 开销: {warmup_avg - stable_avg:.2f} ms")

        # GPU 理论上限对比
        print(f"\n性能评估:")
        actual_qps = total_count / total_time
        theoretical_max = 250  # 用户预估的 GPU 上限
        utilization = actual_qps / theoretical_max * 100
        print(f"  实测 QPS: {actual_qps:.1f}")
        print(f"  理论上限: {theoretical_max}")
        print(f"  GPU 利用率: {utilization:.1f}%")

        return {
            "total_count": total_count,
            "total_time": total_time,
            "qps": actual_qps,
            "avg_latency_ms": sum(stable_latencies) / n_stable,
        }

    def test_full_benchmark_all_100(self, benchmark_data, embedding_adapter):
        """完整基准测试：处理全部 100 条数据"""
        print("\n" + "=" * 60)
        print("测试：完整基准测试 (100 条)")
        print("=" * 60)

        contexts = [item["context"] for item in benchmark_data]

        # 方案 1: 逐条处理
        print("\n方案 1: 逐条处理")
        start = time.perf_counter()
        for ctx in contexts:
            embedding_adapter.embed(ctx)
        serial_time = time.perf_counter() - start
        print(f"  总耗时: {serial_time*1000:.2f} ms")
        print(f"  吞吐量: {len(contexts)/serial_time:.1f} 条/秒")

        # 方案 2: 批量处理
        print("\n方案 2: 批量处理 (batch_size=32)")
        start = time.perf_counter()
        batch_size = 32
        for i in range(0, len(contexts), batch_size):
            batch = contexts[i:i+batch_size]
            embedding_adapter.embed_batch(batch)
        batch_time = time.perf_counter() - start
        print(f"  总耗时: {batch_time*1000:.2f} ms")
        print(f"  吞吐量: {len(contexts)/batch_time:.1f} 条/秒")

        # 方案 3: 线程池并发
        print("\n方案 3: 线程池并发 (4 threads)")
        results = []

        def embed_one(ctx: str):
            embedding_adapter.embed(ctx)

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(embed_one, ctx) for ctx in contexts]
            for f in futures:
                f.result()
        thread_time = time.perf_counter() - start
        print(f"  总耗时: {thread_time*1000:.2f} ms")
        print(f"  吞吐量: {len(contexts)/thread_time:.1f} 条/秒")

        # 性能对比
        print("\n性能对比:")
        print(f"  逐条 vs 批量: {serial_time/batch_time:.2f}x (批量更快)")
        print(f"  逐条 vs 线程池: {serial_time/thread_time:.2f}x (线程池更快)")

        return {
            "serial_time": serial_time,
            "batch_time": batch_time,
            "thread_time": thread_time,
        }


# ============================================================================
# 数据抽样独立运行
# ============================================================================


def run_sample(args: list[str]):
    """独立运行数据抽样"""
    sample_size = int(args[0]) if len(args) > 0 else 100
    output_file = args[1] if len(args) > 1 else "embedding_benchmark_data.json"

    print("=" * 60)
    print("Embedding 基准测试数据抽样")
    print("=" * 60)
    print(f"抽样数量: {sample_size}")
    print(f"输出文件: {output_file}")

    sample_questions_from_qdrant(
        sample_size=sample_size,
        output_file=output_file,
    )


def run_benchmark():
    """运行基准测试"""
    import subprocess

    print("=" * 60)
    print("Embedding 性能基准测试")
    print("=" * 60)

    result = subprocess.run(
        [
            "uv", "run", "pytest",
            "tests/performance/test_embedding_benchmark.py",
            "-v", "--tb=short", "-s",
            "-k", "test_full_benchmark",
        ],
        capture_output=True,
        text=True,
        cwd="/home/liuchenyu/Offer-Catcher/backend",
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    return result.returncode


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "sample":
        run_sample(sys.argv[2:])
    else:
        run_benchmark()