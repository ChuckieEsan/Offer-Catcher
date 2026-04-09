# Offer-Catcher 系统架构文档

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端层 (Next.js 16)                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │  面经录入  │  │  题目管理  │  │  对话练习  │  │  数据统计  │  │  题目聚类  │     │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API 层 (FastAPI)                                │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ /extract/*  │ /questions/*  │ /chat/*  │ /stats/*  │ /search/*       │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        CacheService (Redis)                           │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│   PostgreSQL     │      │    RabbitMQ      │      │     Redis        │
│  - 会话持久化     │      │   - 任务队列      │      │   - 缓存层       │
│  - 面经解析任务   │      │   - 削峰填谷      │      │   - 5分钟 TTL    │
└──────────────────┘      └──────────────────┘      └──────────────────┘
          │                           │
          │                           │
          ▼                           ▼
┌──────────────────┐      ┌──────────────────────────────────────┐
│     Qdrant       │      │            Workers                    │
│  - 向量存储      │      │  ┌────────────────────────────────┐  │
│  - 混合检索      │      │  │ Extract Worker (面经解析)       │  │
│  - Payload 过滤  │      │  │ Answer Worker (答案生成)        │  │
└──────────────────┘      │  │ Clustering Worker (聚类)       │  │
                          │  └────────────────────────────────┘  │
                          └──────────────────────────────────────┘
```

---

## 核心模块

### 1. 面经录入系统

#### 1.1 异步任务模式

```
用户提交 → API 创建任务 → Worker 异步解析 → 用户查看/编辑 → 确认入库
    │            │              │               │            │
    └─ 立即返回   └─ PostgreSQL  └─ MQ 消费      └─ 更新任务  └─ Qdrant
       task_id
```

#### 1.2 任务状态机

```
pending → processing → completed → confirmed
                  ↘ failed
```

#### 1.3 数据存储

| 数据 | 存储位置 | 说明 |
|------|---------|------|
| 任务元数据 | PostgreSQL | task_id, status, result |
| 图片数据 | PostgreSQL (gzip) | Base64 压缩存储 |
| 解析结果 | PostgreSQL (JSONB) | 可编辑的 Interview 数据 |
| 最终题目 | Qdrant | 入库后的向量数据 |

### 2. 题目检索系统

#### 2.1 两阶段检索

```
Stage 1: 向量召回
  - 统一 Embedding 策略：公司+岗位+题目
  - 召回 k*3 条候选

Stage 2: Rerank 精排
  - CrossEncoder (bge-reranker-base)
  - 返回 top-k 结果
```

#### 2.2 服务端过滤

```python
# Qdrant 服务端过滤，避免内存溢出
filter_conditions = SearchFilter(
    company=company,
    cluster_ids=[cluster_id],
)
questions = qdrant.scroll_with_filter(filter_conditions)
count = qdrant.count_with_filter(filter_conditions)
```

### 3. 缓存系统

#### 3.1 一致性策略

- **TTL 兜底**: 所有缓存 5 分钟过期
- **主动失效**: 写操作后删除缓存
- **延迟双删**: 解决并发读写问题

#### 3.2 Key 设计

```
oc:stats:overview        # 总览统计
oc:stats:clusters        # 聚类统计
oc:questions:list:{hash} # 题目列表
oc:questions:item:{id}   # 单个题目
```

---

## API 设计

### 面经解析 API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/extract/submit` | POST | 提交解析任务 |
| `/extract/tasks` | GET | 获取任务列表 |
| `/extract/tasks/{id}` | GET | 获取任务详情 |
| `/extract/tasks/{id}` | PUT | 编辑解析结果 |
| `/extract/tasks/{id}/confirm` | POST | 确认入库 |
| `/extract/tasks/{id}` | DELETE | 删除任务 |

### 题目管理 API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/questions` | GET | 获取题目列表（服务端过滤） |
| `/questions/{id}` | GET | 获取单个题目 |
| `/questions/{id}` | PUT | 更新题目 |
| `/questions/{id}` | DELETE | 删除题目 |
| `/questions/{id}/regenerate` | POST | 重新生成答案 |

### 统计 API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/stats/overview` | GET | 总览统计 |
| `/stats/companies` | GET | 公司统计 |
| `/stats/clusters` | GET | 聚类统计 |

---

## 数据模型

### ExtractTask (面经解析任务)

```python
class ExtractTask(BaseModel):
    task_id: str                    # UUID
    user_id: str                    # 用户 ID
    source_type: str                # image / text
    source_content: Optional[str]   # 文本内容
    source_images_gz: Optional[str] # 图片 Base64 (gzip 压缩)
    status: str                     # pending/processing/completed/failed/confirmed
    error_message: Optional[str]    # 错误信息
    created_at: datetime
    updated_at: datetime
    result: Optional[ExtractedInterview]  # 解析结果
```

### QuestionItem (题目)

```python
class QuestionItem(BaseModel):
    question_id: str                # MD5(company + question_text)
    question_text: str              # 题目文本
    question_type: str              # knowledge/project/behavioral/scenario/algorithm
    company: str                    # 公司
    position: str                   # 岗位
    mastery_level: int              # 0/1/2
    core_entities: list[str]        # 知识点
    cluster_ids: list[str]          # 所属聚类
    question_answer: Optional[str]  # 答案
```

---

## Workers

### Extract Worker

```bash
# 启动命令
PYTHONPATH=. uv run python workers/extract_worker.py

# 职责
1. 轮询 PostgreSQL 获取 pending 任务
2. 调用 Vision Extractor 解析
3. 更新任务状态和结果
```

### Answer Worker

```bash
# 启动命令
PYTHONPATH=. uv run python workers/answer_worker.py

# 职责
1. 消费 RabbitMQ 消息
2. 调用 Web Search Agent 生成答案
3. 更新 Qdrant 中的题目答案
4. 失效 Redis 缓存
```

### Clustering Worker

```bash
# 启动命令
PYTHONPATH=. uv run python workers/clustering_worker.py --run-now

# 职责
1. 获取所有题目
2. KMeans 聚类
3. 更新 cluster_ids 字段
```

---

## 技术栈

| 层级 | 技术选型 |
|------|---------|
| 前端 | Next.js 16 + React 19 + Ant Design |
| 后端 | FastAPI + LangGraph + LangChain |
| 向量数据库 | Qdrant |
| 关系数据库 | PostgreSQL |
| 消息队列 | RabbitMQ |
| 缓存 | Redis |
| LLM | DeepSeek / DashScope |
| Embedding | BGE-M3 |
| Reranker | BGE-Reranker-Base |

---

## 目录结构

```
Offer-Catcher/
├── backend/
│   ├── app/
│   │   ├── agents/          # 智能体
│   │   ├── api/routes/      # API 路由
│   │   ├── db/              # 数据库客户端
│   │   ├── models/          # 数据模型
│   │   ├── pipelines/       # 业务流水线
│   │   ├── services/        # 业务服务
│   │   ├── tools/           # Agent 工具
│   │   └── utils/           # 工具函数
│   └── workers/             # 后台 Worker
├── frontend/
│   └── src/
│       ├── app/             # 页面
│       ├── components/      # 组件
│       ├── lib/             # API 客户端
│       └── types/           # 类型定义
└── docs/                    # 文档
```

---

## 运维命令

```bash
# 后端 API
cd backend && uv run python -m app.main

# Worker 进程
cd backend && PYTHONPATH=. uv run python workers/extract_worker.py
cd backend && PYTHONPATH=. uv run python workers/answer_worker.py

# 前端开发
cd frontend && npm run dev

# 运行测试
cd backend && uv run pytest tests/ -v
```