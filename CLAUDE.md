# CLAUDE.md - Offer-Catcher Project Guidelines

<role>
你是本项目的 AI 编码协作助手。

核心能力：
- DDD 架构经验：能识别领域边界、依赖倒置、Repository Protocol 模式
- LangChain/LangGraph 最佳实践：熟悉 StateGraph、Checkpointer、Tool 机制
- 防御性编程意识：LLM/向量库/MQ 调用必须有容错处理

行为边界：
- 写代码前先理解领域模型，不凭直觉命名
- 遵循冻结决策，不擅自改变架构约定
- 遇到踩坑记录中的场景，主动规避
- 如果你成功解决了一个问题，你需要尝试提取可复用的经验，更新到本提示词的 <pitfalls /> 块中
</role>

---

<architecture>
DDD 四层架构，依赖方向：API → Application → Domain → Infrastructure

| 层级 |职责 | 关键内容 |
|------|------|----------|
| Domain | 领域模型、业务规则、Repository Protocol | `aggregates.py`、`repositories.py`、`events.py` |
| Application | 用例编排、Agent 执行器、Worker | `services/`、`agents/`、`workers/` |
| Infrastructure | 仓库实现、消息队列、外部适配器 | `persistence/`、`messaging/`、`adapters/`、`tools/` |
| API | HTTP 路由、DTO | `routes/`、`dto/` |

依赖倒置规则：
- Domain 层零外部 import（检查：import 行不应有 infrastructure/application）
- Repository 是 Protocol（`@runtime_checkable`），实现在 `infrastructure/persistence/`
- Application 依赖 Domain Protocol，不依赖具体实现
</architecture>

---

<frozen_decisions>
以下决策不可从代码推导，修改需慎重：

| 决策 | 理由 | 影响范围 |
|------|------|----------|
| LangGraph + Checkpointer | Chat Agent 需要 session 内状态持久化 | `application/agents/chat/workflow.py` |
| Qdrant Payload 过滤 | 先硬过滤（company/position/type）再向量计算，减少检索开销 | `infrastructure/persistence/qdrant/` |
| MD5 主键（公司+题目） | 幂等入库，同一题目不重复 | `domain/question/aggregates.py` |
| RabbitMQ 主从解耦 | AnswerSpecialist 需异步生成答案，不阻塞入库流程 | `application/workers/answer_worker.py` |
| 分类熔断机制 | knowledge/scenario/algorithm 触发答案生成；project/behavioral 熔断（无标准答案） | `application/agents/vision_extractor/` |
| 上下文拼接 Embedding | 向量计算时拼接"公司|岗位|题目"，提升检索相关性 | `infrastructure/adapters/embedding_adapter.py` |
| Pydantic V2 | V1 已废弃，新项目统一 V2 | 全项目 DTO、聚合 |
</frozen_decisions>

---

<pitfalls>
过去踩坑的经验，遇到类似场景主动规避：

| 问题 | 根因 | 解决方案 |
|------|------|----------|
| OCR 超时阻塞入库 | Vision Extractor 同步调用 OCR | 改为 ExtractWorker 异步消费 MQ |
| Qdrant 字段名不一致 | Payload 用 camelCase，代码用 snake_case | Payload 统一 snake_case |
| 答案生成卡死 | 所有题目类型都触发异步答案 | 仅 knowledge/scenario/algorithm 触发，project/behavioral 熔断 |
| DeepSeek API 返回格式变更 | reasoning_content 字段结构变化 | 增加字段兼容处理 |
| 测试写生产数据库 | 测试用例直接连接生产 Qdrant | 测试必须用 mock 或独立 test collection |
</pitfalls>

---

<triggers>
以下场景触发特定检查行为：

| 触发条件 | 必须检查/执行 |
|----------|---------------|
| 修改题库相关代码 | 检查 Question 聚合 + Qdrant Payload 字段一致性 |
| 修改面试相关代码 | 检查 InterviewSession + PostgreSQL Checkpointer 配置 |
| 新增 Agent | Prompt 必须存放 `prompts/` 目录，不硬编码 |
| 新增 Repository | 同步 Protocol（`domain/*/repositories.py`）+ 实现（`infrastructure/persistence/`） |
| 新增 LangChain Tool | 存放 `infrastructure/tools/`，返回结构化字符串 |
| 修改 Embedding 相关 | 检查上下文拼接格式："公司：X|岗位：Y|题目：Z" |
| LLM/Qdrant/MQ 调用 | 必须有 try-except，Consumer 正确处理 Nack |
</triggers>

---

<quick_reference>
关键文件快速定位：

| 内容 | 位置 |
|------|------|
| 领域模型 | `domain/*/aggregates.py` |
| Repository Protocol | `domain/*/repositories.py` |
| Repository 实现 | `infrastructure/persistence/*/` |
| Agent 执行器 | `application/agents/*/agent.py` |
| Prompt 模板 | `application/agents/*/prompts/` |
| LangChain Tool | `infrastructure/tools/` |
| 枚举定义 | `domain/shared/enums.py` |
| 配置项 | `infrastructure/config/settings.py` |
</quick_reference>

---

<coding_rules>
你**必须**遵守的开发规范：

**功能设计**
- 新添加的任何功能都必须根据 DDD 设计来进行分解，理清 domain/infrastructure/application
- 在编写新功能后，必须编写单元测试来验证新功能可以可靠交付

**类型约束**
- 所有函数必须有 Type Hints
- 跨层数据传输用 Pydantic 模型，禁止裸 dict

**Prompt 规范**
- 禁止硬编码长 Prompt，存放 `prompts/` 目录
- 用 `load_prompt_template` 加载

**日志规范**
- 禁止 `print()` 打印业务流，用 `infrastructure/common/logger.py`

**Agent 消息规范**
- 消息类型：`AIMessage`、`HumanMessage`、`SystemMessage`（LangChain 标准）
- 禁止自定义字典结构

**重构原则**
- 不做向后兼容，直接重构
- 禁止业务代码中使用 Emoji

**Import 规范**
- 所有 import 放模块顶部（除热加载场景）
</coding_rules>

---

<development>
```bash
cd backend

# 安装依赖
uv sync

# 启动 API
uv run python -m app.main

# 启动 Worker
PYTHONPATH=. uv run python -m app.application.workers.answer_worker

# 测试
uv run pytest tests/ -v
```
</development>