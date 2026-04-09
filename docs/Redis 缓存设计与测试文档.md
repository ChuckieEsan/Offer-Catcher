# Redis 缓存设计文档

## 概述

本系统引入 Redis 缓存层，优化 Qdrant 向量数据库的查询性能，同时保证分钟级数据一致性。

## 架构设计

```
┌──────────────────────────────────────────────────────────────┐
│                         客户端                                │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                      FastAPI 路由层                           │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                     CacheService                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  1. 查 Redis 缓存                                        │ │
│  │  2. Miss → 查 Qdrant → 写 Redis                         │ │
│  │  3. 写操作 → 失效缓存                                    │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
           │                              │
           ▼                              ▼
┌─────────────────────┐      ┌─────────────────────┐
│       Redis         │      │       Qdrant        │
│   (缓存层, 5min TTL) │      │    (持久化存储)      │
└─────────────────────┘      └─────────────────────┘
```

## 一致性策略

### 方案：TTL + 主动失效 + 延迟双删

| 策略 | 说明 | 作用 |
|------|------|------|
| TTL 兜底 | 所有缓存 5 分钟过期 | 极端情况下的最终一致性保证 |
| 主动失效 | 写操作后立即删除缓存 | 大部分情况下实时一致 |
| 延迟双删 | 写操作后延迟 1 秒再次删除 | 解决并发读写导致的脏数据 |

### 写入流程

```
API 写操作:
1. 删除 Redis 缓存（第一次）
2. 写 Qdrant
3. 延迟 1 秒
4. 再次删除 Redis 缓存（第二次）

Worker 异步写:
1. 写 Qdrant
2. 删除 Redis 缓存
```

### 读取流程

```
1. 查 Redis 缓存
2. Hit → 直接返回
3. Miss → 查 Qdrant → 写 Redis (TTL 5分钟) → 返回
```

## Redis Key 设计

### Key 命名规范

```
{业务前缀}:{模块}:{具体标识}
```

- **业务前缀**: `oc` (offer-catcher 缩写)
- **模块**: stats, questions, user 等
- **具体标识**: ID 或参数哈希

### Key 列表

| Key | 说明 | TTL |
|-----|------|-----|
| `oc:stats:overview` | 总览统计 | 5min |
| `oc:stats:clusters` | 聚类统计列表 | 5min |
| `oc:stats:companies` | 公司统计列表 | 5min |
| `oc:questions:list:{hash}` | 题目列表（按过滤条件） | 5min |
| `oc:questions:item:{id}` | 单个题目 | 5min |

### Key 管理器

```python
class CacheKeys:
    """Redis Key 管理器"""
    
    PREFIX = "oc"
    TTL_MINUTES = 5
    
    @classmethod
    def stats_overview(cls) -> str:
        return f"{cls.PREFIX}:stats:overview"
    
    @classmethod
    def stats_clusters(cls) -> str:
        return f"{cls.PREFIX}:stats:clusters"
    
    @classmethod
    def questions_list(cls, filter_hash: str) -> str:
        return f"{cls.PREFIX}:questions:list:{filter_hash}"
    
    @classmethod
    def questions_item(cls, question_id: str) -> str:
        return f"{cls.PREFIX}:questions:item:{question_id}"
    
    @classmethod
    def questions_list_pattern(cls) -> str:
        return f"{cls.PREFIX}:questions:list:*"
    
    @classmethod
    def ttl_seconds(cls) -> int:
        return cls.TTL_MINUTES * 60
```

## 失效策略

### 失效场景

| 操作 | 失效范围 |
|------|---------|
| 新增题目 | 列表缓存、统计缓存 |
| 更新题目 | 列表缓存、统计缓存、单个题目缓存 |
| 删除题目 | 列表缓存、统计缓存、单个题目缓存 |
| 重新生成答案 | 单个题目缓存 |
| 聚类更新 | 列表缓存、统计缓存 |

### 失效实现

