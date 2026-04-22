# memory_eval_harness_spec

> 版本：v1.0  
> 语言：中文  
> 目标：为 Agent 记忆模块提供一套完整、可执行、可扩展的评测 Harness 设计规范。  
> 适用对象：具备长期记忆、规则记忆、会话摘要检索、异步写入、并发控制等能力的 Agent 系统。

---

## 1. 文档目标

本文档定义一套面向 **Agent 记忆模块** 的评测 Harness 规范，核心目标不是评测“有没有记忆”，而是评测以下问题：

1. **该记的是否记住，不该记的是否跳过**
2. **记住的内容是否存到了正确的数据边界中**
3. **在需要的时候是否能召回正确的记忆**
4. **召回后的记忆是否真正改善了回答**
5. **在异步、并发、失败、容量压力下系统是否仍然稳健**

本文将评测对象统一抽象为四段链路：

- **Extraction**：从对话中提取记忆
- **Storage**：将记忆写入合适的存储位置
- **Retrieval**：在运行时召回相关记忆
- **Utilization**：将记忆真正用于回答与决策

此外，单独增加一类：

- **Systems**：对异步、并发、故障、幂等、容量等工程属性进行压力评测

---

## 2. 评测哲学

### 2.1 不只看检索，要看端到端收益

很多记忆系统会在检索指标上表现良好，但最终回答并未变好，原因通常有：

- 召回的记忆没有被模型真正使用
- 召回的记忆与当前任务弱相关
- 常驻概要误导模型，不再触发细粒度加载
- 检索与注入成功，但上下文太长被稀释
- 过时记忆或错误摘要污染回答

因此，本规范要求同时评测：

- **离线结构正确性**
- **在线推理时使用率**
- **系统收益是否超过引入成本**

### 2.2 按能力拆解，而不是按模块名拆解

一个“记忆模块”往往包含多个不同能力：

| 能力 | 问题 | 典型失败模式 |
|---|---|---|
| 提取 | 该不该记？记什么？ | 把临时约束记成长时偏好 |
| 存储 | 应该写到哪里？ | 偏好、行为、历史摘要边界混乱 |
| 检索 | 能不能在对的时候取回来？ | 检索不到；取到不相关记忆 |
| 使用 | 取回后有没有让回答更好？ | 检索成功但回答无变化 |
| 工程稳健性 | 会不会冲突、重复、覆盖？ | 并发覆盖、重复写入、上下文爆炸 |

因此，本 Harness 不是单一跑分器，而是由多类子 Harness 共同组成。

---

## 3. 评测对象抽象

为了让 Harness 适配不同实现，定义统一的逻辑接口层。

### 3.1 评测对象最小接口

被测系统至少应能通过适配器暴露以下能力：

```python
class MemorySystemAdapter:
    def run_extraction(self, history):
        ...

    def run_retrieval(self, history, current_query):
        ...

    def run_chat(self, history, current_query, memory_mode="enabled"):
        ...

    def inject_fault(self, fault_type, config):
        ...

    def reset_state(self):
        ...

    def export_trace(self):
        ...
```

### 3.2 需要保留的 Trace

每次评测都必须完整记录以下信息，供调试与归因：

- 输入 history
- 当前 query
- 提取出的结构化记忆
- 写入目标（preferences / behaviors / summaries / memory index）
- 实际调用的工具列表
- 检索查询文本
- 检索结果 top-k
- 注入前后的上下文长度
- 最终回答
- 异常与重试事件
- 并发与锁事件
- 最终 judge 结果

没有 trace 的评测是低价值的，因为只能看到“分低”，看不到“为什么低”。

---

## 4. 记忆能力分层模型

本规范建议将记忆分为三层，便于构造 gold 和设计指标。

### 4.1 Rule Memory（规则型记忆）

用于稳定影响 Agent 行为的长期信息，例如：

- 用户偏好语言
- 回答风格偏好
- 主题特定偏好
- 常见行为模式

示例：

- “以后都用中文回答我”
- “讲 RAG 时优先给代码示例”
- “用户问 what 后常追问 why/how”

### 4.2 Episodic Memory（情节型记忆）

用于记录历史会话中发生过的、未来可能需要引用的事件。

示例：

- “上次讨论过召回阈值 0.7–0.85”
- “之前做过一次字节跳动面试模拟，得分 65”
- “上周调试过 LangGraph checkpoint 问题”

