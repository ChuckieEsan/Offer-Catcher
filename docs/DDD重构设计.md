# DDD 重构设计方案

> 本文档记录 Offer-Catcher 项目向领域驱动设计（DDD）方向重构的设计方案。
> 创建日期：2026-04-15
> 最后更新：2026-04-16（新增 Agent 编排与 Workflow 分层设计）

---

## 一、概述

### 1.1 重构目标

- 将混合的代码结构重构为清晰的分层架构
- 明确领域边界，建立聚合和领域事件机制
- 实现依赖倒置，让领域层独立于基础设施
- 提高代码的可测试性和可维护性

### 1.2 DDD 核心概念

| 概念 | 说明 |
|------|------|
| **领域（Domain）** | 业务知识的边界，包含相关的业务逻辑和规则 |
| **聚合（Aggregate）** | 一组相关对象的集合，作为数据修改的单元，具有事务一致性边界 |
| **聚合根（Aggregate Root）** | 聚合的入口点，外部只能通过聚合根访问聚合内部对象 |
| **领域事件（Domain Event）** | 领域内发生的事情，用于跨聚合通信和最终一致性 |
| **仓库（Repository）** | 聚合的持久化抽象，领域层定义接口，基础设施层实现 |
| **领域服务（Domain Service）** | 不属于任何实体或值对象的业务逻辑 |

---

## 二、当前架构分析

### 2.1 当前目录结构

```
backend/app/
├── agents/          # Agent 层（LangChain/LangGraph 实现）
│   ├── graph/       # LangGraph 工作流定义
│   ├── prompts/     # Prompt 模板文件
│   └── skills/      # 技能模块
│   ├── chat_agent.py
│   ├── interview_agent.py
│   ├── vision_extractor.py
│   ├── answer_specialist.py
│   └── scorer.py
│
├── api/routes/      # API 路由层
│   ├── chat.py
│   ├── interview.py
│   ├── extract.py
│   ├── questions.py
│   └── ...
│
├── models/          # 数据模型层（混合多种类型的模型）
│   ├── question.py      # 题库领域 + Qdrant Payload + MQ 消息
│   ├── interview_session.py  # 面试会话
│   ├── chat_session.py       # 对话会话
│   ├── extract.py           # 提取任务 DTO
│   ├── agent.py             # Agent 输出模型
│
├── db/              # 数据库客户端层
│   ├── qdrant_client.py
│   ├── postgres_client.py
│   ├── redis_client.py
│   ├── graph_client.py
│   └── checkpointer.py
│
├── tools/           # Agent 工具层
│   ├── search_question_tool.py
│   ├── embedding_tool.py
│   ├── web_search_tool.py
│   └── ...
│
├── pipelines/       # 业务流水线层
│   ├── ingestion.py
│   └── retrieval.py
│
├── services/        # 业务服务层
│   ├── cache_service.py
│   ├── clustering_service.py
│   └── xfyun_asr.py
│
├── mq/              # 消息队列层
│   ├── producer.py
│   ├── consumer.py
│   └── thread_pool_consumer.py
│
├── memory/          # 记忆系统
│   ├── agent/
│   ├── io.py
│   ├── injection.py
│   └── ...
│
├── utils/           # 工具类
│   ├── logger.py
│   ├── cache.py
│   ├── hasher.py
│   └── ...
│
├── config/          # 配置
│   └── settings.py
│
└── workers/         # 后台 Worker（backend/workers/）
    ├── answer_worker.py
    ├── extract_worker.py
    ├── clustering_worker.py
    └── reembed_worker.py
```

### 2.2 当前架构问题分析

#### 问题一：领域模型与基础设施模型混合

`models/question.py` 中混合了：
- 领域模型：`QuestionItem`, `QuestionType`, `MasteryLevel`
- 基础设施模型：`QdrantQuestionPayload`, `MQTaskMessage`
- 查询/响应 DTO：`SearchFilter`, `SearchResult`

**问题**：领域概念被存储细节污染，如 `QdrantQuestionPayload` 包含了 `created_at`、`cluster_ids` 等存储相关字段。

#### 问题二：业务逻辑分散

业务逻辑散落在多个层次：
- `pipelines/ingestion.py` — 入库流程编排
- `agents/vision_extractor.py` — 提取逻辑
- `agents/answer_specialist.py` — 答案生成逻辑
- `workers/answer_worker.py` — Worker 处理逻辑
- `tools/search_question_tool.py` — 检索逻辑

**问题**：同样的业务规则（如"分类熔断机制"、"幂等性检查"）在不同地方重复实现。

#### 问题三：缺少聚合根

目前的模型都是扁平的数据结构，没有聚合的概念：
- `QuestionItem` 本身不是聚合根（它需要依附于公司、岗位的上下文）
- `InterviewSession` 虽然包含 `InterviewQuestion` 列表，但没有明确的聚合边界管理

**问题**：缺乏事务一致性边界。

#### 问题四：基础设施层直接暴露给上层

API 路由直接调用基础设施层：

```python
# chat.py
pg = get_postgres_client()
pg.add_message(user_id, conversation_id, "user", request.message)

# ingestion.py
qdrant_manager = get_qdrant_manager()
qdrant_manager.upsert_questions(payloads, vectors)
```

**问题**：上层代码直接依赖具体的存储实现，违背了依赖倒置原则。

#### 问题五：单例模式滥用

几乎所有组件都使用 `@singleton` 装饰器：

```python
get_qdrant_manager()
get_postgres_client()
get_chat_agent()
get_ingestion_pipeline()
```

**问题**：单例模式使得依赖关系隐式化，不利于测试和模块替换。

---

## 三、领域划分方案

### 3.1 领域总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        核心领域                                  │
├─────────────────────────────────────────────────────────────────┤
│  1. 题库领域（Question Domain）                                 │
│     子模块：面经提取 → 答案生成 → 入库 → 聚类 → 图分析             │
│                                                                 │
│  2. 模拟面试领域（Mock Interview Domain）                       │
│     会话管理、出题、评分、报告生成                                 │
│                                                                 │
│  3. 智能对话领域（Chat Domain）                                  │
│     对话会话、上下文管理                                          │
├─────────────────────────────────────────────────────────────────┤
│                        通用领域                                  │
├─────────────────────────────────────────────────────────────────┤
│  4. 记忆领域（Memory Domain）                                    │
│     长期记忆存储、检索、注入（被面试和对话共享）                    │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 领域职责说明

| 领域 | 核心职责 | 输入 | 输出 |
|------|----------|------|------|
| **题库领域** | 管理面试题目库，包括提取、入库、答案生成、聚类分析 | 面经文本/图片 | Question、Cluster、Answer |
| **模拟面试领域** | 提供模拟面试体验，管理面试会话和评分 | 用户配置（公司、岗位、难度） | InterviewSession、InterviewReport |
| **智能对话领域** | AI 助手对话，回答用户关于面试的问题 | 用户消息 | Conversation、Message |
| **记忆领域** | 管理用户长期记忆，为其他领域提供上下文 | 会话结束事件 | Memory |

### 3.3 领域依赖关系

