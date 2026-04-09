# Offer-Catcher: 面经智能体系统

**版本**: v2.1 (异步架构 + 性能优化)
**核心定位**: 基于 Multi-Agent 架构与混合 RAG 的面经收集、结构化图谱分析与智能对练系统。

---

## 产品背景与核心价值

### 痛点分析

当前求职者在复习"大模型/Agent开发"面经时面临三大痛点：
1. **数据非结构化与噪音大**: 小红书/牛客网面经多为长截图，包含大量寒暄废话，难以提取结构化考点。
2. **缺乏时效性与标准答案**: LLM 技术迭代极快（如 MCP、Agentic RAG 等），依靠死记硬背或大模型幻觉生成的答案往往是过时或错误的。
3. **缺乏宏观统计与个性化追踪**: 无法得知"字节最近最爱考什么"，也无法追踪自己对某道题的掌握程度。

### 核心价值与解决方案

- **多模态与分类熔断提取**: 支持图文混排输入，利用 Vision LLM 进行结构化提取，并对题目进行智能分类（knowledge/project/behavioral/scenario/algorithm），过滤无效生成。
- **异步面经解析**: 提交后立即返回任务 ID，Worker 后台解析，用户可随时查看进度和结果，支持编辑后入库。
- **两阶段检索架构**: 向量召回 + Rerank 精排，提升检索准确率。
- **消息队列与 Multi-Agent 异步答疑**: 引入 RabbitMQ 削峰填谷，由主 Agent 调度带联网搜索能力的子 Agent 异步生成最新标准答案。
- **混合存储架构**: Qdrant 向量库（支撑细粒度混合检索） + Neo4j 图数据库（支撑宏观考频统计与知识点关联分析）。
- **Redis 缓存层**: TTL + 主动失效 + 延迟双删，保证分钟级数据一致性。
- **前后端分离**: FastAPI 后端 + Next.js 前端，支持独立部署和扩展。

---

## 系统架构设计

系统采用 **"前后端分离、读写分离、主从智能体解耦、消息驱动"** 的架构。

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端层 (Next.js 16)                             │
│  - React 19 + Ant Design + Tailwind CSS                                     │
│  - SSE 流式对话渲染                                                          │
│  - 多页面: 聊天、录入、练习、管理、仪表盘                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │ HTTP/SSE
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             API 层 (FastAPI)                                 │
│  /api/v1/chat/stream       - 流式对话                                        │
│  /api/v1/extract/submit    - 异步面经提取                                    │
│  /api/v1/extract/tasks     - 任务列表/详情/编辑                               │
│  /api/v1/questions         - 题目管理（服务端过滤）                           │
│  /api/v1/stats/clusters    - 聚类统计                                        │
│  /api/v1/search            - 向量搜索                                        │
│  /api/v1/conversations     - 会话管理                                        │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        CacheService (Redis)                            │ │
│  │  - TTL 5分钟兜底                                                       │ │
│  │  - 主动失效 + 延迟双删                                                 │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
┌───────────────────┐      ┌───────────────────┐      ┌───────────────────┐
│    PostgreSQL     │      │     RabbitMQ      │      │      Redis        │
│  - 会话持久化      │      │   - 任务队列      │      │   - 缓存层        │
│  - 面经解析任务    │      │   - 削峰填谷      │      │   - 5分钟 TTL     │
│  - 图片 (gzip)    │      │                   │      │                   │
└───────────────────┘      └───────────────────┘      └───────────────────┘
          │                           │
          ▼                           ▼
┌───────────────────┐      ┌───────────────────────────────────────────────┐
│      Qdrant       │      │                   Workers                      │
│  - 向量存储        │      │  ┌──────────────────────────────────────────┐ │
│  - 混合检索        │      │  │ Extract Worker (面经异步解析)            │ │
│  - Payload 过滤    │      │  │ Answer Worker (答案生成)                 │ │
│  - 服务端过滤      │      │  │ Clustering Worker (聚类)                 │ │
└───────────────────┘      │  └──────────────────────────────────────────┘ │
                           └───────────────────────────────────────────────┘
```

---

## 核心特性

### 1. 异步面经解析

```
用户提交 → 返回 task_id → Worker 后台解析 → 用户查看/编辑 → 确认入库
```

- **即时响应**: 提交后立即返回，不阻塞前端
- **任务管理**: 查看任务列表、状态筛选、自动刷新
- **结果编辑**: 修改公司/岗位、编辑题目、删除题目
- **图片压缩**: Base64 gzip 压缩存储

### 2. 两阶段检索

```
Stage 1: 向量召回
  - 统一 Embedding: "公司：xxx | 岗位：xxx | 题目：xxx"
  - 召回 k*3 条候选