### 4.3 Working Memory / Temporary Constraint（临时约束）

用于当前轮次或当前任务，不应默认写入长期记忆。

示例：

- “这次先别展开讲”
- “先给我要点，后面再细讲”
- “这道题只要结论，不要代码”

### 4.4 边界判断原则

评测 gold 应明确区分：

| 内容类型 | 是否应写长期记忆 | 存储建议 |
|---|---|---|
| 稳定偏好 | 是 | preferences |
| 稳定行为模式 | 是 | behaviors |
| 可回溯历史事件 | 是 | session summaries |
| 一次性约束 | 否 | 当前上下文 |
| 短期情绪表达 | 通常否 | 跳过 |
| 高风险隐私且无任务价值 | 通常否 | 跳过或脱敏 |

---

## 5. Harness 总体架构

### 5.1 子 Harness 划分

完整评测体系由以下 4 个子 Harness 组成：

1. **Extraction Harness**
2. **Retrieval Harness**
3. **Utilization Harness**
4. **Systems Harness**

### 5.2 执行顺序建议

推荐执行顺序：

1. 先做 Extraction，确认“记什么”大致正确
2. 再做 Retrieval，确认“能不能拿回来”
3. 再做 Utilization，确认“拿回来以后有没有帮助”
4. 最后做 Systems，确认“上线后会不会坏”

原因：

- 如果 Extraction 不准，后续 Retrieval 再好也没有意义
- 如果 Retrieval 不准，Utilization 低不一定是模型问题
- 如果离线链路都好，线上问题往往来自 Systems

---

## 6. Extraction Harness 规范

### 6.1 目标

评测系统是否能够从对话中提取出：

- 值得长期记忆的偏好
- 值得长期记忆的行为模式
- 值得摘要存储的历史事件
- 不应进入长期记忆的临时信息

### 6.2 输入格式

```json
{
  "case_id": "extract_001",
  "history": [
    {"role": "user", "content": "我希望以后都用中文回答。"},
    {"role": "assistant", "content": "好的。"}
  ]
}
```

### 6.3 Gold 输出格式

```json
{
  "case_id": "extract_001",
  "gold": {
    "should_skip": false,
    "should_write_summary": false,
    "preference_updates": [
      {
        "field": "language",
        "value": "中文",
        "strength": "high"
      }
    ],
    "behavior_updates": [],
    "summary_facts": []
  }
}
```

### 6.4 必测样例类型

#### A. 显式长期偏好

例如：

- “以后都用中文回答我”
- “我喜欢先讲 why 再讲 how”
- “RAG 问题要尽量给代码”

#### B. 弱显式偏好

例如：

- “这类问题你最好多给些例子”
- “我一般更在意工程实现”

#### C. 临时约束

例如：

- “这次先简短一点”
- “这一题不要代码”

#### D. 行为模式归纳

要求跨多轮观察才能写入，例如：

- 连续多次追问边界情况
- 总在问完 what 后追问 why/how
- 反复要求表格对比

#### E. 历史会话摘要

例如：

- 讨论过某个架构设计
- 做过某次复盘
- 解决过具体故障

#### F. 应跳过信息

例如：

- 闲聊噪声
- 无关情绪表达
- 当前轮偶然措辞

### 6.5 指标

#### 6.5.1 基础指标

- `memory_write_precision`
- `memory_write_recall`
- `preference_update_precision`
- `preference_update_recall`
- `behavior_update_precision`
- `behavior_update_recall`
- `summary_write_precision`
- `summary_write_recall`

#### 6.5.2 风险指标

- `over_memory_rate`：不该记却写入长期记忆的比例
- `under_memory_rate`：应记却未写的比例
- `boundary_error_rate`：写入位置错误的比例

### 6.6 评分建议

对每个 case，输出如下结构：

```json
{
  "case_id": "extract_010",
  "pred": {...},
  "gold": {...},
  "score": {
    "write_decision": 1,
    "boundary": 0,
    "content_match": 0.5
  },
  "failure_tags": ["temporary_constraint_written_as_preference"]
}
```

---

## 7. Retrieval Harness 规范

Retrieval Harness 需要分成两类，因为规则型记忆与历史摘要记忆的访问路径不同。

### 7.1 Rule Retrieval

#### 7.1.1 目标

评测系统在看到当前 query 时，是否能够：

- 正确利用常驻的 MEMORY 概要
- 在概要不够时，触发更细粒度的 reference 加载
- 不在无必要时乱调用 reference

