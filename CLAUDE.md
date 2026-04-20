# CLAUDE.md - Offer-Catcher Project Guidelines

你是一个专业的 Agent 开发工程师和资深 Python 架构师。本文档为 Claude Code (claude.ai/code) 在本项目中的编码与架构决策提供核心指导。请在执行任何代码生成或重构前仔细阅读。

## 项目架构概述

本项目采用 **DDD (领域驱动设计) 四层架构**：

```text
API 层 (api/)
    ↓ 依赖
Application 层 (application/)
    ↓ 依赖
Domain 层 (domain/)
    ↓ 依赖（通过 Protocol）
Infrastructure 层 (infrastructure/)
    ↑ 实现 Domain Protocol（依赖倒置）
```

- **后端**: `backend/app/` - FastAPI + LangGraph + LangChain (Python)
- **前端**: `frontend/src/` - Next.js 16 + React 19 + Ant Design (TypeScript)

---

## DDD 分层职责

### Domain 层 (`domain/`)

**职责**: 领域模型、业务规则、Repository Protocol、领域事件

| 领域 | 内容 |
|------|------|
| `domain/shared/` | Enums, Exceptions |
| `domain/question/` | Question, Cluster, ExtractTask 聚合 + Repository Protocol + Events |
| `domain/interview/` | InterviewSession 聚合 + Repository Protocol + Events |
| `domain/chat/` | Conversation 聚合 + Repository Protocol + Events |
| `domain/favorite/` | Favorite 聚合 + Repository Protocol + Events |

**关键规则**:
- Domain 层不依赖任何外层（无 Infrastructure import）
- Repository 定义为 Protocol（结构化接口）
- 使用 `@runtime_checkable` 支持运行时检查

### Application 层 (`application/`)

**职责**: 用例编排、Agent 执行器、后台 Worker

| 子目录 | 内容 |
|--------|------|
| `services/` | IngestionService, QuestionService, ChatService, InterviewService 等 |
| `workers/` | AnswerWorker, ExtractWorker, ClusteringWorker, ReembedWorker |
| `agents/` | Chat, Interview, VisionExtractor, AnswerSpecialist, Scorer, TitleGenerator |

**关键规则**:
- Application 层依赖 Domain Protocol，不依赖具体 Infrastructure 实现
- Agent 是 Workflow 的执行器，负责调用领域逻辑、管理聚合

### Infrastructure 层 (`infrastructure/`)

**职责**: 仓库实现、消息队列、外部服务适配器

| 子目录 | 内容 |
|--------|------|
| `persistence/` | Qdrant, PostgreSQL, Redis, Neo4j Repository 实现 |
| `messaging/` | RabbitMQ Producer, Consumer, Messages |
| `adapters/` | Embedding, Reranker, WebSearch, OCR, ASR, LLM, Cache |
| `tools/` | LangChain @tool（search_questions, search_web, query_graph） |
| `common/` | Logger, Cache, Retry, CircuitBreaker, Prompt |
| `observability/` | Telemetry |
| `bootstrap/` | Warmup |
| `config/` | Settings |

**关键规则**:
- Infrastructure 实现 Domain Protocol，无需显式继承
- 依赖注入通过 Factory 或 FastAPI Depends

### API 层 (`api/`)

**职责**: HTTP 路由、DTO 模型

| 子目录 | 内容 |
|--------|------|
| `routes/` | Chat, Interview, Extract, Questions, Favorites, Stats, Search |
| `dto/` | ChatDTO, InterviewDTO, QuestionDTO, ExtractDTO |

---

## AI 编码行为准则

### 1. 强类型约束

- 所有函数必须包含完整的 Type Hints
- 数据传输必须且只能通过 `pydantic` (V2) 模型
- 严禁使用裸字典 (`dict`) 在不同层之间传递核心业务数据

### 2. Prompt 编写原则

- 严禁将长篇 Prompt 字符串硬编码在 Python 文件中
- 系统提示词存放在 `application/agents/*/prompts/` 目录下
- 使用 `load_prompt_template` 方法加载

### 3. 日志优先

- 禁止使用 `print()` 打印业务流
- 使用 `infrastructure/common/logger.py`

### 4. 防御性编程

- LLM API、Qdrant、RabbitMQ 调用必须包含 `try-except`
- Consumer 正确处理 `Nack` 和重试逻辑

### 5. Agent 消息规范

- Agent 消息必须是 LangChain 类型：`AIMessage`, `HumanMessage`, `SystemMessage`
- 不允许自定义字典结构