```python
def invalidate_question(question_id: str = None):
    """失效题目相关缓存"""
    # 1. 删除题目列表缓存（所有过滤组合）
    redis.delete_pattern("oc:questions:list:*")
    
    # 2. 删除统计数据缓存
    redis.delete("oc:stats:overview", "oc:stats:clusters", "oc:stats:companies")
    
    # 3. 删除单个题目缓存
    if question_id:
        redis.delete(f"oc:questions:item:{question_id}")
```

## CacheService 实现

```python
class CacheService:
    """缓存服务"""
    
    def get_questions_list(self, filter_params: dict, fetch_fn: callable):
        """获取题目列表（带缓存）"""
        key = CacheKeys.questions_list(self._hash_params(filter_params))
        
        # 1. 查缓存
        cached = redis.get(key)
        if cached:
            return json.loads(cached)
        
        # 2. 查 Qdrant
        questions = fetch_fn()
        
        # 3. 写缓存
        redis.setex(key, CacheKeys.ttl_seconds(), json.dumps(questions))
        return questions
    
    def invalidate_question(self, question_id: str = None):
        """失效缓存"""
        redis.delete_pattern(CacheKeys.questions_list_pattern())
        redis.delete(CacheKeys.stats_overview(), CacheKeys.stats_clusters())
        if question_id:
            redis.delete(CacheKeys.questions_item(question_id))
    
    async def invalidate_question_delayed(self, question_id: str = None):
        """延迟双删"""
        self.invalidate_question(question_id)
        await asyncio.sleep(1)
        self.invalidate_question(question_id)
```

## 跨进程一致性

### 问题

API 进程和 Worker 进程都会写入 Qdrant，需要确保两边都能正确失效缓存。

### 解决方案

1. **统一失效入口**: API 和 Worker 都调用 `CacheService.invalidate_question()`
2. **Redis 作为协调层**: 缓存失效操作通过 Redis 完成，不依赖进程间通信
3. **TTL 兜底**: 即使失效失败，5 分钟后缓存也会自动过期

```
┌──────────┐                    ┌──────────┐
│   API    │                    │  Worker  │
└────┬─────┘                    └────┬─────┘
     │                               │
     │  写 Qdrant                     │  异步写 Qdrant
     │                               │
     ├───────────────┬───────────────┤
     │               │               │
     ▼               ▼               ▼
┌──────────┐   ┌──────────┐   ┌──────────┐
│ Qdrant   │   │  Redis   │   │ Qdrant   │
└──────────┘   └──────────┘   └──────────┘
                    │
              删除缓存 Key
              (两边都调用)
```

## 缓存三灾防护

### 缓存雪崩

**风险**：所有 Key TTL 相同（5分钟），可能同时过期，导致大量请求穿透到 Qdrant。

**解决方案**：TTL 随机化

```python
import random

BASE_TTL = 300  # 5 分钟
RANDOM_RANGE = 60  # 随机 ±1 分钟

def get_ttl() -> int:
    """获取随机化 TTL，避免同时过期"""
    return BASE_TTL + random.randint(-RANDOM_RANGE, RANDOM_RANGE)
```

### 缓存击穿

**风险**：热点 Key（如 `oc:stats:overview`）过期瞬间，大量并发请求穿透到数据库。

**解决方案**：分布式锁 + 双重检查

```python
def get_with_lock(self, key: str, fetch_fn: callable, ttl: int = None):
    """带分布式锁的缓存读取"""
    # 1. 查缓存
    cached = self.redis.get(key)
    if cached:
        return json.loads(cached)
    
    # 2. 获取分布式锁
    lock_key = f"lock:{key}"
    if self.redis.setnx(lock_key, 1, ex=10):  # 10秒锁
        try:
            # 3. 双重检查
            cached = self.redis.get(key)
            if cached:
                return json.loads(cached)
            
            # 4. 查数据库
            data = fetch_fn()
            
            # 5. 写缓存
            self.redis.setex(key, ttl or get_ttl(), json.dumps(data))
            return data
        finally:
            self.redis.delete(lock_key)
    else:
        # 6. 等待锁释放后重试
        time.sleep(0.1)
        return self.get_with_lock(key, fetch_fn, ttl)
```