```
┌──────────────────┐
│  模拟面试领域    │ ──────┐
└──────────────────┘       │
                           │  共享
┌──────────────────┐       ▼
│  智能对话领域    │ ───→ ┌──────────────────┐
└──────────────────┘      │    记忆领域      │
                          └──────────────────┘
┌──────────────────┐
│    题库领域      │ ───→ 被面试和对话引用（题目来源）
└──────────────────┘
```

---

## 四、聚合设计

### 4.1 题库领域聚合

#### 聚合一：Question（题目聚合）

```
┌─────────────────────────────────────────────────────────────┐
│  Question 聚合                                               │
│                                                             │
│  Question (聚合根)                                           │
│    - question_id: str (MD5)                                 │
│    - question_text: str                                     │
│    - question_type: QuestionType                            │
│    - mastery_level: MasteryLevel                            │
│    - company: str                                           │
│    - position: str                                          │
│    - core_entities: list[str]                               │
│    - answer: str | None        ← 单一版本答案               │
│    - cluster_ids: list[str]    ← 引用 Cluster               │
│    - metadata: dict                                         │
│                                                             │
│  聚合内规则：                                                │
│    - 所有字段修改必须通过 Question 方法                       │
│    - question_id 创建后不可变                                │
│    - 答案生成/更新是聚合内部操作                              │
└─────────────────────────────────────────────────────────────┘
```

#### 聚合二：Cluster（考点簇聚合）

```
┌─────────────────────────────────────────────────────────────┐
│  Cluster 聚合                                                │
│                                                             │
│  Cluster (聚合根)                                            │
│    - cluster_id: str                                        │
│    - cluster_name: str                                      │
│    - summary: str                                           │
│    - knowledge_points: list[str]                            │
│    - question_ids: list[str]   ← 引用 Question              │
│                                                             │
│  聚合内规则：                                                │
│    - 聚类算法负责创建/更新                                    │
│    - question_ids 是引用列表，不持有 Question 实体           │
└─────────────────────────────────────────────────────────────┘
```

#### 聚合三：ExtractTask（面经提取任务聚合）

```
┌─────────────────────────────────────────────────────────────┐
│  ExtractTask 聚合                                            │
│                                                             │
│  ExtractTask (聚合根)                                        │
│    - task_id: str                                           │
│    - source_type: str                                       │
│    - source_content: str                                    │
│    - status: ExtractTaskStatus                              │
│    - extracted_interview: dict | None                       │
│    - created_at / updated_at                                │
│                                                             │
│  聚合内规则：                                                │
│    - 用户确认后才触发入库                                    │
│    - 完成后可归档，不影响 Question                           │
└─────────────────────────────────────────────────────────────┘
```

#### Question 与 Cluster 的跨聚合关系

```
Question 和 Cluster 是两个独立的聚合：
  - 通过 ID 互相引用，不能直接持有对方实体
  - 跨聚合的一致性通过领域事件保证

场景分析：

场景1：新增一道题目
  → 只需要创建 Question，不影响任何 Cluster
  → Question 聚合内的事务，独立完成

场景2：题目被删除
  → Question 被删除
  → 相关 Cluster 需要从 question_ids 列表中移除该 ID
  → 用领域事件：QuestionDeleted → Cluster 更新（异步）

场景3：聚类算法执行
  → 算法批量分析所有题目，生成/更新 Cluster
  → Cluster 被创建/更新
  → 相关 Question 需要更新 cluster_ids
  → 用领域事件：ClusterAssigned → Question 更新（异步）
```

#### 题库领域事件

| 事件名 | 触发时机 | 消费者 |
|--------|----------|--------|
| `ExtractConfirmed` | 用户确认提取结果入库 | IngestionService → 创建 Question |
| `QuestionCreated` | Question 入库成功 | AnswerWorker → 异步生成答案 |
| `QuestionDeleted` | Question 被删除 | ClusterEventHandler → 更新 Cluster |
| `ClusterAssigned` | 聚类完成，题目归属簇 | QuestionEventHandler → 更新 cluster_ids |
| `AnswerGenerated` | 答案生成完成 | QuestionEventHandler → 更新 answer |

---

### 4.2 模拟面试领域聚合

#### 聚合：InterviewSession（面试会话聚合）

```
┌─────────────────────────────────────────────────────────────┐
│  InterviewSession 聚合                                       │
│                                                             │
│  InterviewSession (聚合根)                                   │
│    - session_id: str                                        │
│    - user_id: str                                           │
│    - company: str                                           │
│    - position: str                                          │
│    - difficulty: str                                        │
│    - total_questions: int                                   │
│    - status: SessionStatus                                  │
│    - current_question_idx: int                              │
│                                                             │
│    - questions: list[InterviewQuestionItem]  ← 聚合内实体    │
│        - question_id: str (引用题库的 Question)             │
│        - question_text: str (快照，避免跨聚合查询)           │
│        - question_type: str                                 │
│        - user_answer: str | None                            │
│        - score: int | None                                  │
│        - feedback: str | None                               │
│        - follow_ups: list[str]                              │
│        - status: QuestionStatus                             │
│                                                             │
│    - statistics: SessionStatistics                          │
│        - correct_count                                      │
│        - total_score                                        │
│        - average_score                                      │
│                                                             │
│    - timestamps                                             │
│        - started_at, ended_at                               │
│                                                             │
│  聚合内规则：                                                │
│    - 所有题目状态变更通过 Session 方法                        │
│    - 题目快照：入题时复制 question_text，不依赖题库实时数据   │
└─────────────────────────────────────────────────────────────┘
```

#### InterviewReport 的定位

```
InterviewReport 不是聚合，而是面试结束后的生成结果：
  - 从 Session 聚合提取数据
  - 由 InterviewReportService 生成
  - 可独立存储用于历史查看
```

#### 题目快照机制

```
面试开始时，从题库检索题目 → 复制必要信息 → 创建 InterviewQuestionItem

此后 Session 与题库解耦：
  - 题库变更不影响进行中的面试
  - 面试是"历史时刻"，题目状态应冻结
```

#### 模拟面试领域事件

| 事件名 | 触发时机 | 消费者 |
|--------|----------|--------|
| `InterviewStarted` | 面试开始 | - |
| `InterviewEnded` | 面试结束 | MemoryAgent → 提取面试洞察 |

---

### 4.3 智能对话领域聚合

#### 聚合：Conversation（对话聚合）

```
┌─────────────────────────────────────────────────────────────┐
│  Conversation 聚合                                           │
│                                                             │
│  Conversation (聚合根)                                       │
│    - conversation_id: str                                   │
│    - user_id: str                                           │
│    - title: str                                             │
│    - status: ConversationStatus                             │
│                                                             │
│    - messages: list[Message]  ← 聚合内实体                   │
│        - message_id: str                                    │
│        - role: MessageRole                                  │
│        - content: str                                       │
│        - created_at: datetime                               │
│                                                             │
│  聚合内规则：                                                │
│    - 消息追加是聚合内操作                                    │
│    - 消息不可修改/删除（对话是历史记录）                      │
│    - title 可由 AI 自动生成                                  │
└─────────────────────────────────────────────────────────────┘
```

#### LangGraph Checkpointer 的处理

