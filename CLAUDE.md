# CLAUDE.md - Offer-Catcher Project Guidelines

你是一个专业的 Agent 开发工程师和资深 Python 架构师。本文档为 Claude Code (claude.ai/code) 在本项目中的编码与架构决策提供核心指导。请在执行任何代码生成或重构前仔细阅读。

## 项目架构概述

本项目采用 **前后端分离架构**：

- **后端**: `backend/app/` - FastAPI + LangGraph + LangChain (Python)
- **前端**: `frontend/src/` - Next.js 16 + React 19 + Ant Design (TypeScript)

---

## AI 编码行为准则

在编写代码时，你需要遵循软件开发的 SDD 和 TDD 准则，在编写完每个模块的代码后，你需要编写对应的单元测试以验证写的模块代码可用，
随后才可以转入下一个模块的开发。在写完代码后，你需要通过 git 来检测你新写的代码，并让代码符合下面的规范：

### 1. 强类型约束

- 所有函数必须包含完整的 Type Hints（类型提示）
- 数据传输必须且只能通过 `pydantic` (V2版本) 模型
- 严禁使用裸字典 (`dict`) 在不同层之间传递核心业务数据

### 2. Prompt 外置原则

- 严禁将长篇 Prompt 字符串硬编码在 Python 文件中
- 所有的系统提示词必须作为单独的 `.md` 文件存放在 `backend/app/agents/prompts/` 目录下
- 在代码中按需读取，使用 `load_prompt_template` 方法

### 3. 日志优先

- 禁止使用标准的 `print()` 函数打印业务流
- 请使用 `backend/app/utils/logger.py` 进行日志记录
- 便于后续在生产环境和排查 MQ 消费时追踪

### 4. 防御性编程

- 在调用 LLM API、Qdrant 数据库和 RabbitMQ 时，必须包含 `try-except` 块
- 在合适的地方（如 RabbitMQ Consumer）正确处理 `Nack` 或失败重试逻辑

### 5. Agent 消息规范

- Agent 的消息必须是 Langchain 的消息类型：`AIMessage`, `HumanMessage`, `SystemMessage`, `BaseMessage`
- 不允许自定义字典结构作为消息

### 6. LangChain/LangGraph 最佳实践

- 尽可能复用 Langchain 已有的组件，减少重复造轮子
- 使用 doc-langchain MCP 工具查阅相关 API

### 7. 重构原则

- 如果发生重构，不要进行向后兼容，直接重构
- 禁止在业务代码中使用 Emoji 字符

### 8. 测试规范

- 禁止在测试用例中写生产数据库，只允许读
- 测试文件放在 `backend/tests/` 目录

### 9. 除了热加载或者初始化的场景，所有的 import 导入必须遵循 PEP 规范，放置在模块顶部

---

## 核心领域模型

**重要：所有的业务数据模型必须在 app/models 文件夹当中！工具调用的数据模型要放到自己的 tools 文件当中，fast api 的数据传输模型应该只在路由中**

### 数据模型文件位置

- `backend/app/models/schemas.py` - 面经题目相关模型
- `backend/app/models/enums.py` - 枚举定义
- `backend/app/models/interview_session.py` - 模拟面试相关模型

### 枚举类

- `QuestionType`: `knowledge`（客观题）、`project`（项目深挖题）、`behavioral`（行为题）、`scenario`（场景题）、`algorithm`（算法题）
- `MasteryLevel`: `LEVEL_0`（未掌握）、`LEVEL_1`（熟悉）、`LEVEL_2`（已掌握）

### 核心数据模型

- **ExtractedInterview**: 包含 `company`, `position` 和 `questions` 列表
- **QuestionItem**: 必须包含 `question_id` (MD5哈希)、`question_text`、`question_type`、`company`, `position`
- **InterviewSession**: 模拟面试会话
- **InterviewReport**: 面试报告

---

## 核心架构设计模式

