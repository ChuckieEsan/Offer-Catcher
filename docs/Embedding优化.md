# Embedding 性能优化方案

## 背景

在压测工具调用时，发现 embedding 是主要瓶颈。当有大量并发 `search_questions` 调用时，每个请求都需要计算 embedding，导致吞吐量受限。

## 当前架构

```
search_questions 调用链：
  → RetrievalApplicationService.search_with_rerank()
    → EmbeddingAdapter.embed(context)  ← 瓶颈点（串行）
    → QuestionRepository.search()
    → RerankerAdapter.rerank()
```

## 基准测试数据

### 测试环境

- **模型**: BGE-M3 (1024 维向量)
- **数据来源**: 从 Qdrant 生产数据库抽样 100 道题目
- **测试文件**: `backend/tests/performance/test_embedding_benchmark.py`

### 单条 Embedding 延迟

| 指标 | 延迟 |
|------|------|
| 平均 | 47.24 ms |
| P50 | 29.67 ms |
| P95 | 380.69 ms |
| 稳定后 | ~30 ms |

**关键发现**：
1. 第一条请求有 **380ms warmup 开销**（CUDA kernel 编译/缓存预热）
2. 后续稳定在 **~30ms** 左右
3. 理论吞吐量：**约 33 条/秒**（单线程串行）

### 1000 次串行 Embedding 测试

测试配置：100 条数据 × 10 轮 = 1000 次

| 指标 | 数值 |
|------|------|
| **总耗时** | 32.19 秒 |
| **实测 QPS** | 31.1 |
| **稳定阶段平均延迟** | 30.88 ms |
| **P50 延迟** | 31.97 ms |
| **P95 延迟** | 37.98 ms |
| **GPU 利用率** | 12.4% |

**核心问题**：
- GPU 理论上限约 250 QPS，实测仅 31 QPS
- **利用率仅 12.4%**，GPU 大量空闲等待 CPU 提交
- 存在约 **8 倍优化空间**

**延迟分布分析**：
| 阶段 | 平均延迟 | 说明 |
|------|----------|------|
| 第一轮 (warmup) | 43.97 ms | CUDA kernel 预热 |
| 稳定阶段 | 30.88 ms | 正常运行 |
| Warmup 开销 | 13.08 ms | 额外开销 |

### 批量 Embedding 性能测试

测试不同 batch_size 对吞吐量的影响：

| batch_size | 总耗时 | 平均每条延迟 | 吞吐量 |
|------------|--------|-------------|--------|
| 1 | 325.94 ms | 325.94 ms | 3.1 QPS |
| 10 | 233.75 ms | 23.37 ms | 42.8 QPS |
| 16 | 275.65 ms | 17.23 ms | **67.3 QPS** |
| 32 | 568.27 ms | 17.76 ms | 56.3 QPS |
| 50 | 820.31 ms | 16.41 ms | 61.0 QPS |
| 100 | 1613.77 ms | 16.14 ms | 62.0 QPS |

**关键发现**：
1. **batch_size=16 效果最佳**，达到 67.3 QPS
2. batch_size 过大（>50）收益递减，延迟反而增加
3. 相比串行（31 QPS），批量处理提升约 **2.2 倍**

### 性能对比总结

| 方案 | 吞吐量 (QPS) | GPU 利用率 | 适用场景 |
|------|-------------|-----------|---------|
| 串行 (batch=1) | 31.1 | 12.4% | 单次查询 |
| batch=16 | 67.3 | 26.9% | 入库/批量处理 |
| batch=32 | 56.3 | 22.5% | 入库流程 |
| batch=100 | 62.0 | 24.8% | 大批量数据 |

**结论**：
- GPU 利用率仍仅 **26.9%**，距离理论上限 250 QPS 还有 **73% 空间**
- 批量处理优化了 GPU kernel 开销，但单线程仍是瓶颈
- 需要进一步测试线程池并发来提升 GPU 利用率

## 优化方案对比

### 方案 1: 线程池并行

```python
class EmbeddingAdapter:
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=4)
    
    def embed(self, text: str) -> list[float]:
        future = self._executor.submit(self._embeddings.embed_query, text)
        return future.result()
```

**优点**：
- 改动小，现有架构兼容
- 不阻塞主线程（async 场景）

**局限**：
- GPU 内部串行执行，多线程只是提交更快
- 线程数 > 4 会增加 CPU-GPU 同步开销

**适用场景**: 高并发请求（请求来自不同用户）

### 方案 2: 批量处理

```python
# 不逐条 embed，而是批量处理
texts = [q.context for q in questions]
vectors = embedding_adapter.embed_batch(texts)
```

**优点**：
- GPU 内部 batch 处理，效率最高
- 减少 kernel launch 开销

**局限**：
- 需要收集一批请求才能处理
- 单条请求场景不适用

**适用场景**: 入库流程、批量检索

### 方案 3: CUDA Streams

```python
# 单线程管理多个 CUDA 流
stream1 = torch.cuda.Stream()
stream2 = torch.cuda.Stream()

with torch.cuda.stream(stream1):
    output1 = model(input1)
with torch.cuda.stream(stream2):
    output2 = model(input2)
```

**优点**：
- 单线程开销更小
- CUDA 层面真正的并行

**局限**：
- 需要底层 PyTorch 修改
- LangChain HuggingFaceEmbeddings 不直接支持

### 方案 4: 模型服务化

使用专业的 embedding 服务（如 Text Embeddings Inference）：

```bash
# 启动 TEI 服务
docker run -p 8080:80 ghcr.io/huggingface/text-embeddings-inference:latest \
    --model-id BAAI/bge-m3
```

**优点**：
- 专业优化（inflight batching、FP16/FP8）
- 高吞吐、低延迟
- 支持多 GPU 扩展

**局限**：
- 需要额外部署
- 网络开销（本地调用影响较小）

## 官方最佳实践（来源调研）

### BGE-M3 官方建议

1. **FP16 精度**: `use_fp16=True` 可获得 ~2x 加速
2. **避免多进程池**: 单句子场景多进程启动开销远大于编码时间
3. **合理 batch_size**: 推荐 32-64

### Sentence-Transformers 建议

| 场景 | 推荐方案 |
|------|----------|
| 单 GPU + 单条查询 | 直接 `encode()`，无需线程池 |
| 单 GPU + 高并发 | 线程池 (2-4 threads) |
| 多 GPU | `encode_multi_process()` |
| 大批量数据 | 批量 `encode(batch_size=32)` |

### PyTorch 论坛建议

- GPU 是瓶颈，线程数不宜超过 GPU 并行能力
- 推荐单线程 + 队列，避免多线程 warmup 开销

## 待完成测试

以下测试需要补充数据：

1. 批量 embedding 性能（batch_size: 1, 10, 32, 50, 100）
2. 多线程并发测试（1, 2, 4, 8 线程）
3. 完整对比：逐条 vs 批量 vs 线程池

## 推荐方案

针对当前架构，推荐采用：

1. **短期**: 线程池优化（2-4 threads），改动最小
2. **中期**: 入库流程改为批量处理
3. **长期**: 模型服务化（TEI），应对更大规模

## 参考链接

- [Sentence-Transformers 效率优化](https://sbert.net/docs/sentence_transformer/usage/efficiency.html)
- [BGE-M3 FAQ](https://bge-model.com/FAQ/index.html)
- [CUDA 多线程 vs 多流](https://leimao.github.io/blog/Multi-Thread-Single-Stream-VS-Single-Thread-Multi-Stream-CUDA/)