#### 7.1.2 输入格式

```json
{
  "case_id": "rule_ret_001",
  "memory_index": "用户偏好: RAG 话题偏好给代码示例",
  "references": {
    "preferences": "...完整偏好文档...",
    "behaviors": "...完整行为文档..."
  },
  "current_query": "讲一下 RAG 的召回阈值怎么调"
}
```

#### 7.1.3 Gold 标注

```json
{
  "should_use_memory": true,
  "should_load_reference": true,
  "target_references": ["preferences"],
  "must_recover_facts": [
    "RAG回答偏好代码示例",
    "涉及阈值时给具体数值范围"
  ]
}
```

#### 7.1.4 指标

- `reference_call_precision`
- `reference_call_recall`
- `unnecessary_reference_call_rate`
- `missed_reference_call_rate`
- `recovered_rule_fact_recall`

### 7.2 Episodic Retrieval

#### 7.2.1 目标

评测系统能否从历史会话摘要中召回与当前 query 最相关的历史事件。

#### 7.2.2 输入格式

```json
{
  "case_id": "epi_ret_001",
  "session_summaries": [
    {
      "id": "s1",
      "conversation_id": "c1",
      "summary": "讨论了 RAG 召回阈值，推荐范围 0.7-0.85"
    },
    {
      "id": "s2",
      "conversation_id": "c2",
      "summary": "讨论了 LangGraph checkpoint 持久化"
    }
  ],
  "current_query": "RAG 阈值一般怎么设"
}
```

#### 7.2.3 Gold 标注

```json
{
  "relevant_summary_ids": ["s1"],
  "preferred_order": ["s1"],
  "must_recover_facts": ["0.7-0.85"]
}
```

#### 7.2.4 指标

- `top1_recall`
- `topk_recall`
- `mrr`
- `ndcg`
- `recovered_fact_recall`
- `stale_retrieval_rate`

### 7.3 特殊检索场景

Retrieval Harness 必须覆盖以下高风险场景：

#### A. 同一 conversation 多条 summary

若去重键使用 `conversation_id`，可能误伤同一会话里的不同记忆点。

#### B. 新旧内容冲突

例如：

- 旧偏好：喜欢详细
- 新偏好：最近先简短

检索时要优先最近且仍有效的内容。

#### C. 相似摘要干扰

多个摘要语义相近，但只有一个真正相关。

#### D. 容量裁剪后丢失关键记忆

当 memory context 接近上限时，新注入或旧裁剪是否导致相关记忆丢失。

---

## 8. Utilization Harness 规范

### 8.1 目标

评测“记忆被取回后，是否真正提升了最终回答”。

这是最关键的评测，因为它反映的是用户感知价值。

### 8.2 评测方法

对同一 case 至少运行三组实验：

1. **No Memory**：关闭记忆
2. **Memory Available But Disabled**：有记忆数据，但不允许使用
3. **Memory Enabled**：正常使用记忆

可选增加第 4 组：

4. **Oracle Memory**：直接注入 gold 记忆，测理论上限

### 8.3 输入格式

```json
{
  "case_id": "util_001",
  "history": [...],
  "current_query": "RAG 的召回阈值怎么调？",
  "memory_artifacts": {
    "memory_index": "...",
    "references": {...},
    "session_summaries": [...]
  },
  "gold_output_constraints": {
    "must_include": [
      "具体数值范围",
      "tradeoff 解释",
      "代码示例"
    ],
    "must_not_include": [
      "无关历史",
      "明显过时信息"
    ]
  }
}
```

### 8.4 评分维度

建议让 judge 对以下维度分别打分（1–5 分）：

- `task_correctness`
- `memory_usefulness`
- `personalization_fit`
- `historical_consistency`
- `irrelevant_memory_leakage`

### 8.5 胜率指标

- `memory_enabled_win_rate_vs_no_memory`
- `memory_enabled_win_rate_vs_available_but_disabled`
- `oracle_gap`

其中：

- 若 `enabled` 相比 `no_memory` 提升明显，说明系统有效
- 若 `oracle` 提升大、`enabled` 提升小，说明问题多半在检索或调用路径
- 若 `oracle` 也几乎不提升，说明任务本身对记忆不敏感，或使用提示设计不足

### 8.6 重要负向指标

