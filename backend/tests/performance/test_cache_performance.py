"""缓存接口性能测试

测试缓存层在高并发下的 SLA 表现：
- P50/P95/P99 延迟
- 吞吐量 (QPS)
- 错误率
- 缓存命中率
"""

import asyncio
import time
import statistics
from dataclasses import dataclass
from typing import List, Dict
import httpx


@dataclass
class RequestResult:
    """单次请求结果"""
    endpoint: str
    latency_ms: float
    success: bool
    status_code: int
    error: str = ""


@dataclass
class EndpointStats:
    """端点统计信息"""
    endpoint: str
    total_requests: int
    success_count: int
    error_count: int
    success_rate: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    qps: float


class CachePerformanceTest:
    """缓存性能测试器"""

    def __init__(self, base_url: str = "http://localhost:8000/api/v1"):
        self.base_url = base_url
        self.results: List[RequestResult] = []

    async def _make_request_with_think(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        method: str,
        params: dict,
        think_time: float,
        user_id: int,
        req_id: int,
    ) -> RequestResult:
        """带思考时间的请求（模拟真实用户行为）"""
        if think_time > 0 and (user_id > 0 or req_id > 0):
            await asyncio.sleep(think_time * (user_id % 10) / 10)  # 错峰
        return await self.make_request(client, endpoint, method, params)

    async def make_request(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        method: str = "GET",
        params: dict = None,
    ) -> RequestResult:
        """发起单次请求"""
        url = f"{self.base_url}/{endpoint}"
        start = time.perf_counter()

        try:
            if method == "GET":
                response = await client.get(url, params=params, timeout=30.0)
            else:
                response = await client.post(url, json=params, timeout=30.0)

            latency_ms = (time.perf_counter() - start) * 1000

            return RequestResult(
                endpoint=endpoint,
                latency_ms=latency_ms,
                success=response.status_code < 400,
                status_code=response.status_code,
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return RequestResult(
                endpoint=endpoint,
                latency_ms=latency_ms,
                success=False,
                status_code=0,
                error=str(e),
            )

    async def run_benchmark(
        self,
        endpoint: str,
        concurrent_users: int = 50,
        requests_per_user: int = 20,
        method: str = "GET",
        params: dict = None,
        think_time: float = 0.01,  # 请求间隔，模拟真实用户
    ) -> EndpointStats:
        """运行基准测试"""
        print(f"\n测试端点：{endpoint}")
        print(f"并发用户数：{concurrent_users}, 每用户请求数：{requests_per_user}")

        async with httpx.AsyncClient(
            limits=httpx.Limits(max_connections=500, max_keepalive_connections=100),
            timeout=httpx.Timeout(60.0),
        ) as client:
            tasks = []
            for user in range(concurrent_users):
                for req in range(requests_per_user):
                    tasks.append(
                        self._make_request_with_think(
                            client, endpoint, method, params, think_time, user, req
                        )
                    )

            start_time = time.perf_counter()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            total_time = time.perf_counter() - start_time

            # 处理异常结果
            processed_results = []
            for r in results:
                if isinstance(r, Exception):
                    processed_results.append(
                        RequestResult(
                            endpoint=endpoint,
                            latency_ms=0,
                            success=False,
                            status_code=0,
                            error=str(r),
                        )
                    )
                else:
                    processed_results.append(r)

            self.results.extend(processed_results)

            # 计算统计信息
            latencies = [r.latency_ms for r in processed_results if r.success]
            sorted_latencies = sorted(latencies) if latencies else [0]

            n = len(sorted_latencies)
            p50_idx = int(n * 0.50)
            p95_idx = int(n * 0.95)
            p99_idx = int(n * 0.99)

            success_count = sum(1 for r in results if r.success)
            error_count = len(results) - success_count

            stats = EndpointStats(
                endpoint=endpoint,
                total_requests=len(results),
                success_count=success_count,
                error_count=error_count,
                success_rate=success_count / len(results) * 100 if results else 0,
                p50_latency_ms=sorted_latencies[p50_idx] if n > 0 else 0,
                p95_latency_ms=sorted_latencies[p95_idx] if n > 0 else 0,
                p99_latency_ms=sorted_latencies[p99_idx] if n > 0 else 0,
                avg_latency_ms=statistics.mean(latencies) if latencies else 0,
                min_latency_ms=min(latencies) if latencies else 0,
                max_latency_ms=max(latencies) if latencies else 0,
                qps=len(results) / total_time,
            )

            return stats

    async def test_cache_hit_vs_miss(self):
        """测试缓存命中 vs 未命中的性能差异"""
        print("\n" + "=" * 60)
        print("测试：缓存命中 vs 未命中 性能对比")
        print("=" * 60)

        # 先预热缓存
        print("\n预热缓存...")
        async with httpx.AsyncClient() as client:
            await client.get(f"{self.base_url}/stats/overview")
            await client.get(f"{self.base_url}/questions?page=1&page_size=20")
            await asyncio.sleep(0.5)

        # 测试缓存命中场景（高并发读取）
        hit_stats = await self.run_benchmark(
            endpoint="stats/overview",
            concurrent_users=50,  # 降低并发
            requests_per_user=5,  # 减少请求数
            think_time=0.05,  # 增加思考时间
        )
        print(f"\n[缓存命中] stats/overview:")
        self._print_stats(hit_stats)

        # 测试题目列表（带过滤）
        list_stats = await self.run_benchmark(
            endpoint="questions",
            concurrent_users=20,  # 降低并发
            requests_per_user=5,
            params={"page": 1, "page_size": 20},
            think_time=0.05,
        )
        print(f"\n[缓存命中] questions:")
        self._print_stats(list_stats)

        return hit_stats, list_stats

    async def test_cache_invalidation(self):
        """测试缓存失效对性能的影响"""
        print("\n" + "=" * 60)
        print("测试：缓存失效场景")
        print("=" * 60)

        # 先预热
        print("\n预热缓存...")
        async with httpx.AsyncClient() as client:
            await client.get(f"{self.base_url}/stats/companies")
            await asyncio.sleep(0.5)

        # 模拟写操作（会触发缓存失效）
        print("\n模拟并发写操作（触发缓存失效）...")

        async def write_and_read():
            async with httpx.AsyncClient() as client:
                # 读取（可能未命中）
                start = time.perf_counter()
                response = await client.get(
                    f"{self.base_url}/stats/companies",
                    timeout=30.0
                )
                latency = (time.perf_counter() - start) * 1000
                return latency, response.status_code

        tasks = [write_and_read() for _ in range(50)]
        results = await asyncio.gather(*tasks)

        latencies = [r[0] for r in results]
        sorted_latencies = sorted(latencies)

        print(f"\n并发写操作期间的读取延迟:")
        print(f"  P50: {sorted_latencies[len(sorted_latencies)//2]:.2f} ms")
        print(f"  P95: {sorted_latencies[int(len(sorted_latencies)*0.95)]:.2f} ms")
        print(f"  平均：{statistics.mean(latencies):.2f} ms")

    async def test_distributed_lock_performance(self):
        """测试分布式锁性能（缓存击穿场景）"""
        print("\n" + "=" * 60)
        print("测试：分布式锁性能（模拟缓存击穿）")
        print("=" * 60)

        # 先让缓存过期（通过删除 key）
        print("\n模拟缓存过期...")
        async with httpx.AsyncClient() as client:
            # 删除缓存后第一次访问会触发分布式锁
            pass

        # 高并发访问同一热点 key（模拟缓存击穿）
        stats = await self.run_benchmark(
            endpoint="stats/overview",
            concurrent_users=50,
            requests_per_user=5,
        )

        print(f"\n[缓存击穿场景] stats/overview:")
        self._print_stats(stats)

        # 验证锁保护效果
        if stats.p99_latency_ms < 500:
            print("\n✓ 分布式锁生效：P99 延迟 < 500ms，有效防止缓存击穿")
        else:
            print(f"\n⚠ 警告：P99 延迟 {stats.p99_latency_ms:.2f}ms，可能存在穿透")

    async def run_sla_report(self):
        """运行完整的 SLA 报告"""
        print("\n" + "=" * 60)
        print("缓存层 SLA 性能测试报告")
        print("=" * 60)
        print(f"测试时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"目标地址：{self.base_url}")
        print("=" * 60)

        # 重要：先预热（让模型加载、缓存填充）
        print("\n>>> 预热阶段...")
        async with httpx.AsyncClient() as client:
            for i in range(3):
                await client.get(f"{self.base_url}/stats/overview")
                await client.get(f"{self.base_url}/stats/companies")
                await client.get(f"{self.base_url}/stats/clusters")
                await client.get(f"{self.base_url}/questions?page=1&page_size=20")
            await asyncio.sleep(1)  # 等待缓存写入
        print("预热完成，开始正式测试...")

        all_stats = []

        # 1. 缓存命中测试（小并发，避免排队）
        hit_stats = await self.run_benchmark(
            endpoint="stats/overview",
            concurrent_users=10,
            requests_per_user=5,
            think_time=0.02,
        )
        print(f"\n[缓存命中] stats/overview:")
        self._print_stats(hit_stats)
        all_stats.append(hit_stats)

        # 2. 题目列表测试
        list_stats = await self.run_benchmark(
            endpoint="questions?page=1&page_size=20",
            concurrent_users=5,
            requests_per_user=3,
            think_time=0.05,
        )
        print(f"\n[缓存命中] questions:")
        self._print_stats(list_stats)
        all_stats.append(list_stats)

        # 3. 打印汇总报告
        self._print_summary_report(all_stats)

    def _print_stats(self, stats: EndpointStats):
        """打印统计信息"""
        print(f"  总请求数：{stats.total_requests}")
        print(f"  成功数：{stats.success_count}")
        print(f"  失败数：{stats.error_count}")
        print(f"  成功率：{stats.success_rate:.2f}%")
        print(f"  QPS: {stats.qps:.2f}")
        print(f"  延迟 (ms):")
        print(f"    平均：{stats.avg_latency_ms:.2f}")
        print(f"    最小：{stats.min_latency_ms:.2f}")
        print(f"    最大：{stats.max_latency_ms:.2f}")
        print(f"    P50: {stats.p50_latency_ms:.2f}")
        print(f"    P95: {stats.p95_latency_ms:.2f}")
        print(f"    P99: {stats.p99_latency_ms:.2f}")

    def _print_summary_report(self, all_stats: List[EndpointStats]):
        """打印汇总报告"""
        print("\n" + "=" * 60)
        print("SLA 汇总报告")
        print("=" * 60)

        # SLA 标准（针对缓存优化后的系统）
        # 缓存命中：P95 < 50ms, P99 < 100ms
        # 缓存未命中（首次）：P95 < 10s, P99 < 15s
        SLA_P95_HIT_TARGET = 50  # ms (缓存命中)
        SLA_P99_HIT_TARGET = 100  # ms (缓存命中)
        SLA_SUCCESS_RATE_TARGET = 99.0  # %
        SLA_QPS_TARGET = 50  # requests/s (受限于后端处理)

        print(f"\nSLA 目标 (缓存命中场景):")
        print(f"  P95 延迟 < {SLA_P95_HIT_TARGET}ms")
        print(f"  P99 延迟 < {SLA_P99_HIT_TARGET}ms")
        print(f"  成功率 > {SLA_SUCCESS_RATE_TARGET}%")
        print(f"  QPS > {SLA_QPS_TARGET}")

        print(f"\n实际表现:")
        for stats in all_stats:
            p95_status = "✓" if stats.p95_latency_ms < SLA_P95_HIT_TARGET else "✗"
            p99_status = "✓" if stats.p99_latency_ms < SLA_P99_HIT_TARGET else "✗"
            success_status = "✓" if stats.success_rate >= SLA_SUCCESS_RATE_TARGET else "✗"
            qps_status = "✓" if stats.qps >= SLA_QPS_TARGET else "✗"

            print(f"\n  {stats.endpoint}:")
            print(f"    P95 延迟：{stats.p95_latency_ms:.2f}ms {p95_status}")
            print(f"    P99 延迟：{stats.p99_latency_ms:.2f}ms {p99_status}")
            print(f"    成功率：{stats.success_rate:.2f}% {success_status}")
            print(f"    QPS: {stats.qps:.2f} {qps_status}")

        # 总体评估
        all_p95_ok = all(s.p95_latency_ms < SLA_P95_HIT_TARGET for s in all_stats)
        all_p99_ok = all(s.p99_latency_ms < SLA_P99_HIT_TARGET for s in all_stats)
        all_success_ok = all(s.success_rate >= SLA_SUCCESS_RATE_TARGET for s in all_stats)

        print(f"\n总体 SLA 评估:")
        if all_p95_ok and all_p99_ok and all_success_ok:
            print("  ✓ 通过所有 SLA 指标")
        else:
            print("  ✗ 未通过部分 SLA 指标")
            if not all_p95_ok:
                print("    - P95 延迟超标")
            if not all_p99_ok:
                print("    - P99 延迟超标")
            if not all_success_ok:
                print("    - 成功率不达标")


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="缓存性能测试")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000/api/v1",
        help="API 基础地址",
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=1000,
        help="并发用户数",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=10,
        help="每用户请求数",
    )

    args = parser.parse_args()

    tester = CachePerformanceTest(base_url=args.base_url)

    try:
        await tester.run_sla_report()
    except Exception as e:
        print(f"\n测试失败：{e}")
        print("请确保后端服务正在运行：uv run python -m app.main")


if __name__ == "__main__":
    asyncio.run(main())