在实现业务流水线时，请贯彻以下设计哲学：

### 1. 分类熔断机制

在 Vision Extractor 提取阶段，必须由 LLM 对题目类型打标。仅 `knowledge` 类型触发 MQ 异步答案生成；`project` 和 `behavioral` 类型触发熔断（仅存题目不存答案），防止大模型幻觉与 Token 浪费。

### 2. 上下文拼接 Embedding

计算向量时，不要只嵌入题目。必须拼接上下文：`"公司：字节跳动 | 岗位：Agent应用开发 | 题目：qlora怎么优化显存？"`

### 3. 混合检索底座

Qdrant 写入时必须携带 Payload（包含 `company`, `position`, `mastery_level`, `question_type`）。在检索时，优先使用 Payload 建立硬过滤条件（Pre-filtering），再进行稠密向量计算。

### 4. 主键幂等性

所有的 `question_id` 强制使用 `MD5("公司名" + "题目文本")` 生成。无论是第一次入库还是后续更新，都必须利用该 MD5 进行 Qdrant 的 **Upsert** 操作，保证数据一致性。

### 5. 主从 Agent 解耦

主系统不负责繁重的答疑。它仅负责将包装好的 Context 发送至 RabbitMQ。后台 Worker 消费消息并唤醒 `Answer_Specialist_Agent`（挂载 Web Search Tool）去查资料生成最新答案。

### 6. 状态管理

- Chat Agent 使用 LangGraph Checkpointer + PostgreSQL 实现状态持久化
- 无需手动维护会话状态，通过 `conversation_id` (thread_id) 自动恢复

### 7. 流式输出

- 后端使用 `StreamingResponse` + SSE 实现流式输出
- 前端使用 `fetch` + `ReadableStream` 接收流式数据
- 注意：前端回调函数中避免依赖 React state，应使用局部变量

---

## 项目目录结构

