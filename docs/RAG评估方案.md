# Offer-Catcher RAG 检索评估方案

> 文档版本：v1.0  
> 更新时间：2026-04-17  
> 目标：系统化评估 RAG 检索质量，量化优化效果

---

## 目录

1. [评估目标与范围](#一评估目标与范围)
2. [评估指标体系](#二评估指标体系)
3. [测试数据集构建](#三测试数据集构建)
4. [实验设计](#四实验设计)
5. [评估代码实现](#五评估代码实现)
6. [评估工具与框架](#六评估工具与框架)
7. [实验流程](#七实验流程)
8. [结果分析框架](#八结果分析框架)
9. [迭代优化路径](#九迭代优化路径)
10. [附录：测试数据模板](#附录测试数据模板)

---

## 一、评估目标与范围

### 1.1 核心目标

| 目标 | 说明 | 优先级 |
|------|------|--------|
| **量化检索质量** | 用 Recall、Precision、MRR 等指标客观评估 | P0 |
| **对比优化效果** | Baseline vs Reranker vs Graph 增强 | P0 |
| **发现问题模式** | 找出低召回率的 query pattern | P1 |
| **建立评估流水线** | 可复用的自动化评估流程 | P1 |

### 1.2 评估范围

```
┌─────────────────────────────────────────────────────────────┐
│ 本次评估聚焦：检索层（Retrieval）                              │
│                                                              │
│ 检索层 ←───── 本次评估 ─────→ 生成层（暂不评估）               │
│                                                              │
│ - search_questions Tool                                      │
│ - 向量召回 + Reranker 精排                                    │
│ - query_graph Tool（可选评估）                                │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 不在本次范围

- 生成层评估（Faithfulness、Answer Relevance）
- 端到端 RAG 评估（用户满意度）
- 系统性能评估（延迟、吞吐量）

---

## 二、评估指标体系

### 2.1 核心指标定义

#### Recall@K（召回率）

> **定义**：Top-K 结果中包含相关文档的比例
> 
> **公式**：`Recall@K = |relevant ∩ retrieved_top_k| / |relevant|`
> 
> **含义**：覆盖率，衡量检索系统是否找到了所有相关文档

```python
def recall_at_k(relevant_ids: list[str], retrieved_ids: list[str], k: int) -> float:
    top_k = set(retrieved_ids[:k])
    rel_set = set(relevant_ids)
    if not rel_set:
        return 0.0
    return len(top_k & rel_set) / len(rel_set)
```

**示例**：
- Ground truth: [A, B, C]（3 个相关文档）
- Retrieved Top-5: [A, D, E, B, F]
- Recall@5 = |{A, B} ∩ {A, B, C}| / 3 = 2/3 = 0.67

#### Precision@K（准确率）

> **定义**：Top-K 结果中相关文档的占比
> 
> **公式**：`Precision@K = |relevant ∩ retrieved_top_k| / K`
> 
> **含义**：准确度，衡量检索结果的"纯净度"

```python
def precision_at_k(relevant_ids: list[str], retrieved_ids: list[str], k: int) -> float:
    top_k = set(retrieved_ids[:k])
    rel_set = set(relevant_ids)
    return len(top_k & rel_set) / k
```

**示例**：
- Ground truth: [A, B, C]
- Retrieved Top-5: [A, D, E, B, F]
- Precision@5 = 2/5 = 0.4

#### MRR（Mean Reciprocal Rank）

> **定义**：第一个相关文档排名倒数的平均值
> 
> **公式**：`MRR = 1/N * Σ(1/rank_i)`
> 
> **含义**：排序质量，关注第一个正确答案的位置

```python
def mrr(relevant_ids: list[str], retrieved_ids: list[str]) -> float:
    rel_set = set(relevant_ids)
    for i, doc_id in enumerate(retrieved_ids):
        if doc_id in rel_set:
            return 1.0 / (i + 1)
    return 0.0
```

**示例**：
- Query 1: 第一个相关文档在位置 2 → RR = 1/2 = 0.5
- Query 2: 第一个相关文档在位置 1 → RR = 1/1 = 1.0
- MRR = (0.5 + 1.0) / 2 = 0.75

#### NDCG@K（Normalized Discounted Cumulative Gain）

> **定义**：考虑位置权重的排序质量归一化指标
> 
> **公式**：`NDCG@K = DCG@K / IDCG@K`
> 
> **含义**：精细排序质量，高相关文档排在前面得分更高

```python
def dcg_at_k(relevance_scores: list[int], k: int) -> float:
    """DCG = Σ(2^rel_i - 1 / log2(i+1))"""
    dcg = 0.0
    for i, rel in enumerate(relevance_scores[:k]):
        dcg += (2 ** rel - 1) / math.log2(i + 2)
    return dcg

def ndcg_at_k(relevance_scores: list[int], ideal_scores: list[int], k: int) -> float:
    """NDCG = DCG / IDCG"""
    dcg = dcg_at_k(relevance_scores, k)
    idcg = dcg_at_k(sorted(ideal_scores, reverse=True), k)
    if idcg == 0:
        return 0.0
    return dcg / idcg
```

**示例**：
- 相关性评分：[3, 0, 1, 0, 2]（Top-5，3=高度相关，2=中度，1=低度）
- 理想排序：[3, 2, 1, 0, 0]
- DCG@5 = (2³-1)/log₂(2) + (2¹-1)/log₂(4) + (2²-1)/log₂(6) = 7 + 0.5 + 1.5 = 9
- IDCG@5 = (2³-1)/log₂(2) + (2²-1)/log₂(3) + (2¹-1)/log₂(4) = 7 + 3 + 0.5 = 10.5
- NDCG@5 = 9/10.5 ≈ 0.86

#### Hit@K（命中率）

> **定义**：Top-K 中是否至少包含一个相关文档
> 
> **公式**：`Hit@K = 1 if |relevant ∩ retrieved_top_k| > 0 else 0`
> 
> **含义**：简化版召回，适合快速评估

```python
def hit_at_k(relevant_ids: list[str], retrieved_ids: list[str], k: int) -> int:
    top_k = set(retrieved_ids[:k])
    rel_set = set(relevant_ids)
    return 1 if len(top_k & rel_set) > 0 else 0
```

### 2.2 指标选择建议

| 评估场景 | 推荐指标 | 原因 |
|---------|---------|------|
| **快速评估** | Hit@5, Precision@5 | 简单直观 |
| **全面评估** | Recall@5/10, Precision@5/10, MRR, NDCG@5 | 覆盖多维度 |
| **排序优化** | MRR, NDCG@K | 关注排序质量 |
| **覆盖率评估** | Recall@K | 关注是否遗漏 |

### 2.3 期望指标目标

| 指标 | Baseline（纯向量） | +Reranker | +Graph 增强 |
|------|-------------------|-----------|-------------|
| Recall@5 | 55-65% | 65-75% | 70-80% |
| Precision@5 | 40-50% | 55-65% | 60-70% |
| MRR | 0.35-0.45 | 0.50-0.60 | 0.55-0.65 |
| NDCG@5 | 0.45-0.55 | 0.60-0.70 | 0.65-0.75 |
| Hit@5 | 70-80% | 80-90% | 85-95% |

---

## 三、测试数据集构建

### 3.1 数据集设计原则

| 原则 | 说明 |
|------|------|
| **真实性** | 使用真实题目数据，而非合成数据 |
| **多样性** | 覆盖不同查询类型、不同领域 |
| **可复现** | 固定测试集，便于对比不同配置 |
| **规模适中** | 100-200 条测试用例，兼顾效率和覆盖 |

### 3.2 查询类型分类

| 类型 | 定义 | 数量建议 | 示例 |
|------|------|---------|------|
| **精确匹配** | Query = 原题目文本 | 40-50 | "什么是 RAG？" |
| **语义相似** | Query 是题目的改写/变形 | 30-40 | "RAG 技术怎么理解？" |
| **关键词查询** | Query 是关键词组合 | 20-30 | "字节跳动 RAG 面试题" |
| **概念查询** | Query 是知识点名称 | 10-20 | "向量检索相关题目" |
| **多文档查询** | Query 期望召回多道相关题 | 10-15 | "Agent 架构设计题目" |

### 3.3 构建方案

#### 方案 A：从真实数据构建（推荐）

**步骤 1：抽样题目**

```python
# 从 Qdrant 随机抽取题目
import random

def sample_questions(total: int = 100) -> list[Question]:
    """分层抽样，保证公司/岗位/类型多样性"""
    all_questions = question_repo.find_all()
    
    # 分层抽样
    by_company = group_by(all_questions, "company")
    by_type = group_by(all_questions, "question_type")
    
    sampled = []
    for company, questions in by_company.items():
        sampled.extend(random.sample(questions, min(5, len(questions))))
    
    return sampled[:total]
```

**步骤 2：构造测试用例**

```python
from dataclasses import dataclass

@dataclass
class TestCase:
    """测试用例"""
    query: str                      # 查询文本
    relevant_ids: list[str]         # Ground truth（相关文档 ID）
    query_type: str                 # 查询类型
    company: str | None = None      # 公司（可选过滤）
    position: str | None = None     # 岗位（可选过滤）
    difficulty: str = "medium"      # 预估难度

def build_test_cases_from_questions(questions: list[Question]) -> list[TestCase]:
    """从题目构建测试用例"""
    test_cases = []
    
    for q in questions:
        # 类型 1：精确匹配
        test_cases.append(TestCase(
            query=q.question_text,
            relevant_ids=[q.question_id],
            query_type="exact_match",
            company=q.company,
            position=q.position,
        ))
        
        # 类型 2：语义相似（改写）
        rewritten_queries = generate_similar_queries(q.question_text)
        for rq in rewritten_queries:
            test_cases.append(TestCase(
                query=rq,
                relevant_ids=[q.question_id],
                query_type="semantic_similar",
            ))
    
    return test_cases
```

**步骤 3：LLM 辅助生成相似查询**

```python
async def generate_similar_queries(original: str, n: int = 2) -> list[str]:
    """用 LLM 生成语义相似的查询表述"""
    
    prompt = f"""将以下面试题改写为 {n} 种不同的表述方式，保持语义相同：

原题目：{original}

要求：
1. 改写后的表述应该是面试中常见的问法
2. 保持核心知识点不变
3. 可以改变句式、增删修饰词

输出格式（JSON 数组）：
["改写1", "改写2"]
"""
    
    response = await llm.ainvoke(prompt)
    return json.loads(response)
```

#### 方案 B：人工标注（最准确）

| 步骤 | 说明 | 工作量 |
|------|------|--------|
| 1. 抽样 | 从 Qdrant 抽取 50 道代表性题目 | - |
| 2. 编写查询 | 每道题编写 2-3 个自然语言查询 | ~2 小时 |
| 3. 标注相关文档 | 标注哪些题目应该被召回 | ~3 小时 |
| 4. 交叉验证 | 两人独立标注，讨论不一致项 | ~1 小时 |

**标注模板**：

```markdown
# 测试用例标注表

| ID | 原题目 | 查询 | 相关文档 ID | 标注人 |
|----|--------|------|-------------|--------|
| 001 | 什么是 RAG？ | RAG 技术原理是什么 | [q_001] | 张三 |
| 002 | 什么是 RAG？ | 检索增强生成怎么做 | [q_001] | 张三 |
| 003 | 如何优化 RAG 召回率？ | RAG 优化方法 | [q_002, q_005] | 李四 |
```

### 3.4 测试数据集存储

```python
# 存储为 JSON 文件，便于版本管理
import json

def save_test_dataset(test_cases: list[TestCase], path: str):
    """保存测试数据集"""
    data = [tc.__dict__ for tc in test_cases]
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_test_dataset(path: str) -> list[TestCase]:
    """加载测试数据集"""
    with open(path, "r") as f:
        data = json.load(f)
    return [TestCase(**item) for item in data]
```

**文件位置**：`backend/tests/eval/rag_test_dataset.json`

---

## 四、实验设计

### 4.1 对比实验矩阵

| 实验编号 | 配置名称 | 向量模型 | Reranker | k 值 | 目标 |
|---------|---------|---------|---------|------|------|
| **E0** | Baseline | BGE-M3 | 无 | 10 | 纯向量检索能力 |
| **E1** | +Reranker | BGE-M3 | BGE-Reranker | 15→5 | Reranker 增益 |
| **E2** | +Context | BGE-M3 | BGE-Reranker | 15→5 | 上下文拼接优化 |
| **E3** | +Graph | BGE-M3 | BGE-Reranker | 15→5 | Graph 增强（可选） |

### 4.2 实验详细配置

#### E0: Baseline（纯向量检索）

```python
# 配置
config_e0 = {
    "embedding_model": "BGE-M3",
    "reranker": None,
    "recall_k": 10,  # 向量召回数量
    "final_k": 10,   # 最终返回数量
    "context_format": "题目：{query}",  # 简单格式
}

# 检索流程
def search_baseline(query: str, k: int = 10) -> list[str]:
    context = f"题目：{query}"
    vector = embedding.embed(context)
    results = qdrant.search(vector, limit=k)
    return [r.question_id for r in results]
```

#### E1: +Reranker（向量召回 + 精排）

```python
# 配置
config_e1 = {
    "embedding_model": "BGE-M3",
    "reranker": "BGE-Reranker-base",
    "recall_k": 15,  # 多召回候选
    "final_k": 5,    # 精排后返回
    "context_format": "题目：{query}",
}

# 检索流程
def search_with_reranker(query: str, k: int = 5) -> list[str]:
    # Stage 1: 向量召回
    context = f"题目：{query}"
    vector = embedding.embed(context)
    candidates = qdrant.search(vector, limit=k * 3)
    
    # Stage 2: Rerank 精排
    candidate_texts = [c.question_text for c in candidates]
    ranked_indices = reranker.rerank(query, candidate_texts, top_k=k)
    
    return [candidates[idx].question_id for idx, _ in ranked_indices]
```

#### E2: +Context（上下文拼接优化）

```python
# 配置
config_e2 = {
    "embedding_model": "BGE-M3",
    "reranker": "BGE-Reranker-base",
    "recall_k": 15,
    "final_k": 5,
    "context_format": "公司：{company} | 岗位：{position} | 题目：{query}",  # 与入库一致
}

# 检索流程（同 E1，但上下文格式优化）
def search_with_context(query: str, company: str, position: str, k: int = 5) -> list[str]:
    context = f"公司：{company} | 岗位：{position} | 题目：{query}"
    vector = embedding.embed(context)
    candidates = qdrant.search(vector, limit=k * 3)
    ranked_indices = reranker.rerank(query, candidate_texts, top_k=k)
    return [candidates[idx].question_id for idx, _ in ranked_indices]
```

#### E3: +Graph（Graph 增强，可选）

```python
# 配置
config_e3 = {
    "embedding_model": "BGE-M3",
    "reranker": "BGE-Reranker-base",
    "recall_k": 15,
    "final_k": 5,
    "graph_enhanced": True,
}

# 检索流程（先图谱定位，再向量检索）
def search_with_graph(query: str, k: int = 5) -> list[str]:
    # Step 1: 图谱定位相关知识点
    keywords = extract_keywords(query)
    related_entities = neo4j.get_related_entities(keywords[0], limit=3)
    
    # Step 2: 构建增强查询
    enhanced_query = query + " " + " ".join(related_entities)
    
    # Step 3: 向量检索 + Reranker
    context = f"题目：{enhanced_query}"
    vector = embedding.embed(context)
    candidates = qdrant.search(vector, limit=k * 3)
    ranked_indices = reranker.rerank(query, candidate_texts, top_k=k)
    
    return [candidates[idx].question_id for idx, _ in ranked_indices]
```

### 4.3 实验变量控制

| 变量 | 控制方式 |
|------|---------|
| **测试数据集** | 固定同一份，不变化 |
| **向量模型** | 固定 BGE-M3 |
| **Reranker** | E0 无，E1/E2/E3 有 |
| **k 值** | E0 k=10，E1/E2/E3 recall_k=15, final_k=5 |
| **执行环境** | 本地执行，无网络依赖 |

---

## 五、评估代码实现

### 5.1 目录结构

```
backend/tests/eval/
│
├── rag_test_dataset.json      # 测试数据集
│
├── evaluator.py               # 评估器核心
│
├── experiments.py             # 实验配置与执行
│
├── analysis.py                # 结果分析与可视化
│
└── run_eval.py                # 执行入口
```

### 5.2 核心评估器

```python
"""RAG 检索评估器

实现 Recall@K, Precision@K, MRR, NDCG@K, Hit@K 等指标计算。
"""

import math
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class TestCase:
    """测试用例"""
    query: str
    relevant_ids: list[str]
    query_type: str = "general"
    company: str | None = None
    position: str | None = None


@dataclass
class EvalResult:
    """单条评估结果"""
    query: str
    query_type: str
    retrieved_ids: list[str]
    recall_at_5: float
    recall_at_10: float
    precision_at_5: float
    precision_at_10: float
    mrr: float
    ndcg_at_5: float
    hit_at_5: int
    hit_at_10: int


@dataclass
class AggregatedResult:
    """聚合评估结果"""
    experiment_name: str
    total_queries: int
    mean_recall_at_5: float
    mean_recall_at_10: float
    mean_precision_at_5: float
    mean_precision_at_10: float
    mean_mrr: float
    mean_ndcg_at_5: float
    mean_hit_at_5: float
    mean_hit_at_10: float
    by_query_type: dict = field(default_factory=dict)


class RAGEvaluator:
    """RAG 检索评估器"""
    
    def recall_at_k(
        self,
        relevant_ids: list[str],
        retrieved_ids: list[str],
        k: int,
    ) -> float:
        """Recall@K"""
        top_k = set(retrieved_ids[:k])
        rel_set = set(relevant_ids)
        if not rel_set:
            return 0.0
        return len(top_k & rel_set) / len(rel_set)
    
    def precision_at_k(
        self,
        relevant_ids: list[str],
        retrieved_ids: list[str],
        k: int,
    ) -> float:
        """Precision@K"""
        top_k = set(retrieved_ids[:k])
        rel_set = set(relevant_ids)
        return len(top_k & rel_set) / k
    
    def mrr(
        self,
        relevant_ids: list[str],
        retrieved_ids: list[str],
    ) -> float:
        """Mean Reciprocal Rank"""
        rel_set = set(relevant_ids)
        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in rel_set:
                return 1.0 / (i + 1)
        return 0.0
    
    def hit_at_k(
        self,
        relevant_ids: list[str],
        retrieved_ids: list[str],
        k: int,
    ) -> int:
        """Hit@K"""
        top_k = set(retrieved_ids[:k])
        rel_set = set(relevant_ids)
        return 1 if len(top_k & rel_set) > 0 else 0
    
    def ndcg_at_k(
        self,
        relevant_ids: list[str],
        retrieved_ids: list[str],
        k: int,
    ) -> float:
        """NDCG@K（简化版：相关=1，不相关=0）"""
        # 构建相关性评分列表
        rel_set = set(relevant_ids)
        relevance_scores = [
            1 if doc_id in rel_set else 0
            for doc_id in retrieved_ids[:k]
        ]
        
        # 计算 DCG
        dcg = 0.0
        for i, rel in enumerate(relevance_scores):
            dcg += (2 ** rel - 1) / math.log2(i + 2)
        
        # 计算 IDCG（理想情况：所有相关文档排在前面）
        ideal_relevance = [1] * min(len(rel_set), k) + [0] * (k - min(len(rel_set), k))
        idcg = 0.0
        for i, rel in enumerate(ideal_relevance[:k]):
            idcg += (2 ** rel - 1) / math.log2(i + 2)
        
        if idcg == 0:
            return 0.0
        return dcg / idcg
    
    def evaluate_single(
        self,
        test_case: TestCase,
        retrieve_func: Callable,
    ) -> EvalResult:
        """评估单条测试用例"""
        retrieved_ids = retrieve_func(
            test_case.query,
            company=test_case.company,
            position=test_case.position,
        )
        
        return EvalResult(
            query=test_case.query,
            query_type=test_case.query_type,
            retrieved_ids=retrieved_ids,
            recall_at_5=self.recall_at_k(test_case.relevant_ids, retrieved_ids, 5),
            recall_at_10=self.recall_at_k(test_case.relevant_ids, retrieved_ids, 10),
            precision_at_5=self.precision_at_k(test_case.relevant_ids, retrieved_ids, 5),
            precision_at_10=self.precision_at_k(test_case.relevant_ids, retrieved_ids, 10),
            mrr=self.mrr(test_case.relevant_ids, retrieved_ids),
            ndcg_at_5=self.ndcg_at_k(test_case.relevant_ids, retrieved_ids, 5),
            hit_at_5=self.hit_at_k(test_case.relevant_ids, retrieved_ids, 5),
            hit_at_10=self.hit_at_k(test_case.relevant_ids, retrieved_ids, 10),
        )
    
    def evaluate_batch(
        self,
        test_cases: list[TestCase],
        retrieve_func: Callable,
        experiment_name: str,
    ) -> AggregatedResult:
        """批量评估"""
        results = [
            self.evaluate_single(tc, retrieve_func)
            for tc in test_cases
        ]
        
        # 计算均值
        n = len(results)
        agg = AggregatedResult(
            experiment_name=experiment_name,
            total_queries=n,
            mean_recall_at_5=sum(r.recall_at_5 for r in results) / n,
            mean_recall_at_10=sum(r.recall_at_10 for r in results) / n,
            mean_precision_at_5=sum(r.precision_at_5 for r in results) / n,
            mean_precision_at_10=sum(r.precision_at_10 for r in results) / n,
            mean_mrr=sum(r.mrr for r in results) / n,
            mean_ndcg_at_5=sum(r.ndcg_at_5 for r in results) / n,
            mean_hit_at_5=sum(r.hit_at_5 for r in results) / n,
            mean_hit_at_10=sum(r.hit_at_10 for r in results) / n,
        )
        
        # 按查询类型分组
        by_type: dict[str, list[EvalResult]] = {}
        for r in results:
            if r.query_type not in by_type:
                by_type[r.query_type] = []
            by_type[r.query_type].append(r)
        
        for query_type, type_results in by_type.items():
            m = len(type_results)
            agg.by_query_type[query_type] = {
                "recall_at_5": sum(r.recall_at_5 for r in type_results) / m,
                "precision_at_5": sum(r.precision_at_5 for r in type_results) / m,
                "mrr": sum(r.mrr for r in type_results) / m,
            }
        
        return agg
```

### 5.3 实验执行器

```python
"""实验配置与执行"""

import json
from pathlib import Path

from app.infrastructure.persistence.qdrant import get_qdrant_manager
from app.infrastructure.adapters.embedding_adapter import get_embedding_adapter
from app.infrastructure.adapters.reranker_adapter import get_reranker_adapter


class ExperimentRunner:
    """实验执行器"""
    
    def __init__(self, test_dataset_path: str):
        self.test_cases = self._load_test_dataset(test_dataset_path)
        self.evaluator = RAGEvaluator()
        self.qdrant = get_qdrant_manager()
        self.embedding = get_embedding_adapter()
        self.reranker = get_reranker_adapter()
    
    def _load_test_dataset(self, path: str) -> list[TestCase]:
        """加载测试数据集"""
        with open(path, "r") as f:
            data = json.load(f)
        return [TestCase(**item) for item in data]
    
    def run_experiment_e0(self) -> AggregatedResult:
        """E0: Baseline（纯向量检索）"""
        def retrieve(query: str, company=None, position=None, k=10):
            context = f"题目：{query}"
            vector = self.embedding.embed(context)
            results = self.qdrant.search(vector, limit=k)
            return [r.question_id for r in results]
        
        return self.evaluator.evaluate_batch(
            self.test_cases,
            retrieve,
            "E0_Baseline",
        )
    
    def run_experiment_e1(self) -> AggregatedResult:
        """E1: +Reranker"""
        def retrieve(query: str, company=None, position=None, k=5):
            context = f"题目：{query}"
            vector = self.embedding.embed(context)
            candidates = self.qdrant.search(vector, limit=k * 3)
            
            candidate_texts = [c.question_text for c in candidates]
            ranked_indices = self.reranker.rerank(query, candidate_texts, top_k=k)
            
            return [candidates[idx].question_id for idx, _ in ranked_indices]
        
        return self.evaluator.evaluate_batch(
            self.test_cases,
            retrieve,
            "E1_Reranker",
        )
    
    def run_experiment_e2(self) -> AggregatedResult:
        """E2: +Context（上下文拼接优化）"""
        def retrieve(query: str, company=None, position=None, k=5):
            # 使用与入库一致的上下文格式
            context = f"公司：{company or '综合'} | 岗位：{position or '综合'} | 题目：{query}"
            vector = self.embedding.embed(context)
            candidates = self.qdrant.search(vector, limit=k * 3)
            
            candidate_texts = [c.question_text for c in candidates]
            ranked_indices = self.reranker.rerank(query, candidate_texts, top_k=k)
            
            return [candidates[idx].question_id for idx, _ in ranked_indices]
        
        return self.evaluator.evaluate_batch(
            self.test_cases,
            retrieve,
            "E2_Context",
        )
    
    def run_all_experiments(self) -> dict[str, AggregatedResult]:
        """运行所有实验"""
        results = {}
        results["E0"] = self.run_experiment_e0()
        results["E1"] = self.run_experiment_e1()
        results["E2"] = self.run_experiment_e2()
        return results
    
    def save_results(self, results: dict, output_path: str):
        """保存实验结果"""
        data = {}
        for exp_name, agg_result in results.items():
            data[exp_name] = {
                "experiment_name": agg_result.experiment_name,
                "total_queries": agg_result.total_queries,
                "metrics": {
                    "recall_at_5": agg_result.mean_recall_at_5,
                    "recall_at_10": agg_result.mean_recall_at_10,
                    "precision_at_5": agg_result.mean_precision_at_5,
                    "precision_at_10": agg_result.mean_precision_at_10,
                    "mrr": agg_result.mean_mrr,
                    "ndcg_at_5": agg_result.mean_ndcg_at_5,
                    "hit_at_5": agg_result.mean_hit_at_5,
                    "hit_at_10": agg_result.mean_hit_at_10,
                },
                "by_query_type": agg_result.by_query_type,
            }
        
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
```

### 5.4 执行入口

```python
"""RAG 检索评估执行入口

使用方式：
    cd backend
    uv run python tests/eval/run_eval.py
"""

from pathlib import Path

from experiments import ExperimentRunner
from analysis import ResultAnalyzer


def main():
    # 配置路径
    test_dataset_path = Path(__file__).parent / "rag_test_dataset.json"
    results_path = Path(__file__).parent / "eval_results.json"
    report_path = Path(__file__).parent / "eval_report.md"
    
    # 运行实验
    runner = ExperimentRunner(str(test_dataset_path))
    results = runner.run_all_experiments()
    
    # 保存结果
    runner.save_results(results, str(results_path))
    
    # 分析结果
    analyzer = ResultAnalyzer(results)
    analyzer.generate_report(str(report_path))
    
    # 打印摘要
    print("\n=== RAG 检索评估结果 ===\n")
    for exp_name, result in results.items():
        print(f"{exp_name}:")
        print(f"  Recall@5:  {result.mean_recall_at_5:.2%}")
        print(f"  Precision@5: {result.mean_precision_at_5:.2%}")
        print(f"  MRR:       {result.mean_mrr:.3f}")
        print()


if __name__ == "__main__":
    main()
```

---

## 六、评估工具与框架

### 6.1 开源框架对比

| 框架 | 特点 | 适用场景 | 推荐度 |
|------|------|---------|--------|
| **RAGAS** | 无参考评估，专注 RAG 端到端 | 快速评估 Context/Answer | ⭐⭐⭐ |
| **RAGChecker** | 细粒度诊断，分离检索/生成 | 深度诊断问题 | ⭐⭐⭐⭐ |
| **DeepEval** | CI/CD 集成，单元测试风格 | 自动化测试流水线 | ⭐⭐⭐ |
| **自定义脚本** | 完全可控，针对性强 | 本次评估 | ⭐⭐⭐⭐⭐ |

### 6.2 本次评估方案

**选择**：自定义脚本 + RAGChecker（可选补充）

**原因**：
- 自定义脚本：精确控制实验配置，与现有架构无缝集成
- RAGChecker：补充细粒度诊断（检索 vs 生成分离）

### 6.3 RAGAS 补充使用（可选）

如果需要评估 Context 相关指标，可以补充使用 RAGAS：

```python
# 安装：uv add ragas

from ragas import evaluate
from ragas.metrics import context_precision, context_recall

# 需要准备的数据格式
ragas_data = [
    {
        "question": "什么是 RAG？",
        "contexts": ["RAG 是检索增强生成..."],  # 检索返回的上下文
        "ground_truth": "检索增强生成技术",
    }
]

result = evaluate(ragas_data, metrics=[context_precision, context_recall])
```

---

## 七、实验流程

### 7.1 完整流程图

```
┌─────────────────────────────────────────────────────────────┐
│ Phase 1: 数据准备                                            │
│                                                              │
│ ├─ Step 1.1: 从 Qdrant 抽样题目（100 道）                      │
│ ├─ Step 1.2: 构造测试用例（精确匹配 + 语义相似）                │
│ ├─ Step 1.3: LLM 辅助生成相似查询                              │
│ ├─ Step 1.4: 人工验证（可选）                                  │
│ └─ Step 1.5: 保存测试数据集 JSON                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 2: 实验执行                                            │
│                                                              │
│ ├─ Step 2.1: 运行 E0（Baseline）                              │
│ ├─ Step 2.2: 运行 E1（+Reranker）                             │
│ ├─ Step 2.3: 运行 E2（+Context）                              │
│ ├─ Step 2.4: 运行 E3（+Graph，可选）                           │
│ └─ Step 2.5: 保存结果 JSON                                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 3: 结果分析                                            │
│                                                              │
│ ├─ Step 3.1: 计算各实验指标对比                                │
│ ├─ Step 3.2: 按查询类型分析                                   │
│ ├─ Step 3.3: 找出低召回率查询                                  │
│ ├─ Step 3.4: 生成评估报告 Markdown                            │
│ └─ Step 3.5: 可视化（可选）                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 4: 优化迭代                                            │
│                                                              │
│ ├─ Step 4.1: 根据分析结果提出优化方案                          │
│ ├─ Step 4.2: 实施优化                                         │
│ ├─ Step 4.3: 重新运行评估                                     │
│ └─ Step 4.4: 验证优化效果                                     │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 时间估算

| 阶段 | 任务 | 预估时间 |
|------|------|---------|
| Phase 1 | 数据准备 | 2-3 小时 |
| Phase 2 | 实验执行 | 30-60 分钟 |
| Phase 3 | 结果分析 | 1-2 小时 |
| Phase 4 | 优化迭代 | 根据优化方案确定 |

---

## 八、结果分析框架

### 8.1 对比分析模板

```markdown
## 实验结果对比

| 指标 | E0 Baseline | E1 +Reranker | E2 +Context | E1 vs E0 增益 | E2 vs E1 增益 |
|------|-------------|--------------|-------------|---------------|---------------|
| Recall@5 | XX% | XX% | XX% | +XX% | +XX% |
| Precision@5 | XX% | XX% | XX% | +XX% | +XX% |
| MRR | 0.XX | 0.XX | 0.XX | +XX% | +XX% |
| NDCG@5 | 0.XX | 0.XX | 0.XX | +XX% | +XX% |
| Hit@5 | XX% | XX% | XX% | +XX% | +XX% |
```

### 8.2 按查询类型分析

```markdown
## 各查询类型表现

| 查询类型 | 数量 | E0 Recall@5 | E1 Recall@5 | E1 增益 |
|---------|------|-------------|-------------|---------|
| exact_match | 50 | XX% | XX% | +XX% |
| semantic_similar | 30 | XX% | XX% | +XX% |
| keyword | 20 | XX% | XX% | +XX% |
| concept | 15 | XX% | XX% | +XX% |
```

### 8.3 问题查询分析

```python
def find_low_recall_queries(
    results: list[EvalResult],
    threshold: float = 0.3,
) -> list[EvalResult]:
    """找出低召回率查询"""
    return [r for r in results if r.recall_at_5 < threshold]

def analyze_failure_patterns(
    low_recall: list[EvalResult],
    test_cases: list[TestCase],
) -> dict:
    """分析失败模式"""
    patterns = {
        "short_query": 0,      # 查询太短
        "ambiguous_query": 0,  # 查询模糊
        "rare_entity": 0,      # 稀有知识点
        "cross_domain": 0,     # 跨领域查询
    }
    
    for r in low_recall:
        tc = next(t for t in test_cases if t.query == r.query)
        
        if len(tc.query) < 10:
            patterns["short_query"] += 1
        # ... 其他模式分析
    
    return patterns
```

### 8.4 评估报告生成

```python
class ResultAnalyzer:
    """结果分析器"""
    
    def __init__(self, results: dict[str, AggregatedResult]):
        self.results = results
    
    def generate_report(self, output_path: str):
        """生成 Markdown 评估报告"""
        report = []
        
        # 1. 标题
        report.append("# RAG 检索评估报告\n")
        report.append(f"> 评估时间：{datetime.now().strftime('%Y-%m-%d')}\n")
        
        # 2. 数据集概览
        report.append("## 1. 测试数据集\n")
        report.append(f"- 测试用例数量：{self.results['E0'].total_queries}\n")
        
        # 3. 实验结果对比
        report.append("## 2. 实验结果对比\n")
        report.append(self._generate_comparison_table())
        
        # 4. 按查询类型分析
        report.append("## 3. 各查询类型表现\n")
        report.append(self._generate_query_type_table())
        
        # 5. 关键发现
        report.append("## 4. 关键发现\n")
        report.append(self._generate_key_findings())
        
        # 6. 优化建议
        report.append("## 5. 优化建议\n")
        report.append(self._generate_recommendations())
        
        # 写入文件
        with open(output_path, "w") as f:
            f.write("\n".join(report))
    
    def _generate_comparison_table(self) -> str:
        """生成对比表格"""
        lines = ["| 指标 | E0 | E1 | E2 | E1增益 | E2增益 |", "|------|----|----|----|----|----|"]
        
        metrics = [
            ("Recall@5", "mean_recall_at_5"),
            ("Precision@5", "mean_precision_at_5"),
            ("MRR", "mean_mrr"),
            ("NDCG@5", "mean_ndcg_at_5"),
        ]
        
        for name, key in metrics:
            e0 = self.results["E0"].__dict__[key]
            e1 = self.results["E1"].__dict__[key]
            e2 = self.results["E2"].__dict__[key]
            
            e1_gain = f"+{(e1 - e0) / e0 * 100:.1f}%" if e0 > 0 else "N/A"
            e2_gain = f"+{(e2 - e1) / e1 * 100:.1f}%" if e1 > 0 else "N/A"
            
            if "Recall" in name or "Precision" in name:
                lines.append(f"| {name} | {e0:.1%} | {e1:.1%} | {e2:.1%} | {e1_gain} | {e2_gain} |")
            else:
                lines.append(f"| {name} | {e0:.3f} | {e1:.3f} | {e2:.3f} | {e1_gain} | {e2_gain} |")
        
        return "\n".join(lines)
```

---

## 九、迭代优化路径

### 9.1 根据评估结果确定优化方向

| 问题模式 | 优化方向 | 预期效果 |
|---------|---------|---------|
| **语义相似查询召回低** | 优化 embedding 上下文拼接 | +5-10% Recall |
| **Reranker 增益不明显** | 换用更强的 Reranker 模型 | +5-8% Precision |
| **稀有知识点召回低** | 增加同义词扩展 | +3-5% Recall |
| **跨领域查询效果差** | 引入 Graph 增强 | +5-10% Recall |

### 9.2 具体优化措施

#### 优化 1：上下文拼接策略

```python
# 当前：简单拼接
context = f"公司：{company} | 岗位：{position} | 题目：{query}"

# 优化：加入考点信息
entities = extract_entities(query)
context = f"公司：{company} | 岗位：{position} | 考点：{entities} | 题目：{query}"
```

#### 优化 2：同义词扩展

```python
def expand_query_with_synonyms(query: str) -> str:
    """查询同义词扩展"""
    synonyms = {
        "RAG": ["检索增强生成", "Retrieval Augmented Generation"],
        "Agent": ["智能体", "AI Agent", "代理"],
    }
    
    for term, syns in synonyms.items():
        if term in query:
            query = query.replace(term, f"{term} ({', '.join(syns)})")
    
    return query
```

#### 优化 3：更强的 Reranker

```python
# 当前：BGE-Reranker-base
# 优化：BGE-Reranker-large 或 Cohere Reranker
reranker = RerankerAdapter(model_path="bge-reranker-large")
```

#### 优化 4：Graph 增强（实验性）

```python
def search_with_graph(query: str, k: int = 5) -> list[str]:
    """Graph 增强检索"""
    # 1. 图谱定位相关知识点
    keywords = extract_keywords(query)
    related_entities = neo4j.get_related_entities(keywords[0])
    
    # 2. 用知识点作为过滤条件
    filter_conditions = {"core_entities": related_entities}
    
    # 3. 向量检索 + Rerank
    candidates = qdrant.search(vector, filter=filter_conditions, limit=k * 3)
    ranked_indices = reranker.rerank(query, candidates, top_k=k)
    
    return ranked_results
```

### 9.3 A/B 测试验证优化

| 测试 | 基线 | 优化 | 验证指标 |
|------|------|------|---------|
| A/B-1 | E1 | E1 + 同义词扩展 | Recall@5 |
| A/B-2 | E1 | E1 + 更强 Reranker | Precision@5 |
| A/B-3 | E2 | E2 + Graph 增强 | Recall@5, NDCG@5 |

---

## 附录：测试数据模板

### A. 测试数据集 JSON 格式

```json
[
  {
    "query": "什么是 RAG？",
    "relevant_ids": ["q_001"],
    "query_type": "exact_match",
    "company": "字节跳动",
    "position": "Agent 开发"
  },
  {
    "query": "RAG 技术原理是什么",
    "relevant_ids": ["q_001"],
    "query_type": "semantic_similar",
    "company": null,
    "position": null
  },
  {
    "query": "字节跳动 RAG 面试题",
    "relevant_ids": ["q_001", "q_002", "q_005"],
    "query_type": "keyword",
    "company": "字节跳动",
    "position": null
  }
]
```

### B. 评估结果 JSON 格式

```json
{
  "E0": {
    "experiment_name": "E0_Baseline",
    "total_queries": 100,
    "metrics": {
      "recall_at_5": 0.58,
      "recall_at_10": 0.72,
      "precision_at_5": 0.45,
      "precision_at_10": 0.38,
      "mrr": 0.42,
      "ndcg_at_5": 0.52,
      "hit_at_5": 0.78,
      "hit_at_10": 0.89
    },
    "by_query_type": {
      "exact_match": {
        "recall_at_5": 0.85,
        "precision_at_5": 0.75,
        "mrr": 0.68
      },
      "semantic_similar": {
        "recall_at_5": 0.45,
        "precision_at_5": 0.35,
        "mrr": 0.32
      }
    }
  }
}
```

### C. 评估报告 Markdown 模板

```markdown
# RAG 检索评估报告

> 评估时间：2026-04-17
> 测试数据集：100 条测试用例

## 1. 测试数据集

- 测试用例数量：100
- 查询类型分布：
  - exact_match: 50
  - semantic_similar: 30
  - keyword: 20

## 2. 实验结果对比

| 指标 | E0 Baseline | E1 +Reranker | E2 +Context |
|------|-------------|--------------|-------------|
| Recall@5 | 58.0% | 71.5% | 75.2% |
| Precision@5 | 45.0% | 63.8% | 68.5% |
| MRR | 0.42 | 0.58 | 0.62 |
| NDCG@5 | 0.52 | 0.68 | 0.72 |

## 3. 关键发现

1. **Reranker 增益显著**：Recall@5 提升 13.5%，MRR 提升 38%
2. **上下文拼接优化有效**：E2 相比 E1 再提升 5%
3. **语义相似查询是短板**：exact_match 达 85%，semantic_similar 仅 45%

## 4. 优化建议

1. 针对语义相似查询，优化 embedding 模型或增加同义词扩展
2. 尝试更强的 Reranker 模型（bge-reranker-large）
3. 对稀有知识点增加 Graph 增强检索
```

---

## 实施计划

| 阶段 | 任务 | 预计完成时间 |
|------|------|-------------|
| **Week 1** | 构建测试数据集 + 实现评估脚本 | 2-3 天 |
| **Week 1** | 运行 E0、E1、E2 实验 | 1 天 |
| **Week 2** | 分析结果 + 生成报告 | 1-2 天 |
| **Week 2** | 根据结果实施优化 | 2-3 天 |
| **Week 3** | 验证优化效果 + 持续迭代 | 根据实际情况 |

---

**下一步**：
1. 创建 `backend/tests/eval/` 目录
2. 实现 `evaluator.py` 评估器
3. 构建测试数据集 `rag_test_dataset.json`
4. 运行实验并生成报告