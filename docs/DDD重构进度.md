# DDD 重构进度跟踪

> 本文档用于跟踪 Offer-Catcher 项目向 DDD 架构重构的进度。
> 创建日期：2026-04-16
> 基于：[DDD重构设计.md](DDD重构设计.md)

---

## 重构概览

### 当前状态

| 层级 | 状态 | 说明 |
|------|------|------|
| `domain/shared/` | **已完成** | 枚举和异常定义已完成，测试通过 |
| `domain/question/` | **已完成** | Question、Cluster、ExtractTask 聚合 + Repository Protocol + 领域事件 |
| `domain/interview/` | 待开始 | 面试领域待定义 |
| `domain/chat/` | 待开始 | 对话领域待定义 |
| `domain/memory/` | 待开始 | 记忆领域待定义 |
| `infrastructure/common/` | **已完成** | logger、cache、retry、circuit_breaker、prompt、image 已迁移 |
| `infrastructure/adapters/` | **已完成** | embedding、reranker、web_search、ocr、asr、llm 已迁移 |
| `infrastructure/persistence/` | **已完成** | Qdrant、PostgreSQL、Redis、Neo4j 客户端已迁移 |
| `infrastructure/messaging/` | **已完成** | MQ 生产者、消费者、线程池消费者已迁移 |
| `infrastructure/config/` | **已完成** | settings 已迁移 |
| `application/` | 骨架已建立 | QuestionService 已完成，其他待实现 |
| `api/dto/` | **已完成** | QuestionDTO 已完成 |
| `api/routes/` | **已完成** | questions_v2 已完成 |
| `models/` | 向后兼容 | 已迁移到 `domain/`，保留转发导入 |
| `agents/` | 旧代码完整 | Workflow 迁移到 `domain/*/workflow/`，执行器迁移到 `application/services/` |
| `db/` | 向后兼容 | 已迁移到 `infrastructure/persistence/`，保留转发导入 |
| `pipelines/` | 旧代码完整 | 需迁移到 `application/services/` |
| `tools/` | 部分迁移 | embedding、reranker、web_search 已使用 adapter |
| `mq/` | 向后兼容 | 已迁移到 `infrastructure/messaging/`，保留转发导入 |
| `services/` | 部分迁移 | xfyun_asr 已迁移到 adapters |
| `utils/` | 向后兼容 | 大部分已迁移，保留转发导入 |

---

## 阶段划分与进度

### 阶段 1：基础设施层基础模块（最低风险） ✅ 已完成（部分）

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 1.1 | logger 迁移 | `infrastructure/common/logger.py` | `utils/logger.py` | **已完成** | 2026-04-17 | 纯工具类，无依赖，utils/logger.py 改为转发 |
| 1.2 | cache 装饰器迁移 | `infrastructure/common/cache.py` | `utils/cache.py` | **已完成** | 2026-04-17 | `@singleton` 装饰器，utils/cache.py 改为转发 |
| 1.3 | circuit_breaker 迁移 | `infrastructure/common/circuit_breaker.py` | `utils/circuit_breaker.py` | **已完成** | 2026-04-17 | 熔断器模式，含 CircuitOpenState 转发 |
| 1.4 | retry 迁移 | `infrastructure/common/retry.py` | `utils/retry.py` | **已完成** | 2026-04-17 | 重试机制，utils/retry.py 改为转发 |
| 1.5 | telemetry 迁移 | `infrastructure/common/telemetry.py` | `utils/telemetry.py` | 待开始 | - | 遗测追踪 |
| 1.6 | prompt_loader 迁移 | `infrastructure/common/prompt.py` | `utils/prompt.py` | **已完成** | 2026-04-17 | 提示词加载工具，utils/prompt.py 改为转发 |
| 1.7 | image 迁移 | `infrastructure/common/image.py` | `utils/image.py` | **已完成** | 2026-04-17 | 图片处理工具，utils/image.py 改为转发 |
| 1.8 | hasher 迁移 | `domain/question/utils.py` | `utils/hasher.py` | **已完成** | 2026-04-17 | **领域逻辑**，infra/common/hasher.py 已删除 |