```
存在两种状态：

1. Conversation.messages（领域层）
   - 存储简单的文本消息
   - 用于展示和简单查询
   - 由 Conversation 聚合管理

2. AgentState（框架层）
   - LangGraph 的状态机状态
   - 包含 messages（LangChain Message 类型）
   - 用于 Agent 接续推理
   - 由 Checkpointer 自动管理

保留两种状态，职责分离：
  - Conversation.messages → 业务查询（前端展示）
  - Checkpointer.state → Agent 接续推理

同步机制：
  - 每次对话结束，将 Checkpointer 中的 messages 同步到 Conversation
```

#### 智能对话领域事件

| 事件名 | 触发时机 | 消费者 |
|--------|----------|--------|
| `ConversationEnded` | 对话结束 | MemoryAgent → 提取会话摘要 |

---

### 4.4 记忆领域聚合

#### 聚合：Memory（记忆聚合）

```
┌─────────────────────────────────────────────────────────────┐
│  Memory 聚合                                                 │
│                                                             │
│  Memory (聚合根)                                             │
│    - memory_id: str                                         │
│    - user_id: str                                           │
│    - memory_type: MemoryType                                │
│        - USER_PROFILE     用户画像                          │
│        - SESSION_SUMMARY  会话摘要                          │
│        - INTERVIEW_INSIGHT 面试洞察                         │
│    - content: str                                           │
│    - source: MemorySource                                   │
│        - conversation_id | session_id                       │
│    - metadata: dict                                         │
│    - created_at / updated_at                                │
│                                                             │
│  聚合内规则：                                                │
│    - 记忆创建由 MemoryAgent 或 Hook 触发                     │
│    - 记忆不可删除（长期保留）                                 │
│    - 记忆可以合并/更新                                       │
└─────────────────────────────────────────────────────────────┘
```

#### 记忆与其他领域的协作

```
┌──────────────────┐     ┌──────────────────┐
│  Conversation    │     │ InterviewSession │
│  聚合            │     │ 聚合             │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         │  领域事件               │  领域事件
         │  ConversationEnded     │  InterviewEnded
         │                        │
         ▼                        ▼
┌─────────────────────────────────────────────┐
│             MemoryAgent                      │
│  (监听事件 → 提取记忆 → 创建 Memory 聚合)     │
└─────────────────────────────────────────────┘
                     │
                     │ Memory 聚合存储
                     ▼
┌─────────────────────────────────────────────┐
│             MemoryStore                      │
│  (记忆检索 → 注入到对话上下文)                │
└─────────────────────────────────────────────┘
                     │
                     │ 记忆注入
                     ▼
┌──────────────────┐     ┌──────────────────┐
│  ChatAgent       │     │ InterviewAgent   │
│  (使用记忆)      │     │ (使用记忆)       │
└──────────────────┘     └──────────────────┘
```

---

### 4.5 聚合设计汇总

| 领域 | 聚合根 | 聚合内实体 | 跨聚合引用 |
|------|--------|-----------|-----------|
| **题库** | Question, Cluster, ExtractTask | - | Question ↔ Cluster (ID引用) |
| **模拟面试** | InterviewSession | InterviewQuestionItem | 引用 Question (ID+快照) |
| **智能对话** | Conversation | Message | 无 |
| **记忆** | Memory | 无 | 引用 Conversation/InterviewSession (source) |

---

## 五、分层架构设计

### 5.1 标准 DDD 四层架构

```
┌─────────────────────────────────────────────────────────────┐
│  用户界面层（User Interface Layer）                          │
│    - API Routes (FastAPI)                                   │
│    - DTOs (Request/Response Models)                         │
│    - 数据转换                                                │
├─────────────────────────────────────────────────────────────┤
│  应用层（Application Layer）                                 │
│    - Application Services (用例编排)                         │
│    - 领域事件发布/订阅                                       │
│    - 事务管理                                                │
├─────────────────────────────────────────────────────────────┤
│  领域层（Domain Layer）                                      │
│    - 聚合、实体、值对象                                       │
│    - 领域服务                                                │
│    - 领域事件定义                                            │
│    - 仓库接口（Repository Protocol）                         │
├─────────────────────────────────────────────────────────────┤
│  基础设施层（Infrastructure Layer）                          │
│    - 仓库实现（Repository Implementation）                   │
│    - 数据库客户端 (Qdrant/PostgreSQL/Redis)                  │
│    - MQ 生产者/消费者                                        │
│    - 外部服务适配器                                          │
│    - 通用基础设施工具                                        │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 特殊组件的定位

| 组件 | 当前位置 | DDD 定位 | 理由 |
|------|---------|---------|------|
| **Agents（执行器）** | `agents/*.py` | 应用层 | Agent 是 Workflow 的执行器，负责调用领域逻辑、管理聚合、发布事件 |
| **LangGraph Workflow** | `agents/graph/` | 领域层 `domain/*/workflow/` | Workflow 定义（State、Nodes、Edges、Graph）是 Agent 行为规则，属于领域逻辑 |
| **Tools** | `tools/` | 领域层 `domain/*/tools.py` | Tools 是领域能力的接口（题库检索、Web搜索等） |
| **Pipelines** | `pipelines/` | 应用层 | 流程编排是应用层职责 |
| **Workers** | `workers/` | 应用层 | 异步用例执行器 |
| **Memory Agent** | `memory/agent/` | 领域服务 | 记忆提取是领域逻辑 |
| **Prompts** | `agents/prompts/` | 领域层 `domain/*/prompts/` | 提示词是领域逻辑的一部分，与领域服务绑定 |
| **Utils** | `utils/` | 拆分处理 | 根据职责分散到不同层 |

### 5.3 Agent 与 Workflow 的分层设计

**关键区分：Workflow 定义 vs Workflow 执行**

```
┌─────────────────────────────────────────────────────────────┐
│  领域层（Domain Layer）                                      │
│                                                             │
│  domain/chat/workflow/                                      │
│    ├── state.py          # AgentState 定义                  │
│    ├── nodes.py          # 节点函数定义                      │
│    ├── edges.py          # 条件边定义                        │
│    ├── graph.py          # Graph 结构定义（build_chat_graph）│
│                                                             │
│  职责：定义 Agent 的行为规则（纯业务逻辑）                    │
│    - 如何响应用户                                           │
│    - 何时调用 Tool                                          │
│    - 如何处理 Tool 结果                                     │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  应用层（Application Layer）                                 │
│                                                             │
│  application/services/                                       │
│    └── chat_service.py   # ChatApplicationService           │
│                                                             │
│  职责：执行 Workflow，管理事务边界                           │
│    - 调用 workflow（编译 Graph 并执行）                      │
│    - 协调其他领域服务（记忆注入）                            │
│    - 管理 Conversation 聚合                                 │
│    - 发布领域事件                                           │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  基础设施层（Infrastructure Layer）                          │
│                                                             │
│  infrastructure/persistence/postgres/                        │
│    └── checkpointer.py   # LangGraph Checkpointer           │
│                                                             │
│  职责：提供 Workflow 执行所需的基础设施                      │
│    - Checkpointer 管理 AgentState 持久化                    │
│    - 注入到编译后的 Graph                                   │
└─────────────────────────────────────────────────────────────┘
```

**为什么 Agent（执行器）在应用层？**

| Agent 的职责 | DDD 定位 | 原因 |
|-------------|---------|------|
| 调用 Workflow 执行 | 应用层 | Workflow 执行需要协调 Checkpointer（基础设施） |
| 协调记忆注入 | 应用层 | 跨领域协作（记忆领域 + 对话领域） |
| 管理 Conversation 聚合 | 应用层 | 聚合管理、事务边界 |
| 发布领域事件 | 应用层 | 跨聚合通信 |
| 流式输出 | 应用层 | API 层的响应处理 |

**为什么 Workflow 定义在领域层？**

| Workflow 的职责 | DDD 定位 | 原因 |
|----------------|---------|------|
| AgentState 定义 | 领域层 | Agent 状态结构是领域概念 |
| Nodes 函数（agent_node, tools_node） | 领域层 | Agent 行为规则是业务逻辑 |
| Edges 条件（should_continue） | 领域层 | 状态转换规则是业务逻辑 |
| Graph 结构（节点、边的连接） | 领域层 | Workflow 拓扑是领域设计 |
| Tools 定义 | 领域层 | 题库检索、Web搜索是领域能力 |

### 5.3 依赖方向规则

```
依赖方向（单向，从外向内）：

