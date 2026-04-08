# Offer-Catcher: 面经智能体系统

**版本**: v2.0 (前后端分离架构)
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
- **消息队列与 Multi-Agent 异步答疑**: 引入 RabbitMQ 削峰填谷，由主 Agent 调度带联网搜索能力的子 Agent 异步生成最新标准答案。
- **混合存储架构**: Qdrant 向量库（支撑细粒度混合检索） + Neo4j 图数据库（支撑宏观考频统计与知识点关联分析）。
- **前后端分离**: FastAPI 后端 + Next.js 前端，支持独立部署和扩展。

---

## 系统架构设计

系统采用 **"前后端分离、读写分离、主从智能体解耦、消息驱动"** 的架构。

```text
┌─────────────────────────────────────────────────────────────────┐
│                      前端层 (Next.js)                            │
│  - React 19 + Ant Design + Tailwind CSS                         │
│  - SSE 流式对话渲染                                              │
│  - 多页面: 聊天、录入、练习、管理、仪表盘                          │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP/SSE
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     API 层 (FastAPI)                             │
│  /api/v1/chat/stream     - 流式对话                              │
│  /api/v1/extract         - 面经提取                              │
│  /api/v1/score           - 答题评分                              │
│  /api/v1/questions       - 题目管理                              │
│  /api/v1/search          - 向量搜索                              │
│  /api/v1/stats           - 数据统计                              │
│  /api/v1/conversations   - 会话管理                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Agent 层 (LangGraph)                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Chat Agent     │  │ Vision Extractor│  │  Scorer Agent   │  │
│  │  (ReAct 流式)   │  │  (多模态提取)   │  │  (打分状态机)   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                              │                                   │
│              ┌───────────────┼───────────────┐                  │
│              ▼               ▼               ▼                  │
│         Search Web      Search Qdrant   Query Neo4j             │
│              (Tavily)     (Hybrid RAG)    (考频统计)             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     存储层 (Hybrid Storage)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Qdrant    │  │    Neo4j    │  │  PostgreSQL │              │
│  │  向量检索   │  │  图数据库   │  │  会话状态   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│  ┌─────────────┐  ┌─────────────┐                               │
│  │   Redis     │  │  RabbitMQ   │                               │
│  │  短期记忆   │  │  异步队列   │                               │
│  └─────────────┘  └─────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Worker 层 (后台进程)                          │
│  - Answer Worker: 异步答案生成                                   │
│  - Clustering Worker: 题目聚类定时任务                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```text
Offer-Catcher/
├── backend/                    # 后端服务 (Python FastAPI)
│   ├── app/
│   │   ├── agents/             # 智能体层
│   │   │   ├── base.py         # Agent 基类
│   │   │   ├── chat_agent.py   # 聊天 Agent (流式输出)
│   │   │   ├── router.py       # 意图路由 Agent
│   │   │   ├── vision_extractor.py # 视觉提取 Agent
│   │   │   ├── scorer.py       # 答题评分 Agent
│   │   │   ├── answer_specialist.py # 异步答案生成 Agent
│   │   │   └── graph/          # LangGraph 工作流
│   │   │       ├── state.py    # 状态定义
│   │   │       ├── nodes.py    # 节点实现
│   │   │       ├── edges.py    # 路由逻辑
│   │   │       └── workflow.py # 工作流组装
│   │   │
│   │   ├── api/                # FastAPI 路由
│   │   │   └── routes/
│   │   │       ├── chat.py     # 流式对话 API
│   │   │       ├── extract.py  # 面经提取 API
│   │   │       ├── score.py    # 答题评分 API
│   │   │       ├── questions.py # 题目管理 API
│   │   │       ├── search.py   # 搜索 API
│   │   │       ├── stats.py    # 统计 API
│   │   │       └── conversations.py # 会话管理 API
│   │   │
│   │   ├── tools/              # 工具箱
│   │   │   ├── embedding_tool.py # 向量嵌入 (BGE-M3)
│   │   │   ├── web_search_tool.py # 联网搜索 (Tavily)
│   │   │   ├── search_question_tool.py # 题目搜索
│   │   │   ├── vision_extractor_tool.py # 图片提取
│   │   │   └── query_graph_tool.py # 图数据库查询
│   │   │
│   │   ├── pipelines/          # 业务流水线
│   │   │   ├── ingestion.py    # 入库流水线
│   │   │   └── retrieval.py    # 检索流水线
│   │   │
│   │   ├── db/                 # 数据库层
│   │   │   ├── qdrant_client.py # Qdrant 向量数据库
│   │   │   ├── graph_client.py  # Neo4j 图数据库
│   │   │   ├── redis_client.py  # Redis 短期记忆
│   │   │   ├── postgres_client.py # PostgreSQL 历史对话
│   │   │   └── checkpointer.py  # LangGraph Checkpointer
│   │   │
│   │   ├── mq/                 # 消息队列层
│   │   │   ├── producer.py     # RabbitMQ 生产者
│   │   │   ├── consumer.py     # 异步消费者 (熔断)
│   │   │   ├── thread_pool_consumer.py # 线程池消费者
│   │   │   └── message_helper.py # 消息处理辅助
│   │   │
│   │   ├── models/             # 数据模型
│   │   │   ├── schemas.py      # Pydantic 模型
│   │   │   └── enums.py        # 枚举类
│   │   │
│   │   ├── prompts/            # Prompt 模板 (外置)
│   │   │   ├── vision_extractor.md
│   │   │   ├── answer_specialist.md
│   │   │   ├── router.md
│   │   │   ├── scorer.md
│   │   │   ├── react_agent.md  # ReAct Agent
│   │   │   └ chat_agent.md     # Chat Agent
│   │   │
│   │   ├── llm/                # LLM 工厂
│   │   │   └── __init__.py     # create_llm, get_llm
│   │   │
│   │   ├── config/             # 配置
│   │   │   └── settings.py     # Pydantic Settings
│   │   │
│   │   ├── services/           # 业务服务
│   │   │   └ clustering_service.py # 题目聚类
│   │   │
│   │   ├── skills/             # Skills 加载器
│   │   │
│   │   └── utils/              # 工具
│   │       ├── hasher.py       # MD5 哈希
│   │       ├── logger.py       # 日志
│   │       ├── retry.py        # 重试装饰器
│   │       ├── circuit_breaker.py # 熔断器
│   │       ├── cache.py        # 缓存装饰器
│   │       ├── telemetry.py    # OpenTelemetry
│   │       ├── ocr.py          # OCR 工具
│   │       └── image.py        # 图片处理
│   │
│   ├── workers/                # 后台进程
│   │   ├── answer_worker.py    # 异步答案生成
│   │   └ clustering_worker.py  # 聚类定时任务
│   │
│   ├── tests/                  # 测试用例
│   │   ├── test_qdrant_client.py
│   │   ├── test_graph_client.py
│   │   ├── test_vision_extractor.py
│   │   ├── test_scorer.py
│   │   ├── test_router.py
│   │   ├── test_tools.py
│   │   ├── test_answer_worker.py
│   │   ├── test_e2e.py
│   │   └ test_schemas.py
│   │   └ test_postgres_client.py
│   │   └ test_rabbitmq.py
│   │   └ test_chat_agent_tools.py
│   │
│   ├── main.py                 # FastAPI 入口
│   ├── pyproject.toml          # 项目配置
│   └── .env                    # 环境变量
│
├── frontend/                   # 前端服务 (Next.js)
│   ├── src/
│   │   ├── app/                # Next.js App Router
│   │   ├── components/         # React 组件
│   │   ├── lib/                # API 客户端
│   │   └ types/                # TypeScript 类型
│   │
│   ├── package.json            # 依赖配置
│   └ next.config.ts            # Next.js 配置
│   └ tailwind.config           # Tailwind 配置
│   └ tsconfig.json             # TypeScript 配置
│
├── gateways/                   # Streamlit 前端 (兼容)
│   ├── cli_chat.py             # Streamlit 主入口
│   └── pages/                  # 多页面
│       ├── 0_chat.py           # AI 聊天
│       ├── 1_interview_input.py # 录入面经
│       ├── 2_practice.py       # 练习答题
│       ├── 3_question_management.py # 题目管理
│       ├── 4_dashboard.py      # 仪表盘
│       └── 5_cluster_view.py   # 考点聚类
│   └── components/
│       └── question_card.py    # 题目卡片组件
│
├── models/                     # 共享模型文件
│
├── docker-compose.yml          # Docker 服务配置
├── CLAUDE.md                   # AI 编码指导
└── README.md                   # 项目文档
```

---

## 技术栈

### 后端

- **Python 3.10+** - 核心语言
- **FastAPI + Uvicorn** - Web API 框架
- **LangChain** - Agent 开发框架
- **LangGraph** - 工作流编排框架
- **Qdrant** - 向量数据库
- **Neo4j** - 图数据库
- **Redis** - 短期记忆存储
- **PostgreSQL** - 历史对话存储 + LangGraph Checkpointer
- **RabbitMQ** - 消息队列
- **DashScope/DeepSeek** - 大模型 API
- **Tavily** - Web 搜索 API
- **OpenTelemetry + Jaeger** - 可观测性

### 前端

- **Next.js 16** - React 框架
- **React 19** - UI 库
- **Ant Design** - UI 组件库
- **Tailwind CSS** - 样式框架
- **TypeScript** - 类型安全

### 兼容前端 (Streamlit)

- **Streamlit** - 快速原型开发

---

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- Docker (用于运行 Qdrant、RabbitMQ、Neo4j、Redis、PostgreSQL)
- uv (Python 包管理工具)

### 1. 启动依赖服务

```bash
# 启动所有依赖服务
docker-compose up -d