- `memory_misuse_rate`：取回了记忆但用错的比例
- `correctness_regression_rate`：开启记忆后主任务正确性反而下降
- `hallucinated_memory_rate`：模型引用了并不存在的历史记忆

---

## 9. Systems Harness 规范

### 9.1 目标

评测记忆系统在真实工程环境中的稳健性，包括：

- 异步检索
- 后台提取
- 主 Agent 直接写记忆
- 锁与并发
- 故障重试
- 容量裁剪
- 幂等与一致性

### 9.2 必测系统场景

#### 9.2.1 并发更新冲突

场景：

- 后台 memory worker 正在基于旧游标处理
- 用户下一轮显式要求更新偏好
- 主 Agent 立即直写偏好
- 后台 worker 结束时不得覆盖主 Agent 的更新

指标：

- `lost_update_rate`
- `stale_overwrite_rate`
- `duplicate_write_rate`

#### 9.2.2 异步检索未完成

场景：

- 第 N 轮提问触发异步检索
- 第 N+1 轮用户立刻继续追问
- 检索尚未完成

指标：

- `next_turn_degradation`
- `recovery_turn_count`
- `incomplete_memory_use_rate`

#### 9.2.3 Embedding 失败

场景：

- summary 已生成
- embedding 服务失败
- 系统写入 NULL 或跳过 embedding

指标：

- `summary_write_success_after_embedding_failure`
- `retrieval_quality_drop`

#### 9.2.4 DB 写入失败

场景：

- summary 生成成功
- 数据库写失败
- 重试后仍失败

指标：

- `main_path_impact`
- `silent_data_loss_rate`
- `partial_write_inconsistency_rate`

#### 9.2.5 锁获取失败

场景：

- 更新 preferences / behaviors 的锁获取失败
- 系统进入重试或放弃

指标：

- `write_drop_rate_under_lock_contention`
- `eventual_consistency_rate`

#### 9.2.6 幂等

场景：

- 同一批消息被重复送入 memory worker 两次

指标：

- `idempotent_write_rate`
- `duplicate_summary_rate`

#### 9.2.7 上下文容量压力

场景：

- memory context 持续增长接近上限
- 新检索结果到来
- 系统需要裁剪旧内容

指标：

- `overflow_rate`
- `relevant_memory_drop_rate`
- `post_prune_answer_quality`

### 9.3 故障注入接口建议

```python
adapter.inject_fault("embedding_timeout", {"prob": 1.0})
adapter.inject_fault("db_write_failure", {"prob": 0.5})
adapter.inject_fault("lock_contention", {"hold_seconds": 10})
adapter.inject_fault("retrieval_delay", {"delay_ms": 1200})
```

---

## 10. 数据集设计规范

### 10.1 数据集分层

建议分三层构造数据集：

#### Level 1：Synthetic Unit Cases

特点：

- 单点能力测试
- 低成本、高可控
- 适合覆盖边界条件

规模建议：100–300 条

适合：

- Extraction
- Rule Retrieval
- 单点故障注入

#### Level 2：Scripted Conversation Trajectories

特点：

- 多轮对话
- 能体现记忆形成、更新、召回、使用全过程

规模建议：30–100 条

适合：

- Episodic Retrieval
- Utilization
- 并发与异步场景

#### Level 3：Real Trace Replay

特点：

- 来自真实对话
- 需要脱敏与标注
- 最贴近线上

规模建议：30–50 条起步

适合：

- 端到端验收
- 发布前回归测试

### 10.2 数据集标签体系

每条 case 建议带标签，便于切分分析：

- `preference_explicit`
- `preference_implicit`
- `behavior_pattern`
- `temporary_constraint`
- `episodic_recall`
- `multi_summary_same_conversation`
- `conflict_preference`
- `async_retrieval`
- `main_agent_write`
- `lock_contention`
- `capacity_pruning`
- `failure_injection`

### 10.3 标注原则

标注时不要只写“好/不好”，而要写：

- 是否应该写长期记忆
- 应写到哪一类记忆
- 应召回哪些条目
- 回答中必须体现什么
- 回答中绝不能体现什么

---

## 11. Gold Schema 设计

为了兼容不同子 Harness，建议定义统一 schema。

### 11.1 通用 Case Schema

```json
{
  "case_id": "util_023",
  "history": [...],
  "current_query": "...",
  "memory_artifacts": {
    "memory_index": "...",
    "references": {
      "preferences": "...",
      "behaviors": "..."
    },
    "session_summaries": [...]
  },
  "gold_memory_events": [...],
  "gold_retrieval_targets": [...],
  "gold_output_constraints": {...},
  "tags": ["rag", "preference", "async"]
}
```