┌─────────────────────────────────────────────────────────────┐
│  API Layer                                                   │
│    ↓ 依赖                                                    │
├─────────────────────────────────────────────────────────────┤
│  Application Layer                                           │
│    ↓ 依赖                                                    │
├─────────────────────────────────────────────────────────────┤
│  Domain Layer                                                │
│    ↓ 依赖（通过 Protocol）                                    │
├─────────────────────────────────────────────────────────────┤
│  Infrastructure Layer                                        │
│    ↑ 实现 Domain Protocol（依赖倒置）                         │
└─────────────────────────────────────────────────────────────┘

关键规则：
1. API 依赖 Application，不直接依赖 Domain
2. Application 依赖 Domain，不依赖 Infrastructure
3. Domain 不依赖任何外层，只定义 Protocol
4. Infrastructure 实现 Domain Protocol（无需显式继承）
```

---

## 六、目录结构规划

### 6.1 目录层级简化方案

采用**适度合并**方案，保留领域边界清晰，但减少层级深度：

```
domain/question/aggregates.py  → 包含 Question、Cluster、ExtractTask
domain/question/repositories.py → 包含所有仓库 Protocol
```

导入路径从 4 层简化为 3 层，同时保持职责清晰。

### 6.2 重构后的目录结构

```
backend/app/
│
├── api/                          # 用户界面层
│   └── routes/
│       ├── chat.py
│       ├── interview.py
│       ├── extract.py
│       ├── questions.py
│       └── ...
│   └── dto/
│       ├── chat_dto.py
│       ├── interview_dto.py
│       └── ...
│
├── application/                  # 应用层
│   ├── services/
│   │   ├── chat_service.py
│   │   ├── interview_service.py
│   │   ├── ingestion_service.py
│   │   └── retrieval_service.py
│   │
│   ├── workers/
│   │   ├── answer_worker.py
│   │   ├── clustering_worker.py
│   │   ├── extract_worker.py
│   │   └── reembed_worker.py
│   │
│   ├── events/
│   │   ├── publishers/
│   │   ├── handlers/
│   │   └── event_bus.py
│   │
│   └── startup/
│   │   └── warmup.py             # 启动预热
│   │
├── domain/                       # 领域层
│   │
│   ├── question/                 # 题库领域
│   │   ├── aggregates.py         # Question, Cluster, ExtractTask
│   │   ├── repositories.py       # Protocol: QuestionRepository, ClusterRepository, ExtractTaskRepository
│   │   ├── services.py           # ExtractorService, AnswerService, ClusteringService, GraphAnalysisService
│   │   ├── events.py             # QuestionCreated, ClusterAssigned, ExtractConfirmed, AnswerGenerated
│   │   ├── utils.py              # question_id 生成（领域逻辑）
│   │   ├── prompts/              # 题库领域的提示词
│   │   │   ├── extractor.md
│   │   │   ├── answer.md
│   │   │   └── clustering.md
│   │   │
│   ├── interview/                # 模拟面试领域
│   │   ├── workflow/             # Interview Workflow 定义（领域逻辑）
│   │   │   ├── state.py          # InterviewAgentState
│   │   │   ├── nodes.py          # ask_question_node, score_node, followup_node
│   │   │   ├── edges.py          # should_continue, should_followup
│   │   │   └── graph.py          # build_interview_graph()
│   │   ├── aggregates.py         # InterviewSession
│   │   ├── repositories.py       # Protocol: InterviewSessionRepository
│   │   ├── services.py           # ScorerService, QuestionSelectorService, ReportGeneratorService
│   │   ├── events.py             # InterviewStarted, InterviewEnded
│   │   ├── prompts/
│   │   │   ├── scorer.md
│   │   │   ├── interview.md
│   │   │   └── report.md
│   │   │
│   ├── chat/                     # 智能对话领域
│   │   ├── workflow/             # LangGraph Workflow 定义（领域逻辑）
│   │   │   ├── state.py          # ChatAgentState
│   │   │   ├── nodes.py          # agent_node, tools_node
│   │   │   ├── edges.py          # should_continue
│   │   │   └── graph.py          # build_chat_graph()
│   │   ├── aggregates.py         # Conversation, Message
│   │   ├── repositories.py       # Protocol: ConversationRepository
│   │   ├── services.py           # TitleGeneratorService
│   │   ├── tools.py              # search_question_tool, web_search_tool, query_graph_tool
│   │   ├── events.py             # ConversationEnded
│   │   ├── prompts/
│   │   │   ├── chat.md
│   │   │   ├── title.md
│   │   │   └── tools_guide.md
│   │   │
│   ├── memory/                   # 记忆领域
│   │   ├── workflow/             # Memory Workflow 定义（可选）
│   │   │   ├── state.py          # MemoryAgentState
│   │   │   ├── nodes.py          # extract_node, store_node
│   │   │   └── graph.py          # build_memory_graph()
│   │   ├── aggregates.py         # Memory
│   │   ├── repositories.py       # Protocol: MemoryRepository
│   │   ├── services.py           # MemoryInjectionService
│   │   ├── events.py             # MemoryCreated
│   │   ├── prompts/
│   │   │   ├── memory_agent.md
│   │   │   ├── injection.md
│   │   │
│   └── shared/                   # 共享内核
│       ├── enums.py              # QuestionType, MasteryLevel, SessionStatus, MemoryType
│       ├── exceptions.py         # DomainException, QuestionNotFoundError, etc.
│       ├── prompts/              # 共享提示词
│       │   └── base.md           # 基础模板
│       │
├── infrastructure/               # 基础设施层
│   ├── persistence/
│   │   ├── qdrant/
│   │   │   ├── question_repository.py   # 实现 QuestionRepository Protocol
│   │   │   ├── cluster_repository.py    # 实现 ClusterRepository Protocol
│   │   │   ├── client.py                # Qdrant 客户端
│   │   │
│   │   ├── postgres/
│   │   │   ├── conversation_repository.py
│   │   │   ├── interview_session_repository.py
│   │   │   ├── extract_task_repository.py
│   │   │   ├── client.py
│   │   │   ├── checkpointer.py          # LangGraph Checkpointer
│   │   │
│   │   ├── redis/
│   │   │   ├── client.py
│   │   │   ├── cache_service.py
│   │   │
│   │   ├── neo4j/
│   │   │   ├── graph_client.py
│   │   │
│   │   ├── memory/
│   │   │   ├── memory_repository.py
│   │   │
│   ├── messaging/
│   │   └── rabbitmq/
│   │       ├── producer.py
│   │       ├── consumer.py
│   │       ├── thread_pool_consumer.py
│   │       ├── event_bus.py
│   │
│   ├── adapters/                 # 外部服务适配器
│   │   ├── embedding_adapter.py
│   │   ├── reranker_adapter.py
│   │   ├── web_search_adapter.py
│   │   ├── asr_adapter.py         # 讯飞 ASR
│   │   ├── ocr_adapter.py         # OCR 服务
│   │   ├── image_adapter.py       # 图片处理
│   │   ├── llm_adapter.py         # LLM 调用
│   │
│   ├── common/                   # 通用基础设施工具
│   │   ├── logger.py
│   │   ├── circuit_breaker.py
│   │   ├── retry.py
│   │   ├── telemetry.py
│   │   ├── cache.py              # 单例装饰器（谨慎使用）
│   │   ├── prompt_loader.py      # 提示词加载工具
│   │
│   └── config/
│       └── settings.py
│
└── main.py                       # 应用入口
```

---

## 七、Utils 和 Prompts 的定位详解

### 7.1 Utils 的拆分处理

当前 `utils/` 包含的内容需要根据职责重新分布：

| 原文件 | 当前职责 | 新位置 | 原因 |
|--------|---------|--------|------|
| `logger.py` | 日志记录 | `infrastructure/common/logger.py` | 基础设施通用工具 |
| `hasher.py` | question_id 生成 | `domain/question/utils.py` | **领域逻辑**（题库特有的 ID 生成规则） |
| `cache.py` | @singleton 装饰器 | `infrastructure/common/cache.py` | 基础设施工具（谨慎使用） |
| `circuit_breaker.py` | 熔断器模式 | `infrastructure/common/circuit_breaker.py` | 基础设施模式 |
| `retry.py` | 重试机制 | `infrastructure/common/retry.py` | 基础设施模式 |
| `telemetry.py` | 遗测追踪 | `infrastructure/common/telemetry.py` | 基础设施能力 |
| `prompt.py` | Prompt 加载 | `infrastructure/common/prompt_loader.py` | 基础设施工具 |
| `warmup.py` | 启动预热 | `application/startup/warmup.py` | 应用启动逻辑 |
| `image.py` | 图片处理 | `infrastructure/adapters/image_adapter.py` | 外部服务适配 |
| `ocr.py` | OCR 调用 | `infrastructure/adapters/ocr_adapter.py` | 外部服务适配 |

### 7.2 Hasher 的特殊处理

`hasher.py` 中的 `generate_question_id` 函数是**领域逻辑**，因为它定义了题目 ID 的生成规则：

```python
# domain/question/utils.py 或作为值对象