# 验证服务启动
# Qdrant: http://localhost:6333
# RabbitMQ: http://localhost:15672 (guest/guest)
# Neo4j: http://localhost:7474 (neo4j/neo4j)
# Redis: localhost:6379
# PostgreSQL: localhost:5432 (root/root)
# Jaeger: http://localhost:16686
```

### 2. 配置环境变量

```bash
# 复制并编辑 backend/.env 文件
cp backend/.env.example backend/.env
# 编辑 backend/.env 填入你的 API Keys
```

### 3. 启动后端 API

```bash
cd backend

# 安装依赖
uv sync

# 启动 FastAPI 服务
uv run python -m app.main

# 或使用 uvicorn
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000/docs 查看 API 文档。

### 4. 启动前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

访问 http://localhost:3000。

### 5. 启动后台 Worker

```bash
cd backend

# 启动 RabbitMQ Consumer (异步答案生成)
PYTHONPATH=. uv run python workers/answer_worker.py

# 启动聚类定时任务 (每天凌晨 2 点)
PYTHONPATH=. uv run python workers/clustering_worker.py

# 立即执行一次聚类
PYTHONPATH=. uv run python workers/clustering_worker.py --run-now
```

### 6. 启动 Streamlit 前端 (可选，兼容模式)

```bash
PYTHONPATH=backend uv run streamlit run gateways/cli_chat.py --server.port 8501
```