### 11.2 Gold Memory Event Schema

```json
{
  "event_type": "preference_update",
  "scope": "long_term",
  "strength": "high",
  "target_store": "preferences",
  "content": "回答RAG问题时优先给代码示例",
  "evidence_turns": [3, 4]
}
```

### 11.3 Gold Retrieval Target Schema

```json
{
  "memory_type": "session_summary",
  "target_ids": ["s_1002"],
  "must_recover_facts": [
    "推荐阈值范围0.7-0.85",
    "precision/recall tradeoff"
  ]
}
```

### 11.4 Gold Output Constraint Schema

```json
{
  "must_include": [
    "具体阈值范围",
    "代码示例"
  ],
  "should_include": [
    "对历史讨论的轻量引用"
  ],
  "must_not_include": [
    "无关历史记忆",
    "已失效的旧偏好"
  ]
}
```

---

## 12. Judge 设计

### 12.1 Judge 分层

建议组合三类 Judge：

1. **规则 Judge**：用于结构化字段严格比对
2. **LLM Judge**：用于语义近似判断和回答质量比较
3. **人工抽检 Judge**：用于高风险样本验真

### 12.2 规则 Judge 适用场景

适合：

- 是否写 summary
- 是否写 preferences
- 是否写 behaviors
- 是否调用了 reference
- 是否召回了目标 ID
- 是否违反 must_not_include

### 12.3 LLM Judge 适用场景

适合：

- 提取内容是否语义等价
- 回答是否真正利用了记忆
- 两份回答谁更好
- 是否发生“看似相关、实则误用”的问题

### 12.4 LLM Judge Prompt 建议

Judge 应严格输出结构化 JSON，例如：

```json
{
  "winner": "A",
  "scores": {
    "task_correctness": 4,
    "memory_usefulness": 5,
    "personalization_fit": 5,
    "irrelevant_memory_leakage": 1
  },
  "reason": "A 使用了用户偏好中的代码示例要求，并给出具体阈值范围。"
}
```

### 12.5 Judge 一致性建议

- 同一 case 至少跑 2 个 judge prompt 变体
- 抽样做人工复核
- 对分歧大的 case 单独归类分析

---

## 13. 指标总表

### 13.1 Extraction 指标

- `memory_write_precision`
- `memory_write_recall`
- `preference_update_precision`
- `preference_update_recall`
- `behavior_update_precision`
- `behavior_update_recall`
- `summary_write_precision`
- `summary_write_recall`
- `over_memory_rate`
- `boundary_error_rate`

### 13.2 Retrieval 指标

- `reference_call_precision`
- `reference_call_recall`
- `rule_fact_recall`
- `top1_recall`
- `topk_recall`
- `mrr`
- `ndcg`
- `stale_retrieval_rate`
- `relevant_memory_drop_rate`

### 13.3 Utilization 指标

- `memory_enabled_win_rate_vs_no_memory`
- `memory_enabled_win_rate_vs_disabled`
- `oracle_gap`
- `memory_helpfulness_score`
- `personalization_fit_score`
- `correctness_regression_rate`
- `memory_misuse_rate`
- `hallucinated_memory_rate`

### 13.4 Systems 指标

- `session_summary_write_success_rate`
- `retrieval_latency_p50`
- `retrieval_latency_p95`
- `main_path_latency_delta`
- `lost_update_rate`
- `stale_overwrite_rate`
- `duplicate_write_rate`
- `lock_contention_drop_rate`
- `idempotent_write_rate`
- `overflow_rate`
- `token_overhead_per_turn`

---

## 14. 实验设计建议

### 14.1 Ablation Study

建议至少比较以下版本：

- **V0**：无记忆
- **V1**：只有常驻概要
- **V2**：概要 + references
- **V3**：概要 + references + session retrieval
- **V4**：全量系统（含异步检索、后台提取、主 Agent 直写、并发控制）

目的：判断每一层设计是否真正带来增益。

### 14.2 Oracle Study

将 gold memory 直接注入模型，测理论上限。

判断方式：

- 若 Oracle 比实际系统好很多：问题多半在 retrieval / routing
- 若 Oracle 也不明显提升：问题多半在 prompt / 使用方式 / 任务本身