import hashlib

def generate_question_id(company: str, question_text: str) -> str:
    """生成题目唯一 ID（领域逻辑）
    
    规则：MD5(company + question_text)
    """
    content = f"{company}{question_text}"
    return hashlib.md5(content.encode()).hexdigest()
```

或者作为值对象的创建方法：

```python
# domain/question/aggregates.py

class QuestionId(str):
    """题目 ID 值对象"""
    
    @classmethod
    def create(cls, company: str, question_text: str) -> "QuestionId":
        content = f"{company}{question_text}"
        return cls(hashlib.md5(content.encode()).hexdigest())
```

### 7.3 Prompts 的领域绑定

提示词是领域逻辑的一部分，应与对应的领域服务绑定：

| 提示词 | 归属领域 | 对应服务 |
|--------|---------|---------|
| `extractor.md` | 题库领域 | ExtractorService |
| `answer.md` | 题库领域 | AnswerService |
| `clustering.md` | 题库领域 | ClusteringService |
| `scorer.md` | 模拟面试领域 | ScorerService |
| `interview.md` | 模拟面试领域 | InterviewAgentService |
| `report.md` | 模拟面试领域 | ReportGeneratorService |
| `chat.md` | 智能对话领域 | WorkflowService |
| `title.md` | 智能对话领域 | TitleGeneratorService |
| `memory_agent.md` | 记忆领域 | MemoryAgentService |
| `base.md` | 共享 | 通用基础模板 |

### 7.4 Prompt 加载工具

```python
# infrastructure/common/prompt_loader.py

from pathlib import Path

def load_prompt(domain: str, filename: str) -> str:
    """加载领域提示词
    
    Args:
        domain: 领域名称 (question, interview, chat, memory)
        filename: 提示词文件名
    
    Returns:
        提示词文本内容
    """
    base_path = Path(__file__).parent.parent.parent / "domain" / domain / "prompts"
    return (base_path / filename).read_text(encoding="utf-8")


# 使用示例 - domain/question/services.py
from infrastructure.common.prompt_loader import load_prompt

class ExtractorService:
    def _build_prompt(self, text: str) -> str:
        template = load_prompt("question", "extractor.md")
        return template.replace("{{text}}", text)
```

---

## 八、依赖倒置实现（Protocol vs ABC）

### 8.1 Python Protocol 简介

Python 的 `Protocol`（结构化子类型）相比 `ABC`（名义子类型）有以下优势：

| 特性 | ABC（抽象基类） | Protocol |
|------|----------------|----------|
| **继承要求** | 必须显式继承 | 不需要继承，鸭子类型 |
| **类型检查** | 需要注册或继承 | 自动识别匹配的类型 |
| **灵活性** | 较低（强耦合） | 较高（松耦合） |
| **运行时检查** | 支持 | 支持（需要 `@runtime_checkable`） |
| **适用场景** | 明确继承关系 | 接口定义、插件架构 |

### 8.2 仓库 Protocol 定义（领域层）

```python
# domain/question/repositories.py

from typing import Protocol
from domain.question.aggregates import Question, Cluster, ExtractTask

class QuestionRepository(Protocol):
    """题目仓库协议（结构化接口）
    
    任何实现了这些方法的类，都会被类型检查器识别为 QuestionRepository。
    不需要显式继承此 Protocol。
    """
    
    def find_by_id(self, question_id: str) -> Question | None: ...
    def save(self, question: Question) -> None: ...
    def delete(self, question_id: str) -> None: ...
    def search(
        self, 
        query_vector: list[float], 
        filter_conditions: dict, 
        limit: int
    ) -> list[Question]: ...
    def find_all(self) -> list[Question]: ...

class ClusterRepository(Protocol):
    """考点簇仓库协议"""
    
    def find_by_id(self, cluster_id: str) -> Cluster | None: ...
    def save(self, cluster: Cluster) -> None: ...
    def find_all(self) -> list[Cluster]: ...

class ExtractTaskRepository(Protocol):
    """提取任务仓库协议"""
    
    def find_by_id(self, task_id: str) -> ExtractTask | None: ...
    def save(self, task: ExtractTask) -> None: ...
    def find_by_status(self, status: str) -> list[ExtractTask]: ...