**阶段 1 检查点**：
- [x] logger、cache、retry、circuit_breaker、prompt、image 迁移完成
- [x] hasher 已正确迁移到 domain/question/utils.py
- [x] utils/*.py 改为导入转发，保持向后兼容
- [ ] telemetry 迁移待完成

---

### 阶段 2：外部服务适配器 ✅ 已完成

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 2.1 | embedding_adapter | `infrastructure/adapters/embedding_adapter.py` | `tools/embedding_tool.py` | **已完成** | 2026-04-16 | 向量嵌入适配，tools/embedding_tool.py 改为使用 adapter |
| 2.2 | reranker_adapter | `infrastructure/adapters/reranker_adapter.py` | `tools/reranker_tool.py` | **已完成** | 2026-04-16 | 重排序适配，tools/reranker_tool.py 改为使用 adapter |
| 2.3 | web_search_adapter | `infrastructure/adapters/web_search_adapter.py` | `tools/web_search_tool.py` | **已完成** | 2026-04-16 | Web搜索适配，tools/web_search_tool.py 改为使用 adapter |
| 2.4 | ocr_adapter | `infrastructure/adapters/ocr_adapter.py` | `utils/ocr.py` | **已完成** | 2026-04-16 | OCR服务适配，utils/ocr.py 已删除 |
| 2.5 | image 工具迁移 | `infrastructure/common/image.py` | `utils/image.py` | **已完成** | 2026-04-17 | 图片处理为通用工具，非外部服务 |
| 2.6 | asr_adapter | `infrastructure/adapters/asr_adapter.py` | `services/xfyun_asr.py` | **已完成** | 2026-04-16 | 讯飞语音识别，services/xfyun_asr.py 已删除 |
| 2.7 | llm_adapter | `infrastructure/adapters/llm_adapter.py` | `llm/` | **已完成** | 2026-04-16 | LLM调用统一封装，app/llm/__init__.py 改为转发 |

**阶段 2 检查点**：
- [x] 所有外部服务调用统一封装为 Adapter
- [x] Adapter 支持依赖注入，便于测试 Mock
- [x] 旧工具文件改为使用 adapter 或删除

---

### 阶段 3：领域层共享内核 ✅ 已完成

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 3.1 | 共享枚举定义 | `domain/shared/enums.py` | `models/question.py` | **已完成** | 2026-04-16 | QuestionType, MasteryLevel, DifficultyLevel 等，含 `requires_async_answer()` 方法 |
| 3.2 | 领域异常定义 | `domain/shared/exceptions.py` | - | **已完成** | 2026-04-16 | DomainException + 各领域异常层级 |
| 3.3 | 共享提示词模板 | `domain/shared/prompts/base.md` | - | 待开始 | - | 基础模板（可选，暂不需要） |

**阶段 3 检查点**：
- [x] 共享枚举完成，所有领域可引用
- [x] 领域异常层级建立
- [x] 类型检查正常
- [x] 单元测试通过（15 + 24 = 39 个测试）

---

### 阶段 4：题库领域（核心领域，被其他领域依赖） ✅ 已完成

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 4.1 | Question 聚合定义 | `domain/question/aggregates.py` | `models/question.py` | **已完成** | 2026-04-16 | 聚合根 Question，含 create()、update_answer()、add_cluster() 等 |
| 4.2 | Cluster 聚合定义 | `domain/question/aggregates.py` | - | **已完成** | 2026-04-16 | 聚合根 Cluster，含 add_question()、remove_question() |
| 4.3 | ExtractTask 聚合定义 | `domain/question/aggregates.py` | `models/extract.py` | **已完成** | 2026-04-16 | 聚合根 ExtractTask，含状态流转方法 |
| 4.4 | question_id 生成逻辑 | `domain/question/utils.py` | `utils/hasher.py` | **已完成** | 2026-04-16 | **领域逻辑**，幂等性保证 |
| 4.5 | Repository Protocol 定义 | `domain/question/repositories.py` | - | **已完成** | 2026-04-16 | QuestionRepository、ClusterRepository、ExtractTaskRepository Protocol |
| 4.6 | 领域事件定义 | `domain/question/events.py` | - | **已完成** | 2026-04-16 | QuestionCreated, AnswerGenerated, ClusterAssigned 等 7 个事件 |
| 4.7 | 题库领域服务 | `domain/question/services.py` | - | 跳过 | - | 领域逻辑暂无，服务在应用层 |
| 4.8 | 领域提示词迁移 | `domain/question/prompts/` | `agents/prompts/` | 待开始 | - | extractor.md, answer.md 等 |
| 4.9 | Workflow 定义 | `domain/question/workflow/` | - | 跳过 | - | 题库领域暂不需要 Workflow |

**阶段 4 检查点**：
- [x] Question 聚合完成，包含 `create()`, `update_answer()` 等方法
- [x] Repository Protocol 定义完成（@runtime_checkable）
- [x] 领域事件定义完成
- [x] 单元测试通过（89 个测试）

---

### 阶段 5：题库仓库实现（基础设施层） ✅ 已完成

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 5.1 | Qdrant 客户端迁移 | `infrastructure/persistence/qdrant/client.py` | `db/qdrant_client.py` | **已完成** | 2026-04-16 | 新版客户端，支持依赖注入 |
| 5.2 | QuestionRepository 实现 | `infrastructure/persistence/qdrant/question_repository.py` | - | **已完成** | 2026-04-16 | 实现 Protocol，含 embedding 计算 |
| 5.3 | ClusterRepository 实现 | `infrastructure/persistence/qdrant/cluster_repository.py` | - | **已完成** | 2026-04-17 | 实现 Protocol，使用 entity_type 区分 |
| 5.4 | ExtractTaskRepository 实现 | `infrastructure/persistence/postgres/extract_task_repository.py` | `db/postgres_client.py` | **已完成** | 2026-04-17 | PostgreSQL 实现，复用现有表 |
| 5.5 | EmbeddingAdapter 实现 | `infrastructure/adapters/embedding_adapter.py` | `tools/embedding_tool.py` | **已完成** | 2026-04-16 | 向量嵌入适配器 |
| 5.6 | 集成测试 | - | - | 待开始 | - | 仓库实现测试 |

**阶段 5 检查点**：
- [x] Qdrant 客户端迁移完成
- [x] QuestionRepository 实现完成，可 CRUD Question
- [x] ClusterRepository 实现完成
- [x] ExtractTaskRepository 实现完成
- [ ] 与旧代码功能对比测试通过
- [ ] 性能无明显下降

---

### 阶段 6：模拟面试领域

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 6.1 | InterviewSession 聚合 | `domain/interview/aggregates.py` | `models/interview_session.py` | 待开始 | - | 面试会话聚合根 |
| 6.2 | InterviewQuestionItem 实体 | `domain/interview/aggregates.py` | `models/interview_session.py` | 待开始 | - | 聚合内实体 |
| 6.3 | Repository Protocol | `domain/interview/repositories.py` | - | 待开始 | - | InterviewSessionRepository |
| 6.4 | 领域事件 | `domain/interview/events.py` | - | 待开始 | - | InterviewStarted, InterviewEnded |
| 6.5 | 领域服务（评分） | `domain/interview/services.py` | `agents/scorer.py` | 待开始 | - | ScorerService 领域逻辑 |
| 6.6 | 领域提示词 | `domain/interview/prompts/` | `agents/prompts/` | 待开始 | - | scorer.md, interview.md |
| 6.7 | Workflow 定义 | `domain/interview/workflow/` | `agents/graph/` | 待开始 | - | 面试 Agent Workflow |

**阶段 6 检查点**：
- [ ] InterviewSession 聚合完成，包含题目快照机制
- [ ] Workflow 定义完成（State, Nodes, Graph）

---

### 阶段 7：面试仓库实现 ✅ 已完成（部分）

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 7.1 | PostgreSQL 客户端迁移 | `infrastructure/persistence/postgres/client.py` | `db/postgres_client.py` | **已完成** | 2026-04-16 | 关系数据库客户端 |
| 7.2 | Redis 客户端迁移 | `infrastructure/persistence/redis/client.py` | `db/redis_client.py` | **已完成** | 2026-04-16 | Redis 短期记忆缓存 |
| 7.3 | Neo4j 客户端迁移 | `infrastructure/persistence/neo4j/client.py` | `db/graph_client.py` | **已完成** | 2026-04-16 | 图数据库（考点关系） |
| 7.4 | Checkpointer 迁移 | `infrastructure/persistence/postgres/checkpointer.py` | `db/checkpointer.py` | **已完成** | 2026-04-16 | LangGraph 状态持久化 |
| 7.5 | InterviewSessionRepository 实现 | `infrastructure/persistence/postgres/interview_session_repository.py` | `db/postgres_client.py` | 待开始 | - | 实现 Protocol |
| 7.6 | 集成测试 | - | - | 待开始 | - | 仓库实现测试 |

**阶段 7 检查点**：
- [x] PostgreSQL、Redis、Neo4j 客户端迁移完成
- [x] Checkpointer 迁移完成
- [x] db/__init__.py 改为导入转发

### 阶段 8：智能对话领域

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 8.1 | Conversation 聚合 | `domain/chat/aggregates.py` | `models/chat_session.py` | 待开始 | - | 对话聚合根 |
| 8.2 | Message 实体 | `domain/chat/aggregates.py` | `models/chat_session.py` | 待开始 | - | 聚合内实体 |
| 8.3 | Repository Protocol | `domain/chat/repositories.py` | - | 待开始 | - | ConversationRepository |
| 8.4 | 领域事件 | `domain/chat/events.py` | - | 待开始 | - | ConversationEnded |
| 8.5 | 领域工具 | `domain/chat/tools.py` | `tools/search_question_tool.py` | 待开始 | - | 题库检索、Web搜索等 |
| 8.6 | 领域提示词 | `domain/chat/prompts/` | `agents/prompts/` | 待开始 | - | chat.md, title.md |
| 8.7 | Workflow 定义 | `domain/chat/workflow/` | `agents/graph/` | 待开始 | - | 对话 Agent Workflow |

---

### 阶段 9：对话仓库实现

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 9.1 | ConversationRepository 实现 | `infrastructure/persistence/postgres/conversation_repository.py` | `db/postgres_client.py` | 待开始 | - | 实现 Protocol |
| 9.2 | 集成测试 | - | - | 待开始 | - | 仓库实现测试 |

---

### 阶段 10：记忆领域

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 10.1 | Memory 聚合 | `domain/memory/aggregates.py` | - | 待开始 | - | 记忆聚合根 |
| 10.2 | Repository Protocol | `domain/memory/repositories.py` | - | 待开始 | - | MemoryRepository |
| 10.3 | 领域事件 | `domain/memory/events.py` | - | 待开始 | - | MemoryCreated |
| 10.4 | 领域提示词 | `domain/memory/prompts/` | `memory/agent/prompts/` | 待开始 | - | memory_agent.md |

---

### 阶段 11：记忆仓库实现

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 11.1 | MemoryRepository 实现 | `infrastructure/persistence/postgres/memory_repository.py` | `db/postgres_client.py` | 待开始 | - | 实现 Protocol |
| 11.2 | MemoryInjectionService 实现 | `infrastructure/services/memory_injection_service.py` | `memory/io.py` | 待开始 | - | 记忆注入服务 |

---

### 阶段 12：消息队列迁移 ✅ 已完成

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 12.1 | Producer 迁移 | `infrastructure/messaging/producer.py` | `mq/producer.py` | **已完成** | 2026-04-16 | MQ 生产者，mq/__init__.py 改为转发 |
| 12.2 | Consumer 迁移 | `infrastructure/messaging/consumer.py` | `mq/consumer.py` | **已完成** | 2026-04-16 | MQ 消费者，含熔断保护 |
| 12.3 | ThreadPoolConsumer 迁移 | `infrastructure/messaging/thread_pool_consumer.py` | `mq/thread_pool_consumer.py` | **已完成** | 2026-04-16 | 线程池消费 |
| 12.4 | MessageHelper 迁移 | `infrastructure/messaging/message_helper.py` | `mq/message_helper.py` | **已完成** | 2026-04-16 | 重试/DLQ 工具 |
| 12.5 | EventBus 实现 | `infrastructure/messaging/event_bus.py` | - | 待开始 | - | 事件总线（可选） |

**阶段 12 检查点**：
- [x] MQ 生产者、消费者、线程池消费者迁移完成
- [x] mq/__init__.py 改为导入转发
- [x] 消费者支持熔断保护

### 阶段 13：应用层事件机制

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 13.1 | EventPublisher 定义 | `application/events/publishers/` | - | 待开始 | - | 各领域事件发布器 |
| 13.2 | EventHandler 定义 | `application/events/handlers/` | - | 待开始 | - | 各领域事件处理器 |
| 13.3 | EventBus Protocol | `application/events/event_bus.py` | - | 待开始 | - | 事件总线接口 |

---

### 阶段 14：应用服务迁移 🔄 进行中

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 14.1 | IngestionApplicationService | `application/services/ingestion_service.py` | `pipelines/ingestion.py` | **已完成** | 2026-04-17 | 入库用例编排，含分类熔断和答案复用 |
| 14.2 | RetrievalApplicationService | `application/services/retrieval_service.py` | `pipelines/retrieval.py` | 待开始 | - | 检索用例编排 |
| 14.3 | ChatApplicationService | `application/services/chat_service.py` | `agents/chat_agent.py` | 待开始 | - | 对话 Agent 执行器 |
| 14.4 | InterviewApplicationService | `application/services/interview_service.py` | `agents/interview_agent.py` | 待开始 | - | 面试 Agent 执行器 |
| 14.5 | MemoryApplicationService | `application/services/memory_service.py` | `memory/agent/` | 待开始 | - | 记忆用例编排 |
| 14.6 | QuestionApplicationService | `application/services/question_service.py` | - | **已完成** | 2026-04-16 | 题库 CRUD 用例编排 |

**阶段 14 检查点**：
- [x] QuestionApplicationService 完成，支持 CRUD 操作
- [x] IngestionApplicationService 完成，含分类熔断和答案复用
- [x] pipelines/ingestion.py 改为向后兼容转发层

---

### 阶段 15：Worker 迁移

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 15.1 | AnswerWorker | `application/workers/answer_worker.py` | `workers/answer_worker.py` | 待开始 | - | 答案生成 Worker |
| 15.2 | ExtractWorker | `application/workers/extract_worker.py` | `workers/extract_worker.py` | 待开始 | - | 面经提取 Worker |
| 15.3 | ClusteringWorker | `application/workers/clustering_worker.py` | `workers/clustering_worker.py` | 待开始 | - | 聚类 Worker |
| 15.4 | ReembedWorker | `application/workers/reembed_worker.py` | `workers/reembed_worker.py` | 待开始 | - | 向量重建 Worker |

---

### 阶段 16：启动预热迁移

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 16.1 | Warmup | `application/startup/warmup.py` | `utils/warmup.py` | 待开始 | - | 启动预热逻辑 |

---

### 阶段 17：API DTO 定义 🔄 进行中

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 17.1 | ChatDTO | `api/dto/chat_dto.py` | `models/chat_session.py` | 待开始 | - | 对话请求/响应 |
| 17.2 | InterviewDTO | `api/dto/interview_dto.py` | `models/interview_session.py` | 待开始 | - | 面试请求/响应 |
| 17.3 | QuestionDTO | `api/dto/question_dto.py` | `models/question.py` | **已完成** | 2026-04-16 | 题库请求/响应 DTO |
| 17.4 | ExtractDTO | `api/dto/extract_dto.py` | `models/extract.py` | 待开始 | - | 提取请求/响应 |
| 17.5 | MemoryDTO | `api/dto/memory_dto.py` | - | 待开始 | - | 记忆请求/响应 |

---

### 阶段 18：API Routes v2 创建 🔄 进行中

| 序号 | 任务 | 目标位置 | 源位置 | 状态 | 完成日期 | 备注 |
|------|------|----------|--------|------|----------|------|
| 18.1 | Chat Routes v2 | `api/routes/chat_v2.py` | `api/routes/chat.py` | 待开始 | - | 使用新架构 |
| 18.2 | Interview Routes v2 | `api/routes/interview_v2.py` | `api/routes/interview.py` | 待开始 | - | 使用新架构 |
| 18.3 | Questions Routes v2 | `api/routes/questions_v2.py` | `api/routes/questions.py` | **已完成** | 2026-04-16 | 已注册到 `/api/v2/questions` |
| 18.4 | Extract Routes v2 | `api/routes/extract_v2.py` | `api/routes/extract.py` | 待开始 | - | 使用新架构 |
| 18.5 | Memory Routes v2 | `api/routes/memory_v2.py` | - | 待开始 | - | 新增记忆 API |

**阶段 18 检查点**：
- [x] Questions Routes v2 完成，支持 CRUD 操作
- [x] 新旧 API 可并行运行（v1 + v2）
- [ ] 其他 Routes 待实现

---

### 阶段 19：清理旧代码

| 序号 | 任务 | 说明 | 状态 | 完成日期 |
|------|------|------|------|----------|
| 19.1 | 删除 `models/` | 所有模型已迁移到 `domain/` | 待开始 | - |
| 19.2 | 删除 `pipelines/` | 已迁移到 `application/services/` | 待开始 | - |
| 19.3 | 删除 `db/` | 已迁移到 `infrastructure/persistence/` | 待开始 | - |
| 19.4 | 删除 `mq/` | 已迁移到 `infrastructure/messaging/` | 待开始 | - |
| 19.5 | 删除旧 `agents/` | Workflow 在 `domain/`，执行器在 `application/` | 待开始 | - |
| 19.6 | 删除旧 `tools/` | 已迁移到 `domain/*/tools.py` 或 `infrastructure/adapters/` | 待开始 | - |
| 19.7 | 删除旧 `services/` | 已按职责拆分迁移 | 待开始 | - |
| 19.8 | 删除旧 `utils/` | 仅保留必要的，大部分已迁移 | 待开始 | - |
| 19.8.1 | 删除 `infrastructure/common/hasher.py` | 领域逻辑，已在 `domain/question/utils.py` 实现 | **已完成** | 2026-04-17 |
| 19.8.2 | 更新 `utils/hasher.py` 导入转发 | 改为转发 `domain/question/utils.py` | **已完成** | 2026-04-17 |
| 19.9 | 删除旧 Routes v1 | v2 Routes 已验证可用 | 待开始 | - |
| 19.10 | 更新 main.py | 使用新架构入口 | 待开始 | - |

---

## 统计信息

| 指标 | 数量 |
|------|------|
| 总阶段数 | 19 |
| 总任务数 | 91 |
| 已完成 | 40 |
| 进行中 | 0 |
| 待开始 | 51 |
| 完成进度 | 43.9% |

---

## 下一步行动

**已完成题库垂直切片！**

入库流程已打通：
```
面经图片上传 → VisionExtractor → ExtractTask (PostgreSQL)
    → 用户确认 → IngestionService → QuestionRepository (Qdrant)
    → MQ → AnswerWorker → 答案回填
```

**已完成的模块：**
- `domain/question/` - Question、Cluster、ExtractTask 聚合 + Repository Protocol + 领域事件
- `infrastructure/persistence/qdrant/` - QuestionRepository、ClusterRepository 实现
- `infrastructure/persistence/postgres/` - ExtractTaskRepository 实现
- `application/services/question_service.py` - 题 CRUD 用例
- `application/services/ingestion_service.py` - 入库用例（分类熔断 + 答案复用）
- `pipelines/ingestion.py` - 向后兼容转发层（仅保留 `process` 方法）

**推荐下一步：**
1. 测试数据库配置 - 让测试使用 `offer_catcher_test` 而非生产数据库
2. 继续实现其他领域的 Repository 和 Service
3. 或验证完整的入库流程（启动服务 + 调用 API）

---

## 备注

### 重构原则

1. **每完成一个任务，必须编写单元测试验证**
2. **保持向后兼容，逐步切换（v1 → v2）**
3. **使用 Protocol 而非 ABC 实现依赖倒置**
4. **不进行向后兼容的过渡代码，直接重构**

### 相关文档

- [DDD重构设计.md](DDD重构设计.md) - 详细设计方案
- [CLAUDE.md](../CLAUDE.md) - 项目编码规范