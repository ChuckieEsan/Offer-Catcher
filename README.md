# Offer-Catcher: 面经智能体系统

**版本**: v3.0 (DDD 架构重构)
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
- **DDD 架构**: 领域驱动设计，清晰的分层架构，高可维护性和可测试性。

---

## 系统架构设计

系统采用 **"前后端分离、DDD 分层架构、主从智能体解耦、消息驱动"** 的架构。

### DDD 四层架构

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                         API 层 (FastAPI)                                     │
│  Routes: chat, interview, extract, questions, stats, favorites             │
│  DTOs: 请求/响应模型，数据转换                                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Application 层 (应用层)                                 │
│  Services: 用例编排（Ingestion, Retrieval, Question, Chat, Interview）       │
│  Workers: 后台任务（Answer, Extract, Clustering, Reembed）                   │
│  Agents: Agent 执行器（Chat, Interview, Vision, Answer, Title, Scorer）      │
│  Events: 领域事件发布/订阅                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Domain 层 (领域层)                                    │
│  question: Question, Cluster, ExtractTask 聚合                              │
│  interview: InterviewSession 聚合                                            │
│  chat: Conversation 聚合                                                     │
│  favorite: Favorite 聚合                                                     │
│  shared: Enums, Exceptions, Events                                          │
│  Repository Protocol: 仓库接口定义                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Infrastructure 层 (基础设施层)                            │
│  Persistence: Qdrant, PostgreSQL, Redis, Neo4j 仓库实现                      │
│  Messaging: RabbitMQ Producer, Consumer                                     │
│  Adapters: Embedding, Reranker, WebSearch, OCR, ASR, LLM                    │
│  Tools: LangChain @tool（search_questions, search_web, query_graph）         │
│  Common: Logger, Cache, Retry, CircuitBreaker                               │
│  Bootstrap: Warmup, 配置加载                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```text
Offer-Catcher/
├── backend/                        # 后端服务 (Python FastAPI)
│   ├── app/
│   │   ├── domain/                 # 领域层 (DDD 核心)
│   │   │   ├── shared/             # 共享内核
│   │   │   │   ├── enums.py        # QuestionType, MasteryLevel 等
│   │   │   │   └── exceptions.py   # 领域异常
│   │   │   │
│   │   │   ├── question/           # 题库领域
│   │   │   │   ├── aggregates.py   # Question, Cluster, ExtractTask 聚合
│   │   │   │   ├── repositories.py # Repository Protocol
│   │   │   │   ├── events.py       # 领域事件
│   │   │   │   └── services.py     # 领域服务
│   │   │   │
│   │   │   ├── interview/          # 模拟面试领域
│   │   │   │   ├── aggregates.py   # InterviewSession 聚合
│   │   │   │   ├── repositories.py # Repository Protocol
│   │   │   │   ├── events.py       # 领域事件
│   │   │   │   └── services.py     # 领域服务
│   │   │   │
│   │   │   ├── chat/               # 智能对话领域
│   │   │   │   ├── aggregates.py   # Conversation 聚合
│   │   │   │   ├── repositories.py # Repository Protocol
│   │   │   │   ├── events.py       # 领域事件
│   │   │   │   └── services.py     # 领域服务
│   │   │   │
│   │   │   └── favorite/           # 收藏领域
│   │   │       ├── aggregates.py   # Favorite 聚合
│   │   │       └── repositories.py # Repository Protocol
│   │   │
│   │   ├── application/            # 应用层
│   │   │   ├── services/           # 应用服务 (用例编排)
│   │   │   │   ├── ingestion_service.py    # 面经入库
│   │   │   │   ├── retrieval_service.py   # 检索用例
│   │   │   │   ├── question_service.py    # 题 CRUD
│   │   │   │   ├── chat_service.py        # 对话用例
│   │   │   │   ├── interview_service.py   # 面试用例
│   │   │   │   └── ...
│   │   │   │
│   │   │   ├── workers/            # 后台任务
│   │   │   │   ├── answer_worker.py       # 答案生成
│   │   │   │   ├── extract_worker.py      # 面经提取
│   │   │   │   ├── clustering_worker.py   # 聚类
│   │   │   │   └── reembed_worker.py      # 向量重建
│   │   │   │
│   │   │   └── agents/             # Agent 执行器
│   │   │       ├── chat/           # 对话 Agent
│   │   │       │   ├── agent.py    # Agent 实现
│   │   │       │   ├── workflow.py # LangGraph Workflow
│   │   │       │   ├── state.py    # AgentState
│   │   │       │   ├── nodes.py    # 节点函数
│   │   │       │   └── runtime.py  # UserContext
│   │   │       │   └── prompts/    # Prompt 模板
│   │   │       │
│   │   │       ├── interview/      # 面试 Agent
│   │   │       ├── vision_extractor/ # 面经提取 Agent
│   │   │       ├── answer_specialist/ # 答案生成 Agent
│   │   │       ├── scorer/         # 评分 Agent
│   │   │       ├── title_generator/ # 标题生成 Agent
│   │   │       └── factory.py      # Agent 工厂
│   │   │
│   │   ├── infrastructure/         # 基础设施层
│   │   │   ├── persistence/        # 持久化
│   │   │   │   ├── qdrant/         # Qdrant 向量库
│   │   │   │   │   ├── client.py
│   │   │   │   │   ├── question_repository.py
│   │   │   │   │   ├── cluster_repository.py
│   │   │   │   │   └── payloads.py
│   │   │   │   │
│   │   │   │   ├── postgres/       # PostgreSQL
│   │   │   │   │   ├── client.py
│   │   │   │   │   ├── extract_task_repository.py
│   │   │   │   │   ├── interview_session_repository.py
│   │   │   │   │   ├── conversation_repository.py
│   │   │   │   │   ├── favorite_repository.py
│   │   │   │   │   └── checkpointer.py
│   │   │   │   │
│   │   │   │   ├── redis/          # Redis 缓存
│   │   │   │   └── neo4j/          # Neo4j 图数据库
│   │   │   │
│   │   │   ├── messaging/          # 消息队列
│   │   │   │   ├── producer.py
│   │   │   │   ├── consumer.py
│   │   │   │   ├── thread_pool_consumer.py
│   │   │   │   └── messages.py
│   │   │   │
│   │   │   ├── adapters/           # 外部服务适配器
│   │   │   │   ├── embedding_adapter.py    # BGE-M3
│   │   │   │   ├── reranker_adapter.py     # BGE-Reranker
│   │   │   │   ├── web_search_adapter.py   # Tavily
│   │   │   │   ├── llm_adapter.py          # DeepSeek/DashScope
│   │   │   │   ├── ocr_adapter.py          # OCR
│   │   │   │   └── asr_adapter.py          # 讯飞 ASR
│   │   │   │
│   │   │   ├── tools/              # LangChain Tools
│   │   │   │   ├── search_questions.py
│   │   │   │   ├── search_web.py
│   │   │   │   └── query_graph.py
│   │   │   │
│   │   │   ├── common/             # 通用工具
│   │   │   │   ├── logger.py
│   │   │   │   ├── cache.py        # @singleton
│   │   │   │   ├── retry.py
│   │   │   │   ├── circuit_breaker.py
│   │   │   │   ├── prompt.py       # Prompt 加载
│   │   │   │   └── image.py
│   │   │   │
│   │   │   ├── observability/      # 可观测性
│   │   │   │   └── telemetry.py
│   │   │   │
│   │   │   ├── bootstrap/          # 启动预热
│   │   │   │   └── warmup.py
│   │   │   │
│   │   │   └── config/             # 配置
│   │   │       └── settings.py
│   │   │
│   │   ├── api/                    # API 层
│   │   │   ├── routes/             # FastAPI 路由
│   │   │   │   ├── chat.py
│   │   │   │   ├── interview.py
│   │   │   │   ├── extract.py
│   │   │   │   ├── questions.py
│   │   │   │   ├── favorites.py
│   │   │   │   ├── search.py
│   │   │   │   ├── stats.py
│   │   │   │   ├── score.py
│   │   │   │   └── conversations.py
│   │   │   │
│   │   │   └── dto/                # DTO 模型
│   │   │       ├── chat_dto.py
│   │   │       ├── interview_dto.py
│   │   │       ├── question_dto.py
│   │   │       ├── extract_dto.py
│   │   │       └── ...
│   │   │
│   │   └── main.py                 # FastAPI 入口
│   │
│   ├── tests/                      # 测试用例
│   │   ├── domain/                 # 领域测试
│   │   ├── application/            # 应用层测试
│   │   └── memory/                 # 记忆系统测试
│   │
│   └── pyproject.toml              # 项目配置
│
├── frontend/                       # 前端服务 (Next.js 16)
│   └── src/
│       ├── app/                    # App Router 页面
│       │   ├── chat/               # AI 对话
│       │   ├── interview/          # 模拟面试
│       │   ├── practice/           # 刷题练习
│       │   ├── questions/          # 题库管理
│       │   ├── extract/            # 面经导入
│       │   ├── favorites/          # 收藏管理
│       │   └── dashboard/          # 数据看板
│       │
│       ├── components/             # React 组件
│       ├── lib/                    # API 客户端
│       └── types/                  # TypeScript 类型
│
├── docs/                           # 文档
│   ├── DDD重构设计.md              # DDD 架构设计
│   ├── DDD重构进度.md              # 重构进度跟踪
│   └── ...
│
├── docker-compose.yml
├── CLAUDE.md                       # AI 编码指导
└── README.md
```