```

### 8.3 仓库实现（基础设施层）

```python
# infrastructure/persistence/qdrant/question_repository.py

# 注意：不需要显式继承 QuestionRepository Protocol
# 只要实现了 Protocol 定义的方法，就会被视为 QuestionRepository 类型

from domain.question.aggregates import Question
from infrastructure.persistence.qdrant.client import QdrantClient
from infrastructure.adapters.embedding_adapter import EmbeddingAdapter

class QdrantQuestionRepository:
    """题目仓库的 Qdrant 实现
    
    实现了 QuestionRepository Protocol 的所有方法，
    因此被类型检查器识别为 QuestionRepository 类型。
    """
    
    def __init__(self, client: QdrantClient, embedding: EmbeddingAdapter):
        self._client = client
        self._embedding = embedding
    
    def find_by_id(self, question_id: str) -> Question | None:
        payload = self._client.retrieve(question_id)
        if payload:
            return Question.from_payload(payload)
        return None
    
    def save(self, question: Question) -> None:
        vector = self._embedding.embed(question.to_context())
        self._client.upsert(question.to_payload(), vector)
    
    def delete(self, question_id: str) -> None:
        self._client.delete(question_id)
    
    def search(
        self, 
        query_vector: list[float], 
        filter_conditions: dict, 
        limit: int
    ) -> list[Question]:
        results = self._client.search(query_vector, filter_conditions, limit)
        return [Question.from_payload(r) for r in results]
    
    def find_all(self) -> list[Question]:
        payloads = self._client.scroll_all()
        return [Question.from_payload(p) for p in payloads]
```

### 8.4 Protocol 的优势

**1. 依赖倒置更纯粹**

```python
# application/services/ingestion_service.py

# 应用层依赖 Protocol（不依赖任何具体实现）
from domain.question.repositories import QuestionRepository  # Protocol

class IngestionApplicationService:
    def __init__(self, question_repo: QuestionRepository):  # Protocol 类型
        self._question_repo = question_repo
```

**2. 测试更方便**

```python
# tests/application/test_ingestion_service.py

# 测试时不需要继承 ABC，直接定义 Mock
# MockQuestionRepository 自动满足 QuestionRepository Protocol

class MockQuestionRepository:
    def __init__(self):
        self._questions = {}
    
    def find_by_id(self, question_id: str) -> Question | None:
        return self._questions.get(question_id)
    
    def save(self, question: Question) -> None:
        self._questions[question.question_id] = question
    
    def delete(self, question_id: str) -> None:
        self._questions.pop(question_id, None)
    
    def search(self, query_vector, filter_conditions, limit) -> list[Question]:
        return list(self._questions.values())[:limit]
    
    def find_all(self) -> list[Question]:
        return list(self._questions.values())

# Mock 可以直接使用，类型检查器会识别它为 QuestionRepository
service = IngestionApplicationService(question_repo=MockQuestionRepository())
```

**3. 多实现共存**

```python
# 可以有多个实现，不需要都继承同一个 ABC
class QdrantQuestionRepository: ...
class PostgresQuestionRepository: ...   # 未来支持 PostgreSQL pgvector
class InMemoryQuestionRepository: ...   # 测试用

# 所有实现都能被类型检查器识别为 QuestionRepository
```

---

## 九、应用服务示例

### 9.1 入库应用服务

```python
# application/services/ingestion_service.py

from domain.question.aggregates import ExtractTask, Question
from domain.question.repositories import QuestionRepository, ExtractTaskRepository
from domain.question.services import ExtractorService
from application.events.publishers import QuestionPublisher

class IngestionApplicationService:
    """入库应用服务（用例编排）"""
    
    def __init__(
        self,
        extract_task_repo: ExtractTaskRepository,
        question_repo: QuestionRepository,
        extractor_service: ExtractorService,
        event_publisher: QuestionPublisher,
    ):
        self._extract_task_repo = extract_task_repo
        self._question_repo = question_repo
        self._extractor_service = extractor_service
        self._event_publisher = event_publisher
    
    async def extract_and_confirm(self, task_id: str) -> list[str]:
        """提取面经并确认入库
        
        流程：
        1. 获取 ExtractTask 聚合
        2. 创建 Question 聚合
        3. 发布领域事件
        4. 更新 ExtractTask 状态
        """
        # 1. 获取 ExtractTask
        task = self._extract_task_repo.find_by_id(task_id)
        if not task or task.status != "completed":
            raise ValueError("Task not ready")
        
        # 2. 创建 Question 聚合
        question_ids = []
        for extracted_question in task.extracted_interview["questions"]:
            question = Question.create(
                question_text=extracted_question["question_text"],
                company=extracted_question["company"],
                position=extracted_question["position"],
                question_type=extracted_question["question_type"],
            )
            self._question_repo.save(question)
            question_ids.append(question.question_id)
        
        # 3. 发布领域事件（触发异步答案生成）
        self._event_publisher.publish_questions_created(question_ids)
        
        # 4. 更新 ExtractTask 状态
        task.confirm()
        self._extract_task_repo.save(task)
        
        return question_ids
```

### 9.2 API 层示例

```python
# api/routes/extract.py

from fastapi import APIRouter, Depends
from api.dto.extract_dto import ExtractRequest, ExtractResponse
from application.services.ingestion_service import IngestionApplicationService
from infrastructure.persistence.qdrant.question_repository import QdrantQuestionRepository
from infrastructure.persistence.postgres.extract_task_repository import PostgresExtractTaskRepository
from infrastructure.common.prompt_loader import load_prompt

router = APIRouter(prefix="/extract", tags=["extract"])

def get_ingestion_service() -> IngestionApplicationService:
    """依赖注入（实际项目中可使用 DI 框架）"""
    question_repo = QdrantQuestionRepository()
    extract_task_repo = PostgresExtractTaskRepository()
    extractor_service = ExtractorService()
    event_publisher = QuestionPublisher()
    
    return IngestionApplicationService(
        extract_task_repo=extract_task_repo,
        question_repo=question_repo,
        extractor_service=extractor_service,
        event_publisher=event_publisher,
    )

@router.post("/confirm", response_model=ExtractResponse)
async def confirm_extract(
    request: ExtractRequest,
    service: IngestionApplicationService = Depends(get_ingestion_service)
):
    """确认提取结果入库"""
    question_ids = await service.extract_and_confirm(request.task_id)
    return ExtractResponse(
        task_id=request.task_id,
        question_ids=question_ids,
        status="confirmed"
    )
```

### 9.3 对话应用服务（Agent 编排示例）

```python
# application/services/chat_service.py

from langchain_core.messages import HumanMessage
from domain.chat.workflow.graph import build_chat_graph
from domain.chat.repositories import ConversationRepository
from domain.memory.services import MemoryInjectionService
from application.events.publishers import ChatPublisher
from infrastructure.persistence.postgres.checkpointer import Checkpointer