```text
Offer-Catcher/
├── backend/                        # 后端服务 (Python)
│   ├── app/
│   │   ├── agents/                 # 智能体层
│   │   │   ├── graph/              # LangGraph 工作流
│   │   │   │   ├── state.py        # AgentState 定义
│   │   │   │   ├── nodes.py        # 节点实现
│   │   │   │   ├── edges.py        # 条件边
│   │   │   │   └── workflow.py     # 工作流组装
│   │   │   ├── prompts/            # Prompt 模板 (.md 文件)
│   │   │   ├── skills/             # 技能模块
│   │   │   ├── chat_agent.py       # AI 对话 Agent
│   │   │   ├── interview_agent.py  # 模拟面试 Agent
│   │   │   ├── vision_extractor.py # 面经提取 Agent
│   │   │   ├── answer_specialist.py# 答案生成 Agent
│   │   │   └── scorer.py           # 评分 Agent
│   │   │
│   │   ├── api/                    # FastAPI 路由
│   │   │   └── routes/
│   │   │       ├── chat.py         # 对话 API
│   │   │       └── interview.py    # 面试 API
│   │   │
│   │   ├── tools/                  # Agent 工具
│   │   │   ├── embedding_tool.py   # 向量嵌入
│   │   │   ├── search_question_tool.py
│   │   │   ├── web_search_tool.py
│   │   │   ├── memory_tools.py
│   │   │   └── ...
│   │   │
│   │   ├── pipelines/              # 业务流水线
│   │   │   ├── ingestion.py        # 入库流程
│   │   │   └── retrieval.py        # 检索流程
│   │   │
│   │   ├── db/                     # 数据库层
│   │   │   ├── qdrant_client.py    # 向量数据库
│   │   │   ├── postgres_client.py  # PostgreSQL
│   │   │   ├── graph_client.py     # 图数据库
│   │   │   ├── redis_client.py     # Redis 缓存
│   │   │   └── checkpointer.py     # LangGraph Checkpointer
│   │   │
│   │   ├── mq/                     # 消息队列层
│   │   │   ├── producer.py
│   │   │   ├── consumer.py
│   │   │   └── message_helper.py
│   │   │
│   │   ├── memory/                 # 长期记忆
│   │   │
│   │   ├── models/                 # 数据模型
│   │   │   ├── schemas.py
│   │   │   ├── enums.py
│   │   │   └── interview_session.py
│   │   │
│   │   ├── llm/                    # LLM 工厂
│   │   │
│   │   ├── config/                 # 配置
│   │   │
│   │   ├── services/               # 业务服务
│   │   │   ├── cache_service.py
│   │   │   └── xfyun_asr.py        # 讯飞语音识别
│   │   │
│   │   └── utils/                  # 工具
│   │       ├── logger.py
│   │       ├── cache.py
│   │       └── ...
│   │
│   ├── workers/                    # 后台进程
│   │   ├── answer_worker.py        # 答案生成
│   │   ├── clustering_worker.py    # 聚类
│   │   ├── extract_worker.py       # 面经提取
│   │   └── reembed_worker.py       # 向量重建
│   │
│   ├── tests/                      # 测试用例
│   │
│   ├── main.py                     # FastAPI 入口
│   └── pyproject.toml
│
├── frontend/                       # 前端 (Next.js)
│   ├── src/
│   │   ├── app/                    # App Router 页面
│   │   │   ├── chat/               # AI 对话
│   │   │   ├── interview/          # 模拟面试
│   │   │   ├── practice/           # 刷题练习
│   │   │   ├── questions/          # 题库管理
│   │   │   ├── extract/            # 面经导入
│   │   │   └── dashboard/          # 数据看板
│   │   │
│   │   ├── components/             # React 组件
│   │   │   ├── MainLayout.tsx
│   │   │   └── VoiceInput.tsx
│   │   │
│   │   ├── lib/                    # API 客户端
│   │   │   └── api.ts
│   │   │
│   │   └── types/                  # TypeScript 类型
│   │       └── index.ts
│   │
│   └── package.json
│
└── docker-compose.yml
```

---

## 开发与测试命令

### 环境管理

本项目使用 `uv` 作为 Python 包管理工具。

### 后端开发

```bash
cd backend

# 安装依赖
uv sync

# 启动 API 服务
uv run python -m app.main

# 或使用 uvicorn (开发模式)
uv run uvicorn app.main:app --reload

# 启动 Worker
PYTHONPATH=. uv run python workers/answer_worker.py

# 运行测试
uv run pytest tests/ -v
```

### 前端开发

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建
npm run build
```

---

## API 设计规范

### 流式响应

使用 Server-Sent Events (SSE) 实现流式输出：

```python
# backend/app/api/routes/chat.py
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

### 请求/响应模型

所有 API 必须定义 Pydantic 模型：

```python
class ChatRequest(BaseModel):
    message: str
    conversation_id: str
```

---

## 前端开发规范

### 目录结构

- `src/app/` - Next.js App Router 页面
- `src/components/` - 共享 React 组件
- `src/lib/` - API 客户端和工具函数
- `src/types/` - TypeScript 类型定义

### 流式数据处理

```typescript
const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split("\n");
  buffer = lines.pop() || "";

  for (const line of lines) {
    if (line.startsWith("data: ")) {
      const data = JSON.parse(line.slice(6));
      // 处理数据
    }
  }
}
```

**注意**: 在 fetch 回调中更新状态时，使用局部变量而非 React state，避免闭包问题。

### UI 组件

使用 Ant Design 组件 + Tailwind CSS 样式。

---

## 重要提醒

1. 后端代码统一放在 `backend/app/` 目录
2. 前端代码统一放在 `frontend/src/` 目录
3. 测试代码放在 `backend/tests/` 目录
4. Worker 进程放在 `backend/workers/` 目录
5. Prompt 模板放在 `backend/app/agents/prompts/` 目录