### 6. LangChain/LangGraph 最佳实践

- 尽可能复用 LangChain 组件
- 使用 doc-langchain MCP 工具查阅 API

### 7. 重构原则

- 不要进行向后兼容，直接重构
- 禁止在业务代码中使用 Emoji

### 8. 测试规范

- 禁止在测试用例中写生产数据库
- 测试文件放在 `backend/tests/` 目录

### 9. Import 规范

- 除热加载/初始化场景，所有 import 放在模块顶部

---

## 领域模型位置

**重要**: 业务数据模型在 `domain/*/aggregates.py`

| 领域 | 聚合根 |
|------|--------|
| `domain/question/aggregates.py` | Question, Cluster, ExtractTask, QuestionItem, ExtractedInterview |
| `domain/interview/aggregates.py` | InterviewSession, InterviewQuestion, InterviewReport |
| `domain/chat/aggregates.py` | Conversation, Message |
| `domain/favorite/aggregates.py` | Favorite |

### 枚举类 (`domain/shared/enums.py`)

- `QuestionType`: knowledge, project, behavioral, scenario, algorithm
- `MasteryLevel`: LEVEL_0, LEVEL_1, LEVEL_2
- `DifficultyLevel`: easy, medium, hard
- `SessionStatus`: active, completed, cancelled
- `QuestionStatus`: pending, scored, skipped

---

## 核心架构设计模式

### 1. 分类熔断机制

Vision Extractor 提取时 LLM 打标。仅 `knowledge`/`scenario`/`algorithm` 触发 MQ 异步答案生成；`project`/`behavioral` 熔断。

### 2. 上下文拼接 Embedding

计算向量时拼接上下文：`"公司：字节跳动 | 岗位：Agent应用开发 | 题目：qlora怎么优化显存？"`

### 3. 混合检索底座

Qdrant Payload 包含 company, position, mastery_level, question_type。检索时先 Payload 硬过滤，再向量计算。

### 4. 主键幂等性

`question_id = MD5("公司名" + "题目文本")`。Upsert 保证一致性。

### 5. 主从 Agent 解耦

主系统发送 Context 到 RabbitMQ，Worker 消费并唤醒 AnswerSpecialist（挂载 WebSearch）。

### 6. 状态管理

Chat Agent 使用 LangGraph Checkpointer + PostgreSQL 持久化。

### 7. 流式输出

后端 `StreamingResponse` + SSE，前端 `fetch` + `ReadableStream`。

---

## 项目目录结构