class ChatApplicationService:
    """对话应用服务
    
    职责（应用层）：
    - 调用 Workflow 执行对话（Agent 编排）
    - 协调记忆注入（跨领域协作）
    - 管理 Conversation 聚合
    - 发布领域事件
    
    注意：Workflow 定义在 domain/chat/workflow/ 中，
    这里只负责编译和执行。
    """
    
    def __init__(
        self,
        conversation_repo: ConversationRepository,
        checkpointer: Checkpointer,
        memory_injection: MemoryInjectionService,
        event_publisher: ChatPublisher,
    ):
        self._conversation_repo = conversation_repo
        self._checkpointer = checkpointer
        self._memory_injection = memory_injection
        self._event_publisher = event_publisher
        # 编译 Graph（注入 Checkpointer 基础设施）
        self._graph = build_chat_graph().compile(checkpointer=checkpointer)
    
    async def astream(
        self,
        message: str,
        conversation_id: str,
        user_id: str,
    ) -> AsyncGenerator[dict, None]:
        """流式对话
        
        流程：
        1. 注入记忆上下文（跨领域协作）
        2. 执行 Workflow（调用领域逻辑）
        3. 流式输出
        """
        # 1. 注入记忆（应用层协调跨领域）
        # memory_context = await self._memory_injection.get_context(user_id)
        
        # 2. 执行 Workflow（调用领域层定义的 Graph）
        async for event in self._graph.astream(
            {"messages": [HumanMessage(content=message)]},
            config={"configurable": {"thread_id": conversation_id, "user_id": user_id}}
        ):
            yield self._format_event(event)
    
    async def end_conversation(self, conversation_id: str) -> None:
        """结束对话，发布事件"""
        self._event_publisher.publish_conversation_ended(conversation_id)
```

### 9.4 Workflow 定义示例（领域层）

```python
# domain/chat/workflow/state.py

from typing import Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages

class ChatAgentState(dict):
    """对话 Agent 状态定义（领域层）
    
    定义 Agent 的状态结构，属于领域逻辑。
    """
    
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str | None = None


# domain/chat/workflow/graph.py

from langgraph.graph import StateGraph
from domain.chat.workflow.state import ChatAgentState
from domain.chat.workflow.nodes import agent_node, tools_node
from domain.chat.workflow.edges import should_continue

def build_chat_graph() -> StateGraph:
    """构建对话工作流图（领域层）
    
    定义 Agent 的行为拓扑结构，属于领域逻辑。
    注意：这里只定义结构，不编译（编译在应用层进行）。
    """
    graph = StateGraph(ChatAgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue)
    graph.add_edge("tools", "agent")
    return graph


# domain/chat/workflow/nodes.py

from domain.chat.tools import search_questions, web_search, query_graph

def agent_node(state: ChatAgentState) -> ChatAgentState:
    """Agent 节点（领域层）
    
    决策并生成回复，属于领域逻辑。
    """
    # LLM 调用决策逻辑...
    pass

def tools_node(state: ChatAgentState) -> ChatAgentState:
    """Tools 节点（领域层）
    
    执行工具调用，属于领域逻辑。
    """
    # Tool 执行逻辑...
    pass


# domain/chat/workflow/edges.py

def should_continue(state: ChatAgentState) -> str:
    """条件边（领域层）
    
    决定是否继续执行或结束，属于领域逻辑。
    """
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "__end__"
```

---

## 十、领域事件机制

### 10.1 事件定义（领域层）

```python
# domain/question/events.py

from dataclasses import dataclass
from datetime import datetime

@dataclass
class QuestionCreated:
    """题目创建事件"""
    question_id: str
    question_type: str
    company: str
    position: str
    occurred_at: datetime

@dataclass
class QuestionDeleted:
    """题目删除事件"""
    question_id: str
    cluster_ids: list[str]  # 需要更新的 Cluster
    occurred_at: datetime

@dataclass
class AnswerGenerated:
    """答案生成完成事件"""
    question_id: str
    answer: str
    occurred_at: datetime

@dataclass
class ClusterAssigned:
    """聚类分配事件"""
    cluster_id: str
    question_ids: list[str]
    occurred_at: datetime
```

### 10.2 事件发布（应用层）

```python
# application/events/publishers/question_publisher.py

from datetime import datetime
from domain.question.events import QuestionCreated, QuestionDeleted
from application.events.event_bus import EventBus

class QuestionPublisher:
    """题目事件发布器"""
    
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
    
    def publish_questions_created(self, question_ids: list[str]) -> None:
        """发布题目创建事件"""
        for question_id in question_ids:
            event = QuestionCreated(
                question_id=question_id,
                occurred_at=datetime.now()
            )
            self._event_bus.publish(event)
    
    def publish_question_deleted(self, question_id: str, cluster_ids: list[str]) -> None:
        """发布题目删除事件"""
        event = QuestionDeleted(
            question_id=question_id,
            cluster_ids=cluster_ids,
            occurred_at=datetime.now()
        )
        self._event_bus.publish(event)
```

### 10.3 事件处理（应用层）

```python
# application/events/handlers/question_handler.py

from domain.question.events import AnswerGenerated, ClusterAssigned
from domain.question.repositories import QuestionRepository, ClusterRepository

class QuestionEventHandler:
    """题目事件处理器"""
    
    def __init__(
        self,
        question_repo: QuestionRepository,
        cluster_repo: ClusterRepository,
    ):
        self._question_repo = question_repo
        self._cluster_repo = cluster_repo
    
    def handle_answer_generated(self, event: AnswerGenerated) -> None:
        """处理答案生成完成事件"""
        question = self._question_repo.find_by_id(event.question_id)
        if question:
            question.update_answer(event.answer)
            self._question_repo.save(question)
    
    def handle_cluster_assigned(self, event: ClusterAssigned) -> None:
        """处理聚类分配事件"""
        for question_id in event.question_ids:
            question = self._question_repo.find_by_id(question_id)
            if question:
                question.add_cluster(event.cluster_id)
                self._question_repo.save(question)
```

### 10.4 事件总线实现（基础设施层）

```python
# infrastructure/messaging/rabbitmq/event_bus.py

import json
from application.events.event_bus import EventBusProtocol

class RabbitMQEventBus:
    """基于 RabbitMQ 的事件总线"""
    
    def __init__(self, producer):
        self._producer = producer
    
    def publish(self, event: object) -> None:
        """发布事件到 MQ"""
        event_type = event.__class__.__name__
        event_data = {
            "type": event_type,
            "data": event.__dict__,
        }
        self._producer.publish(
            routing_key=f"events.{event_type.lower()}",
            message=json.dumps(event_data)
        )
```

---

## 十一、聚合实现示例

### 11.1 Question 聚合

```python
# domain/question/aggregates.py

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from domain.shared.enums import QuestionType, MasteryLevel
from domain.question.utils import generate_question_id