Stage 2: Rerank 精排
  - CrossEncoder (bge-reranker-base)
  - 返回 top-k 结果
```

### 3. 服务端过滤

```python
# Qdrant 服务端过滤，避免内存溢出
questions = qdrant.scroll_with_filter(
    company="字节跳动",
    cluster_ids=["cluster_rag"],
)
count = qdrant.count_with_filter(...)
```

### 4. Redis 缓存一致性

- **TTL 兜底**: 5 分钟自动过期
- **主动失效**: 写操作后删除缓存
- **延迟双删**: 解决并发读写问题
- **跨进程一致**: API 和 Worker 共用 CacheService

### 5. 题目聚类

- KMeans 聚类 + 自动 K 选择
- 按聚类筛选题目
- 聚类统计卡片

---

## 项目结构

```text
Offer-Catcher/
├── backend/                    # 后端服务 (Python FastAPI)
│   ├── app/
│   │   ├── agents/             # 智能体层
│   │   │   ├── chat_agent.py   # 聊天 Agent (流式输出)
│   │   │   ├── router.py       # 意图路由 Agent
│   │   │   ├── vision_extractor.py # 视觉提取 Agent
│   │   │   ├── scorer.py       # 答题评分 Agent
│   │   │   ├── answer_specialist.py # 异步答案生成 Agent
│   │   │   └── graph/          # LangGraph 工作流
│   │   │
│   │   ├── api/routes/         # FastAPI 路由
│   │   │   ├── chat.py         # 流式对话 API
│   │   │   ├── extract.py      # 面经提取 API (同步+异步)
│   │   │   ├── questions.py    # 题目管理 API
│   │   │   ├── stats.py        # 统计 API
│   │   │   └── conversations.py
│   │   │
│   │   ├── tools/              # 工具箱
│   │   │   ├── embedding_tool.py   # BGE-M3
│   │   │   ├── reranker_tool.py    # BGE-Reranker
│   │   │   ├── web_search_tool.py  # Tavily
│   │   │   └── search_question_tool.py
│   │   │
│   │   ├── db/                 # 数据库层
│   │   │   ├── qdrant_client.py    # Qdrant (服务端过滤)
│   │   │   ├── postgres_client.py  # PostgreSQL (任务表)
│   │   │   ├── redis_client.py     # Redis 缓存
│   │   │   └── graph_client.py     # Neo4j
│   │   │
│   │   ├── services/           # 业务服务
│   │   │   ├── clustering_service.py
│   │   │   └── cache_service.py    # Redis 缓存服务
│   │   │
│   │   ├── models/             # 数据模型
│   │   │   ├── schemas.py      # ExtractTask, QuestionItem, etc.
│   │   │   └── enums.py
│   │   │
│   │   └── prompts/            # Prompt 模板 (外置 .md)
│   │
│   ├── workers/                # 后台进程
│   │   ├── extract_worker.py   # 面经异步解析
│   │   ├── answer_worker.py    # 异步答案生成
│   │   └── clustering_worker.py
│   │
│   └── tests/
│
├── frontend/                   # 前端服务 (Next.js 16)
│   └── src/
│       ├── app/
│       │   ├── extract/        # 面经录入 (异步任务)
│       │   ├── questions/      # 题目管理 (聚类筛选)
│       │   ├── chat/           # AI 对话
│       │   ├── practice/       # 练习答题
│       │   └── dashboard/      # 仪表盘
│       ├── lib/api.ts          # API 客户端
│       └── types/              # TypeScript 类型
│
├── docs/                       # 文档
│   ├── architecture.md         # 系统架构
│   ├── api.md                  # API 文档
│   ├── async_extract_design.md # 异步解析设计
│   └── redis_cache_design.md   # 缓存设计
│
├── docker-compose.yml
├── CLAUDE.md                   # AI 编码指导
└── README.md
```

---

## 技术栈

### 后端

| 类别 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| Agent 框架 | LangChain + LangGraph |
| 向量数据库 | Qdrant |
| 关系数据库 | PostgreSQL |
| 图数据库 | Neo4j |
| 消息队列 | RabbitMQ |
| 缓存 | Redis |
| Embedding | BGE-M3 |
| Reranker | BGE-Reranker-Base |
| LLM | DeepSeek / DashScope |
| Web 搜索 | Tavily |

### 前端

| 类别 | 技术 |
|------|------|
| 框架 | Next.js 16 |
| UI 库 | React 19 |
| 组件库 | Ant Design |
| 样式 | Tailwind CSS |
| 类型 | TypeScript |

---

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- Docker
- uv (Python 包管理)

### 1. 启动依赖服务

```bash
docker-compose up -d