访问 http://localhost:8501。

---

## API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/chat/stream` | POST | 流式对话 (SSE) |
| `/api/v1/extract` | POST | 提取面经 (文本/图片) |
| `/api/v1/score` | POST | 答题评分 |
| `/api/v1/questions` | GET/PUT/DELETE | 题目管理 |
| `/api/v1/search` | POST | 向量搜索 |
| `/api/v1/stats` | GET | 数据统计 |
| `/api/v1/conversations` | GET/POST/DELETE | 会话管理 |
| `/health` | GET | 健康检查 |

---

## 核心数据模型

### 题目类型

| 类型 | 描述 | 异步生成答案 |
|------|------|-------------|
| `knowledge` | 客观基础题（八股文） | Yes |
| `project` | 项目深挖题 | No |
| `behavioral` | 行为/软技能题 | No |
| `scenario` | 场景题 | Yes |
| `algorithm` | 算法题 | Yes |

### 掌握程度

| 等级 | 说明 |
|------|------|
| `LEVEL_0` | 未掌握/未复习 |
| `LEVEL_1` | 比较熟悉 |
| `LEVEL_2` | 已掌握 |

---

## 面试高光抓手

### 1. 为什么引入 RabbitMQ？

> 面经往往是批量的（如一次解析 50 题）。若直接并发调用大模型生成答案，极易触发 API Rate Limit。引入 RabbitMQ 实现了 **流量削峰填谷** 与 **失败重试（DLQ）机制**。

### 2. 如何解决 Agent 答题的"幻觉"？

> 采用 **基于 LLM 意图的前置分类熔断机制**。对于 knowledge/scenario/algorithm 类型，调度带联网工具的子 Agent 生成最新答案；对于 project/behavioral 类型，直接触发熔断不予生成。

### 3. Qdrant 向量库的数据粒度设计？

> 抛弃粗暴的 Document-level 切分，采用 **Question-level Chunking + 上下文拼接** 策略，结合 Qdrant Payload 标量索引实现 Pre-filtering + 向量比对的混合检索。

### 4. 图数据库的价值？

> 通过 Neo4j 实现 **考频统计**（各公司热门考点）、**知识点关联分析**（常一起考察的知识点）、**跨公司通用考点**识别。

### 5. 为什么前后端分离？

- **独立部署**: 后端可部署在云服务器，前端可部署在 Vercel/CDN
- **技术栈解耦**: 前端使用现代 React 生态，后端专注 Python AI 逻辑
- **扩展性**: 支持多前端接入（Web、小程序、CLI）
- **流式渲染**: SSE 更适合 React 的组件化渲染

---

## 开发指南

### 运行测试

```bash
cd backend

# 运行所有测试
uv run pytest tests/ -v

# 运行特定测试
uv run pytest tests/test_qdrant_client.py -v

# 测试使用独立的测试 collection，不影响生产数据
```

### 可观测性

启用 OpenTelemetry：

```bash
# 在 .env 中配置
TELEMETRY_ENABLED=true
OTLP_ENDPOINT=http://localhost:4317
```

访问 Jaeger UI: http://localhost:16686

### 收集的指标

| 指标 | 说明 |
|------|------|
| `tool.calls.total` | 工具调用次数 |
| `tool.calls.duration` | 工具调用时长 |
| `llm.tokens.input/output` | Token 消耗 |
| `vector.query.duration` | 向量检索时长 |

---

## 开发路线

### 已完成

- Vision Extractor 多模态提取
- Qdrant 向量库 + 混合检索
- RabbitMQ 异步队列 + 熔断机制
- Web Search Agent 联网生成答案
- Neo4j 图数据库考频分析
- Scorer Agent 打分状态机
- LangGraph ReAct 工作流
- FastAPI 后端 API
- Next.js 前端
- OpenTelemetry 可观测性

### 未来规划

- 微信/Telegram Webhook 接入
- Redis 语义缓存优化
- 用户认证与数据隔离
- 多语言支持

---

## License

MIT