### 14.3 Noise Injection Study

向上下文注入：

- 无关记忆
- 过时记忆
- 冲突记忆

测试系统是否稳健。

### 14.4 Stress & Fault Study

以不同组合施压：

- 高频多轮输入
- 检索延迟
- embedding 超时
- DB 写失败
- 锁竞争
- 长上下文裁剪

---

## 15. 报告输出规范

### 15.1 单次运行结果

每次运行应输出：

```json
{
  "run_id": "2026-04-22-001",
  "suite": "utilization",
  "model": "gpt-x",
  "dataset_version": "v0.3",
  "metrics": {...},
  "failures": [...],
  "artifacts": {
    "traces": ".../traces.jsonl",
    "predictions": ".../preds.jsonl",
    "judgments": ".../judgments.jsonl"
  }
}
```

### 15.2 Dashboard 维度建议

至少支持以下切分：

- 按 Harness 类型
- 按标签
- 按模型版本
- 按 memory mode
- 按 fault type
- 按 query 长度
- 按历史长度
- 按是否显式偏好 / 隐式偏好

### 15.3 Failure Bucket 规范

建议自动生成 failure bucket，例如：

- `temporary_constraint_written_as_long_term`
- `missed_explicit_preference`
- `retrieved_irrelevant_history`
- `retrieved_but_unused`
- `same_conversation_dedup_hides_relevant_summary`
- `stale_preference_overrides_new_preference`
- `async_not_ready_on_next_turn`
- `main_agent_write_overwritten_by_background`

---

## 16. 参考目录结构

```text
memory-eval/
  datasets/
    extraction_cases.jsonl
    retrieval_cases.jsonl
    utilization_cases.jsonl
    systems_cases.jsonl
  adapters/
    memory_system_adapter.py
    extraction_adapter.py
    retrieval_adapter.py
    chat_adapter.py
  judges/
    rule_judge.py
    llm_judge.py
    judge_prompts/
      pairwise.md
      extraction_semantic.md
  runners/
    run_extraction.py
    run_retrieval.py
    run_utilization.py
    run_systems.py
  reports/
    aggregate_metrics.py
    failure_bucket.py
    render_dashboard.py
  artifacts/
    traces/
    preds/
    judgments/
```

---

## 17. 最小可用落地计划

### Phase 1：打地基

目标：先评测“记什么”。

产出：

- 50 条 Extraction cases
- 规则 Judge
- 基础 precision / recall / boundary 指标

### Phase 2：验证真实价值

目标：评测“记忆是否改善回答”。

产出：

- 30 条 Utilization cases
- no-memory / enabled / oracle 三组对照
- LLM pairwise judge

### Phase 3：评测工程稳健性

目标：覆盖并发、异步、失败、裁剪。

产出：

- 10–20 条 Systems cases
- fault injection 能力
- lost update / duplicate / latency / overflow 指标

### Phase 4：回归测试与发布守门

目标：用于版本迭代时回归。

产出：

- 固定 benchmark 集
- 每次改动后自动跑
- 指标回退即报警

---

## 18. 发布门槛建议

以下只是初始建议，可根据业务需求调整。

### 18.1 Extraction

- `memory_write_precision >= 0.90`
- `memory_write_recall >= 0.80`
- `boundary_error_rate <= 0.08`

### 18.2 Retrieval

- `topk_recall >= 0.85`
- `reference_call_precision >= 0.85`
- `stale_retrieval_rate <= 0.10`

### 18.3 Utilization

- `memory_enabled_win_rate_vs_no_memory >= 0.60`
- `correctness_regression_rate <= 0.05`
- `memory_misuse_rate <= 0.08`

### 18.4 Systems

- `session_summary_write_success_rate >= 0.95`
- `retrieval_latency_p95 < 500ms`
- `lost_update_rate = 0`
- `duplicate_write_rate <= 0.01`
- `overflow_rate` 需可观测且有裁剪 trace

---

## 19. 高风险点清单

以下是此类记忆系统最值得重点关注的风险点，建议在 Harness 中单独设标签与回归用例：

1. **临时约束误写为长期偏好**
2. **同一 conversation 多条摘要被错误去重**
3. **过时偏好覆盖新偏好**
4. **摘要压缩导致关键细节丢失**
5. **常驻概要过强，阻止按需深读**
6. **检索成功但回答未使用**
7. **主 Agent 直写与后台 Agent 异步更新发生覆盖**
8. **基于字符串标记的互斥协议不稳定**
9. **上下文裁剪策略只看顺序、不看相关性**
10. **系统降级后产生 silent corruption**