# 验证服务
# Qdrant: http://localhost:6333
# RabbitMQ: http://localhost:15672 (guest/guest)
# Neo4j: http://localhost:7474 (neo4j/neo4j)
# Redis: localhost:6379
# PostgreSQL: localhost:5432 (root/root)
```

### 2. 配置环境变量

```bash
cp backend/.env.example backend/.env
# 编辑 .env 填入 API Keys
```

### 3. 启动后端

```bash
cd backend
uv sync
uv run python -m app.main
```

访问 http://localhost:8000/docs 查看 API 文档。

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:3000。

### 5. 启动 Workers

```bash
cd backend

# 面经异步解析 Worker
PYTHONPATH=. uv run python workers/extract_worker.py

# 答案生成 Worker
PYTHONPATH=. uv run python workers/answer_worker.py

# 聚类 Worker (定时/手动)
PYTHONPATH=. uv run python workers/clustering_worker.py --run-now
```

---

## API 接口

### 面经解析

| 端点 | 方法 | 说明 |
|------|------|------|
| `/extract/submit` | POST | 提交解析任务 |
| `/extract/tasks` | GET | 获取任务列表 |
| `/extract/tasks/{id}` | GET | 获取任务详情 |
| `/extract/tasks/{id}` | PUT | 编辑解析结果 |
| `/extract/tasks/{id}/confirm` | POST | 确认入库 |

### 题目管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/questions` | GET | 题目列表（支持服务端过滤） |
| `/questions/{id}` | GET/PUT/DELETE | 单个题目操作 |
| `/questions/{id}/regenerate` | POST | 重新生成答案 |

### 统计

| 端点 | 方法 | 说明 |
|------|------|------|
| `/stats/overview` | GET | 总览统计 |
| `/stats/companies` | GET | 公司统计 |
| `/stats/clusters` | GET | 聚类统计 |

### 对话

| 端点 | 方法 | 说明 |
|------|------|------|
| `/chat/stream` | POST | 流式对话 (SSE) |
| `/conversations` | GET/POST/DELETE | 会话管理 |

---

## 核心数据模型

### 题目类型

| 类型 | 描述 | 异步生成答案 |
|------|------|-------------|
| `knowledge` | 客观基础题 | Yes |
| `project` | 项目深挖题 | No |
| `behavioral` | 行为/软技能题 | No |
| `scenario` | 场景题 | Yes |
| `algorithm` | 算法题 | Yes |

### 解析任务状态

| 状态 | 说明 |
|------|------|
| `pending` | 待处理 |
| `processing` | 处理中 |
| `completed` | 已完成 |
| `failed` | 失败 |
| `confirmed` | 已入库 |

---

## 面试高光抓手

### 1. 为什么引入 RabbitMQ？

> 面经往往是批量的。引入 RabbitMQ 实现了 **流量削峰填谷** 与 **失败重试机制**。

### 2. 异步面经解析的设计？

> 用户提交后立即返回 task_id，Worker 后台处理。用户可查看进度、编辑结果后再入库。图片使用 gzip 压缩存储。

### 3. 两阶段检索架构？

> Stage 1 向量召回（统一 Embedding），Stage 2 Rerank 精排。解决了检索端与入库端 Embedding 不一致的问题。

### 4. Redis 缓存一致性？

> TTL 兜底 + 主动失效 + 延迟双删。API 和 Worker 共用 CacheService，保证跨进程一致性。

### 5. Qdrant 服务端过滤？

> 避免加载全部数据到内存。使用 scroll_with_filter 和 count_with_filter 实现高效分页。

---

## 文档

- [系统架构文档](docs/architecture.md)
- [API 接口文档](docs/api.md)
- [异步解析设计](docs/async_extract_design.md)
- [Redis 缓存设计](docs/redis_cache_design.md)

---

## 开发路线

### v2.1 已完成

- 异步面经解析系统
- 两阶段检索 + Rerank
- Redis 缓存层
- 题目聚类功能
- 服务端过滤优化

### 未来规划

- 微信/Telegram 接入
- 用户认证与数据隔离
- 多语言支持

---

## License

MIT