class Question(BaseModel):
    """题目聚合根"""
    
    question_id: str = Field(description="题目唯一标识，MD5哈希")
    question_text: str = Field(description="题目文本内容")
    question_type: QuestionType = Field(description="题目类型")
    mastery_level: MasteryLevel = Field(default=MasteryLevel.LEVEL_0)
    company: str = Field(description="公司名称")
    position: str = Field(description="岗位名称")
    core_entities: list[str] = Field(default_factory=list)
    answer: Optional[str] = Field(default=None, description="标准答案")
    cluster_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    
    @classmethod
    def create(
        cls,
        question_text: str,
        company: str,
        position: str,
        question_type: QuestionType,
        core_entities: list[str] = None,
    ) -> "Question":
        """创建题目（工厂方法）"""
        question_id = generate_question_id(company, question_text)
        return cls(
            question_id=question_id,
            question_text=question_text,
            company=company,
            position=position,
            question_type=question_type,
            core_entities=core_entities or [],
        )
    
    def update_answer(self, answer: str) -> None:
        """更新答案"""
        self.answer = answer
    
    def add_cluster(self, cluster_id: str) -> None:
        """添加考点簇引用"""
        if cluster_id not in self.cluster_ids:
            self.cluster_ids.append(cluster_id)
    
    def remove_cluster(self, cluster_id: str) -> None:
        """移除考点簇引用"""
        self.cluster_ids = [c for c in self.cluster_ids if c != cluster_id]
    
    def update_mastery(self, level: MasteryLevel) -> None:
        """更新熟练度"""
        self.mastery_level = level
    
    def to_context(self) -> str:
        """生成用于 embedding 的上下文"""
        entities = ",".join(self.core_entities) if self.core_entities else "综合"
        return (
            f"公司：{self.company} | "
            f"岗位：{self.position} | "
            f"类型：{self.question_type.value} | "
            f"考点：{entities} | "
            f"题目：{self.question_text}"
        )
    
    def to_payload(self) -> dict:
        """转换为存储 payload"""
        return {
            "question_id": self.question_id,
            "question_text": self.question_text,
            "company": self.company,
            "position": self.position,
            "question_type": self.question_type.value,
            "mastery_level": self.mastery_level.value,
            "core_entities": self.core_entities,
            "answer": self.answer,
            "cluster_ids": self.cluster_ids,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_payload(cls, payload: dict) -> "Question":
        """从 payload 恢复"""
        return cls(
            question_id=payload["question_id"],
            question_text=payload["question_text"],
            company=payload["company"],
            position=payload["position"],
            question_type=QuestionType(payload["question_type"]),
            mastery_level=MasteryLevel(payload["mastery_level"]),
            core_entities=payload.get("core_entities", []),
            answer=payload.get("answer"),
            cluster_ids=payload.get("cluster_ids", []),
            metadata=payload.get("metadata", {}),
        )


class Cluster(BaseModel):
    """考点簇聚合根"""
    
    cluster_id: str = Field(description="考点簇唯一标识")
    cluster_name: str = Field(description="考点簇名称")
    summary: str = Field(description="一句话总结")
    knowledge_points: list[str] = Field(default_factory=list)
    question_ids: list[str] = Field(default_factory=list, description="引用的题目 ID")
    
    def add_question(self, question_id: str) -> None:
        """添加题目引用"""
        if question_id not in self.question_ids:
            self.question_ids.append(question_id)
    
    def remove_question(self, question_id: str) -> None:
        """移除题目引用"""
        self.question_ids = [q for q in self.question_ids if q != question_id]


class ExtractTask(BaseModel):
    """面经提取任务聚合根"""
    
    task_id: str = Field(description="任务唯一标识")
    source_type: str = Field(description="来源类型：image/text")
    source_content: str = Field(description="来源内容")
    status: str = Field(default="pending", description="任务状态")
    extracted_interview: Optional[dict] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    def start_processing(self) -> None:
        """开始处理"""
        self.status = "processing"
        self.updated_at = datetime.now()
    
    def complete(self, extracted_interview: dict) -> None:
        """处理完成"""
        self.status = "completed"
        self.extracted_interview = extracted_interview
        self.updated_at = datetime.now()
    
    def confirm(self) -> None:
        """用户确认入库"""
        self.status = "confirmed"
        self.updated_at = datetime.now()
    
    def cancel(self) -> None:
        """取消任务"""
        self.status = "cancelled"
        self.updated_at = datetime.now()
```

---

## 十二、重构实施建议

### 12.1 分阶段重构

建议采用渐进式重构，避免一次性大规模改动：

**第一阶段：建立领域层骨架**
- 创建 `domain/` 目录结构
- 定义聚合和仓库 Protocol
- 定义领域事件
- 不改变现有代码，只是新建结构

**第二阶段：迁移核心领域（题库）**
- 将 Question、Cluster、ExtractTask 迁移到领域层
- 实现 Qdrant 仓库
- 保持 API 兼容，逐步替换底层实现

**第三阶段：迁移其他领域**
- 模拟面试领域
- 智能对话领域
- 记忆领域

**第四阶段：建立应用层**
- 将 Pipelines 迁移到 Application Services
- 建立 Worker 和事件机制
- 建立事件总线

**第五阶段：清理旧代码**
- 删除 `models/` 中的混合模型
- 删除 `pipelines/` 目录
- 删除旧的 `agents/` 目录
- 更新 API 层依赖注入

### 12.2 保持向后兼容

重构过程中，建议：
- 保持现有 API 接口不变
- 通过适配器模式逐步替换
- 新代码使用新结构，旧代码逐步迁移
- 每个阶段完成后运行全部测试

### 12.3 测试策略

每个阶段完成后：
- 运行现有测试确保功能不变
- 为新的聚合编写单元测试
- 为仓库实现编写集成测试
- 使用 Mock Protocol 测试领域逻辑

---

## 十三、待讨论事项

以下事项需要在实施前进一步讨论：

1. **依赖注入框架**：是否引入 DI 框架（如 `dependency-injector`），还是使用 FastAPI 的 `Depends` 手动管理？

2. **LangGraph Checkpointer**：是否需要自定义 Checkpointer Repository，还是继续使用 LangGraph 内置机制？

3. **领域事件存储**：事件是否需要持久化？是否需要事件溯源？

4. **事务管理**：跨聚合操作是否需要 Saga 模式？当前设计使用领域事件实现最终一致性。

---

## 附录：术语对照表

| DDD 术语 | 当前代码对应 | 重构后位置 |
|----------|-------------|-----------|
| Entity | `QuestionItem`, `Message` | `domain/*/aggregates.py`, `domain/*/entities.py` |
| Aggregate Root | 无（扁平结构） | `domain/*/aggregates.py` |
| Value Object | 无（字符串枚举） | `domain/shared/enums.py`, 值对象嵌入聚合 |
| Domain Service | `agents/*.py`, `services/*.py` | `domain/*/services.py` |
| Repository | `db/*.py`（混合） | `domain/*/repositories.py`（Protocol）, `infrastructure/persistence/`（实现） |
| Application Service | `pipelines/*.py`, `agents/chat_agent.py` | `application/services/` |
| Agent（执行器） | `agents/chat_agent.py`, `agents/interview_agent.py` | `application/services/`（ChatApplicationService, InterviewApplicationService） |
| Workflow 定义 | `agents/graph/` | `domain/*/workflow/`（state.py, nodes.py, edges.py, graph.py） |
| Tools | `tools/` | `domain/*/tools.py` |
| DTO | `models/*.py`（混合） | `api/dto/` |
| Domain Event | 无 | `domain/*/events.py`, `application/events/` |
| Prompt | `agents/prompts/*.md` | `domain/*/prompts/` |
| Utils | `utils/*.py` | 拆分到 `domain/*/utils.py`, `infrastructure/common/`, `infrastructure/adapters/` |
| Checkpointer | `db/checkpointer.py` | `infrastructure/persistence/postgres/checkpointer.py` |