---

## 核心特性

### 1. DDD 分层架构

- **Domain 层**: 领域模型（聚合根、实体、值对象）、Repository Protocol、领域事件
- **Application 层**: 用例编排、Agent 执行器、后台 Worker
- **Infrastructure 层**: 仓库实现、消息队列、外部服务适配器
- **API 层**: FastAPI 路由、DTO 模型

### 2. 异步面经解析

```
用户提交 → 返回 task_id → Worker 后台解析 → 用户查看/编辑 → 确认入库
```

### 3. 两阶段检索

```
Stage 1: 向量召回 (BGE-M3)
Stage 2: Rerank 精排 (BGE-Reranker-Base)
```

### 4. 分类熔断机制

| 题目类型 | 描述 | 异步生成答案 |
|----------|------|-------------|
| `knowledge` | 客观基础题 | Yes |
| `project` | 项目深挖题 | No |
| `behavioral` | 行为/软技能题 | No |
| `scenario` | 场景题 | Yes |
| `algorithm` | 算法题 | Yes |

---

## 技术栈

### 后端

| 类别 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| Agent 框架 | LangChain + LangGraph |
| 架构模式 | DDD (Domain-Driven Design) |
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

- Python 3.13+
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
PYTHONPATH=. uv run python -m app.application.workers.extract_worker

