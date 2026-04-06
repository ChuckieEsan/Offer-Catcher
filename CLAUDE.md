
# CLAUDE.md - Offer-Catcher Project Guidelines

本文档为 Claude Code (claude.ai/code) 在本项目中的编码与架构决策提供核心指导。请在执行任何代码生成或重构前仔细阅读。

## 🤖 AI 编码行为准则 (AI Coding Directives)

作为本项目的资深 Python 架构师，你在生成代码时必须严格遵守以下规范：

1. **强类型约束**：所有函数必须包含完整的 Type Hints（类型提示）。数据传输必须且只能通过 `pydantic` (V2版本) 模型，严禁使用裸字典 (`dict`) 在不同层之间传递核心业务数据。
2. **Prompt 外置原则**：严禁将长篇 Prompt 字符串硬编码在 Python 文件中。所有的系统提示词必须作为单独的 `.md` 或 `.txt` 文件存放在 `app/prompts/` 目录下，在代码中按需读取。
3. **日志优先**：禁止使用标准的 `print()` 函数打印业务流。请使用 `app/utils/logger.py`（或 `logging` 模块）进行日志记录，以便后续在生产环境和排查 MQ 消费时追踪。
4. **防御性编程**：在调用 LLM API、Qdrant 数据库和 RabbitMQ 时，必须包含 `try-except` 块，并在合适的地方（如 RabbitMQ Consumer）正确处理 `Nack` 或失败重试逻辑。
5. **小步快跑（当前阶段限制）**：本项目采用敏捷开发。**目前已完成 Phase 1（核心数据流与异步答题阶段）**，请聚焦于 Phase 2 内容（图数据库、打分 Agent），不要提前实现 Phase 3 的内容（如微信接入、Redis 缓存）。
6. **不要在业务代码中使用 Emoji 字符**。在开发 streamlit 前端时，可以适当使用 Emoji。
7. **软件开发设计应当符合 Langchain/LangGraph 的最佳实践**，你需要尽可能少的重复造轮子，尽可能复用 Langchain 已有的组件
8. **如果发生重构，不要进行向后兼容，你需要直接重构**
9. **禁止在测试用例中写生产数据库，只允许读**
10. **Agent 的消息必须是 Langchain 的消息，如 AIMessage, HumanMessage, BaseMessage**，不允许自定义字典结构

---

## 🏗️ 项目架构树 (Clean Architecture)

```text
offer_catcher/
├── app/
│   ├── agents/          # AI 智能体（router, vision, answer_worker, scorer）
│   ├── tools/           # 智能体工具（search_web, search_vector）
│   ├── pipelines/       # 业务流水线编排（ingestion, retrieval）
│   ├── db/              # 基础设施层（qdrant_client）
│   ├── mq/              # 消息队列层（producer, consumer, thread_pool_consumer, message_helper）
│   ├── models/          # 领域数据模型（schemas.py, enums.py）
│   ├── prompts/         # Prompt 模板中心（Markdown）
│   ├── config/          # 全局配置管理（settings.py）
│   └── utils/           # 通用工具（hasher.py, logger.py, retry.py, circuit_breaker.py）
├── workers/             # 后台常驻进程（async_answer_worker.py）
└── gateways/            # 外部接入层（前端为 cli_chat.py）
```

---

## 🧩 核心领域模型 (Domain Models)

严格遵循定义在 `app/models/schemas.py` 和 `app/models/enums.py` 中的契约：

- **枚举类**:
  - `QuestionType`: `knowledge`（客观题）、`project`（项目深挖题）、`behavioral`（行为题）、`scenario`（场景题）
  - `MasteryLevel`: `0`（未掌握）、`1`（熟悉）、`2`（已掌握）
- **核心数据总线 (ExtractedInterview)**: 包含 `company`, `position` 和 `questions` 列表。
- **单题粒度 (QuestionItem)**: 必须包含 `question_id` (MD5哈希)、`question_text`、`question_type`、`requires_async_answer`、`mastery_level`。

---

## 🧠 核心架构与设计模式 (Core Design Patterns)

在实现业务流水线时，请贯彻以下设计哲学：

1. **分类熔断机制 (Classification & Circuit Breaker)**：在 Vision Extractor 提取阶段，必须由 LLM 对题目类型打标。仅 `knowledge` 类型触发 MQ 异步答案生成；`project` 和 `behavioral` 类型触发熔断（仅存题目不存答案），防止大模型幻觉与 Token 浪费。
2. **上下文拼接 Embedding (Context Enrichment)**：计算向量时，不要只嵌入题目。必须拼接上下文：`"公司：字节跳动 | 岗位：Agent应用开发 | 题目：qlora怎么优化显存？"`。
3. **混合检索底座 (Hybrid RAG via Qdrant)**：Qdrant 写入时必须携带 Payload（包含 `company`, `position`, `mastery_level`, `question_type`）。在检索时，优先使用 Payload 建立硬过滤条件（Pre-filtering），再进行稠密向量计算。
4. **主键幂等性 (Deterministic ID)**：所有的 `question_id` 强制使用 `MD5("公司名" + "题目文本")` 生成。无论是第一次入库还是后续更新 `mastery_level` 或写入异步生成的答案，都必须利用该 MD5 进行 Qdrant 的 **Upsert** 操作，保证数据一致性。
5. **主从 Agent 解耦 (Supervisor-Worker via MQ)**：主系统不负责繁重的答疑。它仅负责将包装好的 Context 发送至 RabbitMQ。后台 Worker 消费消息并唤醒 `Answer_Specialist_Agent`（挂载 Web Search Tool）去查资料生成最新答案。

---

## 🛠️ 开发与测试命令 (Dev Commands)

本项目使用的环境是 uv，所以你在执行 Python 代码时，可以使用 `uv run [code_name.py]`，如果要安装某个包，可以使用 `uv add [package_name]`