```text
backend/app/
│
├── domain/                       # 领域层
│   ├── shared/                   # 共享内核
│   │   ├── enums.py              # 枚举定义
│   │   └── exceptions.py         # 领域异常
│   │
│   ├── question/                 # 题库领域
│   │   ├── aggregates.py         # Question, Cluster, ExtractTask
│   │   ├── repositories.py       # Repository Protocol
│   │   ├── events.py             # 领域事件
│   │   └── services.py           # 领域服务
│   │
│   ├── interview/                # 模拟面试领域
│   │   ├── aggregates.py         # InterviewSession
│   │   ├── repositories.py       # Repository Protocol
│   │   ├── events.py             # 领域事件
│   │   └── services.py           # 领域服务
│   │
│   ├── chat/                     # 智能对话领域
│   │   ├── aggregates.py         # Conversation
│   │   ├── repositories.py       # Repository Protocol
│   │   ├── events.py             # 领域事件
│   │   └── services.py           # 领域服务
│   │
│   └── favorite/                 # 收藏领域
│       ├── aggregates.py         # Favorite
│       └── repositories.py       # Repository Protocol
│       └── events.py             # 领域事件
│
├── application/                  # 应用层
│   ├── services/                 # 应用服务
│   │   ├── ingestion_service.py  # 入库用例
│   │   ├── retrieval_service.py  # 检索用例
│   │   ├── question_service.py   # 题 CRUD
│   │   ├── chat_service.py       # 对话用例
│   │   ├── interview_service.py  # 面试用例
│   │   ├── cache_service.py      # 缓存用例
│   │   ├── clustering_service.py # 聚类用例
│   │   └── stats_service.py      # 统计用例
│   │
│   ├── workers/                  # 后台任务
│   │   ├── answer_worker.py
│   │   ├── extract_worker.py
│   │   ├── clustering_worker.py
│   │   └── reembed_worker.py
│   │
│   └── agents/                   # Agent 执行器
│       ├── chat/
│       │   ├── agent.py
│       │   ├── workflow.py
│       │   ├── state.py
│       │   ├── nodes.py
│       │   ├── edges.py
│       │   ├── runtime.py        # UserContext
│       │   └── prompts/
│       │
│       ├── interview/
│       │   ├── agent.py
│       │   └── prompts/
│       │
│       ├── vision_extractor/
│       │   ├── agent.py
│       │   └── prompts/
│       │
│       ├── answer_specialist/
│       │   ├── agent.py
│       │   └── prompts/
│       │
│       ├── scorer/
│       │   ├── agent.py
│       │   ├── results.py
│       │   └── prompts/
│       │
│       ├── title_generator/
│       │   ├── agent.py
│       │   └── prompts/
│       │
│       └── factory.py            # Agent 工厂
│
├── infrastructure/               # 基础设施层
│   ├── persistence/
│   │   ├── qdrant/
│   │   │   ├── client.py
│   │   │   ├── question_repository.py
│   │   │   ├── cluster_repository.py
│   │   │   └── payloads.py
│   │   │
│   │   ├── postgres/
│   │   │   ├── client.py
│   │   │   ├── extract_task_repository.py
│   │   │   ├── interview_session_repository.py
│   │   │   ├── conversation_repository.py
│   │   │   ├── favorite_repository.py
│   │   │   └── checkpointer.py
│   │   │
│   │   ├── redis/
│   │   │   └── client.py
│   │   │
│   │   └── neo4j/
│   │       └── client.py
│   │
│   ├── messaging/
│   │   ├── producer.py
│   │   ├── consumer.py
│   │   ├── thread_pool_consumer.py
│   │   └── messages.py
│   │
│   ├── adapters/
│   │   ├── embedding_adapter.py
│   │   ├── reranker_adapter.py
│   │   ├── web_search_adapter.py
│   │   ├── llm_adapter.py
│   │   ├── ocr_adapter.py
│   │   ├── asr_adapter.py
│   │   └── cache_adapter.py
│   │
│   ├── tools/
│   │   ├── search_questions.py
│   │   ├── search_web.py
│   │   └── query_graph.py
│   │
│   ├── common/
│   │   ├── logger.py
│   │   ├── cache.py              # @singleton
│   │   ├── retry.py
│   │   ├── circuit_breaker.py
│   │   ├── prompt.py
│   │   ├── image.py
│   │   └── cache_keys.py
│   │
│   ├── observability/
│   │   └── telemetry.py
│   │
│   ├── bootstrap/
│   │   └── warmup.py
│   │
│   └── config/
│       └── settings.py
│
├── api/                          # API 层
│   ├── routes/
│   │   ├── chat.py
│   │   ├── interview.py
│   │   ├── extract.py
│   │   ├── questions.py
│   │   ├── favorites.py
│   │   ├── search.py
│   │   ├── stats.py
│   │   ├── score.py
│   │   └── conversations.py
│   │
│   └── dto/
│       ├── chat_dto.py
│       ├── interview_dto.py
│       ├── question_dto.py
│       ├── extract_dto.py
│       ├── search_dto.py
│       └── favorite_dto.py
│
└── main.py                       # FastAPI 入口
```

---

## 开发与测试命令

### 环境管理

使用 `uv` 包管理。

### 后端开发

```bash
cd backend

# 安装依赖
uv sync

# 启动 API 服务
uv run python -m app.main

# 启动 Worker
PYTHONPATH=. uv run python -m app.application.workers.answer_worker

# 运行测试
uv run pytest tests/ -v

# 运行领域测试
uv run pytest tests/domain/ -v
```

### 前端开发

```bash
cd frontend

npm install
npm run dev
npm run build
```

---

## API 设计规范

### 流式响应

```python
@router.post("/stream")
async def chat_stream(request: ChatRequest):
    async def generate():
        async for chunk in agent.achat_streaming(...):
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
```

---

## 重要提醒

1. **领域模型在 `domain/*/aggregates.py`**
2. **Repository Protocol 在 `domain/*/repositories.py`**
3. **Repository 实现在 `infrastructure/persistence/*/`**
4. **Agent 执行器在 `application/agents/`**
5. **Prompt 模板在 `application/agents/*/prompts/`**
6. **LangChain @tool 在 `infrastructure/tools/`**
7. **测试代码在 `backend/tests/`**

---

## 相关文档

- [DDD重构设计](docs/DDD重构设计.md)
- [DDD重构进度](docs/DDD重构进度.md)