# 答案生成 Worker
PYTHONPATH=. uv run python -m app.application.workers.answer_worker

# 聚类 Worker (定时/手动)
PYTHONPATH=. uv run python -m app.application.workers.clustering_worker --run-now
```

---

## API 接口

### 面经解析

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/extract/submit` | POST | 提交解析任务 |
| `/api/v1/extract/tasks` | GET | 获取任务列表 |
| `/api/v1/extract/tasks/{id}` | GET | 获取任务详情 |
| `/api/v1/extract/tasks/{id}` | PUT | 编辑解析结果 |
| `/api/v1/extract/tasks/{id}/confirm` | POST | 确认入库 |

### 题目管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/questions` | GET | 题目列表（支持过滤） |
| `/api/v1/questions/{id}` | GET/PUT/DELETE | 单个题目操作 |
| `/api/v1/questions/{id}/regenerate` | POST | 重新生成答案 |

### 统计

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/stats/overview` | GET | 总览统计 |
| `/api/v1/stats/companies` | GET | 公司统计 |
| `/api/v1/stats/clusters` | GET | 聚类统计 |

### 对话

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/chat/stream` | POST | 流式对话 (SSE) |
| `/api/v1/conversations` | GET/POST/DELETE | 会话管理 |

---

## 开发路线

### v3.0 已完成

- DDD 四层架构重构
- Domain 层：Question、Interview、Chat、Favorite 领域
- Application 层：Services、Workers、Agents
- Infrastructure 层：Persistence、Messaging、Adapters、Tools
- API 层：Routes、DTOs
- 清理旧代码：models、agents、tools、pipelines、db、mq、utils

### 未来规划

- 记忆领域重新设计
- 事件发布/处理机制
- 微信/Telegram 接入
- 用户认证与数据隔离

---

## 文档

- [DDD重构设计](docs/DDD重构设计.md)
- [DDD重构进度](docs/DDD重构进度.md)
- [AI 编码指导](CLAUDE.md)

---

## License

MIT