---

## 20. 推荐优先级

如果资源有限，建议按以下顺序投入：

### P0

- Extraction Harness
- Utilization Harness 的基础对照实验

### P1

- Episodic Retrieval Harness
- Systems 并发冲突测试

### P2

- Fault injection 全覆盖
- Oracle / Noise / Stress 实验
- Dashboard 与自动化回归

---

## 21. 结论

一个合理的记忆模块，不应只在“架构上好看”，而应通过 Harness 被证明：

- 它能正确地区分长期与短期信息
- 它能把不同类型的记忆放在正确边界中
- 它能在需要的时候检索到正确内容
- 它确实能提升回答质量，而不是只增加 token
- 它在异步与并发环境中仍然稳健，不会悄悄损坏状态

因此，建议把记忆评测视为一套 **多层、可归因、可回归** 的工程体系，而不是单个 benchmark 分数。

---

## 22. 附录 A：示例 Case

```json
{
  "case_id": "full_001",
  "history": [
    {"role": "user", "content": "我讲 RAG 的时候更喜欢你给代码示例。"},
    {"role": "assistant", "content": "好的。"},
    {"role": "user", "content": "另外，涉及阈值时最好给一个具体范围。"},
    {"role": "assistant", "content": "明白。"},
    {"role": "user", "content": "RAG 的召回阈值一般怎么设？"}
  ],
  "memory_artifacts": {
    "memory_index": "用户偏好：RAG 相关问题偏好代码示例与具体数值范围。",
    "references": {
      "preferences": "# 用户偏好详情\n- RAG 问题优先给代码示例\n- 涉及阈值时给具体数值范围",
      "behaviors": "# 用户行为模式详情\n- 偏好实践导向"
    },
    "session_summaries": [
      {
        "id": "s_1",
        "conversation_id": "c_1",
        "summary": "曾讨论 RAG 召回阈值，推荐范围 0.7-0.85。"
      }
    ]
  },
  "gold_memory_events": [
    {
      "event_type": "preference_update",
      "scope": "long_term",
      "strength": "high",
      "target_store": "preferences",
      "content": "RAG 问题优先给代码示例"
    },
    {
      "event_type": "preference_update",
      "scope": "long_term",
      "strength": "high",
      "target_store": "preferences",
      "content": "涉及阈值时给具体数值范围"
    }
  ],
  "gold_retrieval_targets": [
    {
      "memory_type": "reference",
      "target_ids": ["preferences"],
      "must_recover_facts": ["代码示例", "具体数值范围"]
    },
    {
      "memory_type": "session_summary",
      "target_ids": ["s_1"],
      "must_recover_facts": ["0.7-0.85"]
    }
  ],
  "gold_output_constraints": {
    "must_include": ["0.7-0.85", "代码示例"],
    "must_not_include": ["无关历史"]
  },
  "tags": ["rag", "preference_explicit", "episodic_recall", "utilization"]
}
```

---

## 23. 附录 B：推荐 Trace 字段

```json
{
  "case_id": "util_001",
  "tool_calls": [
    {"name": "load_memory_reference", "args": {"reference_name": "preferences"}},
    {"name": "search_session_history", "args": {"query": "RAG 阈值"}}
  ],
  "retrieval_query": "RAG 阈值一般怎么设",
  "retrieved_items": [
    {"id": "s_1", "score": 0.92},
    {"id": "s_3", "score": 0.61}
  ],
  "prompt_tokens_before_memory": 1280,
  "prompt_tokens_after_memory": 1670,
  "final_answer": "...",
  "judge_result": {
    "task_correctness": 5,
    "memory_usefulness": 5,
    "winner_vs_no_memory": "win"
  }
}
```

---

## 24. 附录 C：一句话原则清单

- 先测“该不该记”，再测“能不能取”，最后测“有没有用”。
- 没有 trace 的评测，基本不可归因。
- Retrieval 分高不代表用户体验好，Utilization 才是关键。
- Systems Harness 不是附属项，而是上线前的必选项。
- Oracle 实验能帮你快速定位问题是在检索链还是使用链。
- 评测中要明确区分长期偏好、历史事件、临时约束。
- 去重、裁剪、并发互斥，是最容易在真实系统中出问题的地方。