**适用场景**：
- 热点统计数据（`stats:overview`、`stats:clusters`）
- 高频查询的题目列表

### 缓存穿透

**风险**：查询不存在的 question_id 或无效过滤条件，每次都穿透到数据库。

**解决方案**：缓存空值

```python
NULL_MARKER = "__NULL__"
NULL_TTL = 60  # 空值缓存 1 分钟

def get_question(self, question_id: str) -> Optional[dict]:
    """获取单个题目（防穿透）"""
    key = CacheKeys.questions_item(question_id)
    
    # 1. 查缓存
    cached = self.redis.get(key)
    if cached == NULL_MARKER:
        return None  # 命中空值标记
    if cached:
        return json.loads(cached)
    
    # 2. 查数据库
    question = self.qdrant.get_question(question_id)
    
    # 3. 写缓存
    if question:
        self.redis.setex(key, get_ttl(), json.dumps(question.model_dump()))
    else:
        # 缓存空值，TTL 较短
        self.redis.setex(key, NULL_TTL, NULL_MARKER)
    
    return question
```

### 防护策略汇总

| 问题 | 风险 | 解决方案 | 适用场景 |
|------|------|---------|---------|
| 缓存雪崩 | 大量 Key 同时过期 | TTL 随机化 | 所有 Key |
| 缓存击穿 | 热点 Key 过期瞬间 | 分布式锁 | 统计数据、热门列表 |
| 缓存穿透 | 查询不存在的数据 | 缓存空值 | 单个题目查询 |

---

## 性能指标

### SLA 目标（缓存命中场景）

| 指标 | 目标值 | 说明 |
|------|--------|------|
| P95 延迟 | < 50ms | 95% 请求的延迟上限 |
| P99 延迟 | < 100ms | 99% 请求的延迟上限 |
| 成功率 | > 99% | 请求成功率 |
| QPS | > 50 | 每秒查询数（受限于后端处理） |

### 实际性能数据（2026-04-09 测试）

**测试环境**:
- 本地开发环境（WSL2）
- Redis 6.x
- Qdrant 1.13.x
- 测试工具：asyncio + perf_counter

**缓存命中 vs 未命中对比（系统冷启动后）**:

| 指标 | 缓存命中 | 缓存未命中 | 提升倍数 |
|------|---------|-----------|---------|
| **平均延迟** | 0.64 ms | 65.07 ms | **102x** |
| **P50 延迟** | 0.56 ms | 63.13 ms | **112x** |
| **P95 延迟** | 1.47 ms | 87.93 ms | **60x** |
| **吞吐量** | 1569 QPS | 15 QPS | **102x** |

**结论**: 系统冷启动完成后，缓存命中带来约 **100 倍** 的性能提升。

**各场景详细数据**:

| 场景 | P50 | P95 | P99 | 说明 |
|------|-----|-----|-----|------|
| 纯 Redis GET | 0.8ms | 1.1ms | 1.5ms | 仅 Redis 网络往返 + 反序列化 |
| 完整 API（缓存命中） | 0.56ms | 1.47ms | 2.0ms | HTTP + FastAPI + Redis |
| Qdrant 查询（缓存未命中） | 63ms | 88ms | 98ms | 包含向量检索 + 序列化 |

**性能提升总结**:
- 缓存命中 vs 未命中：**~100x** 延迟提升（65ms → 0.6ms）
- 缓存层 overhead：仅 **~1ms**（纯 Redis 操作）
- 系统吞吐量：从 15 QPS 提升至 1500+ QPS

### 分布式锁性能

| 场景 | 指标 | 数值 |
|------|------|------|
| 锁获取延迟 | P95 | < 5ms |
| 锁释放延迟 | P95 | < 2ms |
| 并发 100 读 | 穿透到 DB 次数 | ≤ 3 次 |
| 锁 TTL | 默认 | 10 秒 |

### 高并发压力测试（1000 并发）

**测试场景**：1000 个并发用户同时访问缓存 API

| 指标 | 缓存命中 | 缓存未命中 |
|------|---------|-----------|
| **总请求数** | 1000 | 100 |
| **实际 QPS** | 2170 | 130 |
| **平均延迟** | 0.45 ms | 7.02 ms |
| **P95 延迟** | 0.87 ms | 65.68 ms |
| **P99 延迟** | 1.08 ms | 71.69 ms |
| **成功率** | 100% | 100% |

**关键发现**：
1. 缓存命中时，1000 并发下系统吞吐量达 **2170 QPS**
2. P99 延迟仅 **1.08ms**，高并发下表现稳定
3. 缓存未命中时，吞吐量降至 **130 QPS**（下降 16 倍）
4. 分布式锁在 1000 并发下正常工作，无系统崩溃

**不同并发数对比**：

| 并发数 | QPS（缓存命中） | P99 延迟 |
|--------|----------------|----------|
| 100 | 1569 | 2.0ms |
| 1000 | 2170 | 1.08ms |

> **注意**：1000 并发下 QPS 反而更高，因为批量发送减少了事件循环空闲时间，Redis 连接池利用更充分，网络开销被摊薄。

### 写操作性能测试（测试数据库：offer_catcher_test）

**测试环境**：
- Qdrant collection: `questions_test`
- 测试用例：`tests/test_write_performance.py`

**单次写入延迟**：

| 指标 | 数值 |
|------|------|
| 平均延迟 | 12.27 ms |
| P50 延迟 | 11.40 ms |
| P95 延迟 | 21.08 ms |
| P99 延迟 | 21.08 ms |

**批量写入性能**：

| 批量大小 | 总耗时 | 平均每条 | 吞吐量 |
|---------|--------|---------|--------|
| 10 条 | 47.00 ms | 4.70 ms | 212.8 条/秒 |
| 50 条 | 64.82 ms | 1.30 ms | 771.4 条/秒 |
| 100 条 | 129.69 ms | 1.30 ms | 771.0 条/秒 |

**并发写入性能**：

| 并发数 | 成功率 | 总耗时 | 平均延迟 | P95 延迟 | P99 延迟 | 吞吐量 |
|--------|-------|--------|---------|---------|---------|--------|
| 1 | 100% | 85.58 ms | 15.58 ms | 15.58 ms | 15.58 ms | ~12 items/s |
| 5 | 100% | 538.21 ms | 55.11 ms | 111.61 ms | - | ~9 items/s |
| 10 | 100% | 813.41 ms | 18.55 ms | 25.85 ms | - | ~12 items/s |
| 100 | 100% | 9824 ms | 501.75 ms | 704.38 ms | 755.37 ms | ~10 items/s |

**读写混合场景（80% 读 + 20% 写）**：

| 操作类型 | 平均延迟 | P95 延迟 |
|---------|---------|---------|
| 读操作 | ~50ms | ~100ms |
| 写操作 | ~15ms | ~25ms |

**缓存失效性能**：

| 操作 | 平均耗时 | 说明 |
|------|----------|------|
| 单 Key 删除 | < 5ms | Redis DELETE + 模式删除 |
| 延迟双删 | ~1s | 包含 1 秒延迟等待 |

**结论**：
1. 单次写入延迟约 **12ms**（包含 embedding 计算）
2. 批量写入吞吐量最高可达 **770 条/秒**
3. 并发写入时，所有请求成功率 **100%**
4. 缓存失效在 **5ms** 内完成，延迟双删正常工作
5. **100 并发写入**：平均延迟 **502ms**，P95 延迟 **704ms**，吞吐量约 **10 items/s**
   - 高并发下延迟显著增加，主要受限于 Qdrant 串行处理 + Embedding 计算开销
   - 建议生产环境控制并发写入在 10 以内，或采用批量写入提升吞吐量

---

## 后续优化方向

1. **Redis 缓存预热**: 应用启动时预加载热点数据
2. **本地缓存层**: 引入 LRU 本地缓存，减少 Redis 网络开销
3. **缓存监控**: 添加命中率、延迟等监控指标
4. **智能 TTL**: 根据数据热度动态调整 TTL
5. **SCAN 替代 KEYS**: 大规模 key 场景下使用 SCAN 命令避免阻塞