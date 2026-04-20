# DDD 重构进度跟踪

> 本文档用于跟踪 Offer-Catcher 项目向 DDD 架构重构的进度。
> 创建日期：2026-04-16
> 最后更新：2026-04-20
> 基于：[DDD重构设计.md](DDD重构设计.md)

---

## 重构概览

### 当前状态

| 层级 | 状态 | 说明 |
|------|------|------|
| `domain/shared/` | **已完成** | 枚举和异常定义已完成，测试通过 |
| `domain/question/` | **已完成** | Question、Cluster、ExtractTask 聚合 + Repository Protocol + 领域事件 |
| `domain/interview/` | **已完成** | InterviewSession 聚合 + Repository Protocol + 领域事件 |
| `domain/chat/` | **已完成** | Conversation 聚合 + Repository Protocol + 领域事件 |
| `domain/favorite/` | **已完成** | Favorite 聚合 + Repository Protocol + 领域事件（新增） |
| `domain/memory/` | **跳过** | 记忆领域待重新设计 |
| `infrastructure/common/` | **已完成** | logger、cache、retry、circuit_breaker、prompt、image、cache_keys 已迁移 |
| `infrastructure/observability/` | **已完成** | telemetry 已迁移 |
| `infrastructure/adapters/` | **已完成** | embedding、reranker、web_search、ocr、asr、llm、cache 已迁移 |
| `infrastructure/persistence/` | **已完成** | Qdrant、PostgreSQL、Redis、Neo4j 客户端 + 所有 Repository 实现已迁移 |
| `infrastructure/messaging/` | **已完成** | MQ 生产者、消费者、线程池消费者 + 消息定义已迁移 |
| `infrastructure/tools/` | **已完成** | search_questions、search_web、query_graph 已迁移 |
| `infrastructure/bootstrap/` | **已完成** | warmup 已迁移 |
| `infrastructure/config/` | **已完成** | settings 已迁移 |
| `application/services/` | **已完成** | 所有应用服务已实现 |
| `application/workers/` | **已完成** | 所有 Worker 已迁移 |
| `application/agents/` | **已完成** | 所有 Agent 已迁移到 application 层 |
| `api/dto/` | **已完成** | 所有 DTO 已实现 |
| `api/routes/` | **已完成** | 所有 Routes 使用新架构 |

### 清理状态

| 旧目录 | 状态 | 说明 |
|--------|------|------|
| `app/models/` | **已删除** | 所有模型已迁移到 `domain/` |
| `app/agents/` | **已删除** | 所有 Agent 已迁移到 `application/agents/` |
| `app/tools/` | **已删除** | LangChain @tool 在 `infrastructure/tools/`，其他已清理 |
| `app/pipelines/` | **已删除** | 入库逻辑在 `application/services/ingestion_service.py` |
| `app/db/` | **已删除** | 所有数据库客户端在 `infrastructure/persistence/` |
| `app/mq/` | **已删除** | 所有 MQ 相关在 `infrastructure/messaging/` |
| `app/utils/` | **已删除** | 大部分迁移，部分删除 |
| `app/memory/` | **已删除** | 记忆系统待重新设计 |

---

## 统计信息

| 指标 | 数量 |
|------|------|
| 总阶段数 | 19 |
| 总任务数 | 91 |
| 已完成 | 82 |
| 跳过 | 5 |
| 待开始 | 4 |
| 完成进度 | **90.1%** |

---

## 已完成阶段

### 阶段 1：基础设施层基础模块 ✅ 已完成

| 序号 | 任务 | 目标位置 | 状态 |
|------|------|----------|------|
| 1.1 | logger 迁移 | `infrastructure/common/logger.py` | **已完成** |
| 1.2 | cache 装饰器迁移 | `infrastructure/common/cache.py` | **已完成** |
| 1.3 | circuit_breaker 迁移 | `infrastructure/common/circuit_breaker.py` | **已完成** |
| 1.4 | retry 迁移 | `infrastructure/common/retry.py` | **已完成** |
| 1.5 | telemetry 迁移 | `infrastructure/observability/telemetry.py` | **已完成** |
| 1.6 | prompt_loader 迁移 | `infrastructure/common/prompt.py` | **已完成** |
| 1.7 | image 迁移 | `infrastructure/common/image.py` | **已完成** |
| 1.8 | hasher 迁移 | `domain/question/utils.py` | **已完成** |

### 阶段 2：外部服务适配器 ✅ 已完成

所有 adapters 已迁移：embedding、reranker、web_search、ocr、asr、llm、cache

### 阶段 3：领域层共享内核 ✅ 已完成

- enums.py - QuestionType, MasteryLevel, DifficultyLevel, SessionStatus, QuestionStatus 等
- exceptions.py - DomainException + 各领域异常层级

### 阶段 4：题库领域 ✅ 已完成

| 组件 | 位置 | 说明 |
|------|------|------|
| Question 聚合 | `domain/question/aggregates.py` | 聚合根 + QuestionItem, ExtractedInterview 值对象 |
| Cluster 聚合 | `domain/question/aggregates.py` | 聚合根 |
| ExtractTask 聚合 | `domain/question/aggregates.py` | 聚合根 |
| Repository Protocol | `domain/question/repositories.py` | QuestionRepository, ClusterRepository, ExtractTaskRepository |
| 领域事件 | `domain/question/events.py` | 7 个事件 |
| 领域服务 | `domain/question/services.py` | 领域逻辑 |

### 阶段 5：题库仓库实现 ✅ 已完成

| 仓库 | 位置 | 实现 |
|------|------|------|
| QuestionRepository | `infrastructure/persistence/qdrant/question_repository.py` | Qdrant |
| ClusterRepository | `infrastructure/persistence/qdrant/cluster_repository.py` | Qdrant |
| ExtractTaskRepository | `infrastructure/persistence/postgres/extract_task_repository.py` | PostgreSQL |
| Payloads | `infrastructure/persistence/qdrant/payloads.py` | QdrantQuestionPayload |

### 阶段 6：模拟面试领域 ✅ 已完成

| 组件 | 位置 | 说明 |
|------|------|------|
| InterviewSession 聚合 | `domain/interview/aggregates.py` | 聚合根 + InterviewQuestion 实体 |
| InterviewSessionCreate | `domain/interview/aggregates.py` | 创建请求 |
| InterviewReport | `domain/interview/aggregates.py` | 面试报告 |
| Repository Protocol | `domain/interview/repositories.py` | InterviewSessionRepository |
| 领域事件 | `domain/interview/events.py` | InterviewStarted, InterviewEnded 等 |
| 领域服务 | `domain/interview/services.py` | 领域逻辑 |

### 阶段 7：面试仓库实现 ✅ 已完成

- InterviewSessionRepository - `infrastructure/persistence/postgres/interview_session_repository.py`

### 阶段 8：智能对话领域 ✅ 已完成

| 组件 | 位置 | 说明 |
|------|------|------|
| Conversation 聚合 | `domain/chat/aggregates.py` | 聚合根 + Message 实体 |
| Repository Protocol | `domain/chat/repositories.py` | ConversationRepository |
| 领域事件 | `domain/chat/events.py` | ConversationCreated, ConversationEnded 等 |
| 领域服务 | `domain/chat/services.py` | 领域逻辑 |

### 阶段 9：对话仓库实现 ✅ 已完成

- ConversationRepository - `infrastructure/persistence/postgres/conversation_repository.py`

### 阶段 10-11：记忆领域 ⏭️ 跳过

记忆系统已删除，待重新设计。

### 阶段 12：消息队列迁移 ✅ 已完成

- producer.py - `infrastructure/messaging/producer.py`
- consumer.py - `infrastructure/messaging/consumer.py`
- thread_pool_consumer.py - `infrastructure/messaging/thread_pool_consumer.py`
- messages.py - `infrastructure/messaging/messages.py`

### 阶段 13：应用层事件机制 ⏭️ 跳过（可选）

事件发布/处理机制为可选优化，当前功能正常。

### 阶段 14：应用服务迁移 ✅ 已完成

| 服务 | 位置 | 说明 |
|------|------|------|
| IngestionApplicationService | `application/services/ingestion_service.py` | 入库用例 |
| RetrievalApplicationService | `application/services/retrieval_service.py` | 检索用例 |
| QuestionApplicationService | `application/services/question_service.py` | 题 CRUD 用例 |
| ChatApplicationService | `application/services/chat_service.py` | 对话用例 |
| InterviewApplicationService | `application/services/interview_service.py` | 面试用例 |
| FavoriteApplicationService | `application/services/favorite_service.py` | 收藏用例 |
| ExtractTaskService | `application/services/extract_task_service.py` | 提取任务用例 |
| CacheApplicationService | `application/services/cache_service.py` | 缓存用例 |
| ClusteringApplicationService | `application/services/clustering_service.py` | 聚类用例 |
| StatsApplicationService | `application/services/stats_service.py` | 统计用例 |

### 阶段 15：Worker 迁移 ✅ 已完成

所有 Worker 已迁移到 `application/workers/`：
- answer_worker.py
- extract_worker.py
- clustering_worker.py
- reembed_worker.py

### 阶段 16：启动预热迁移 ✅ 已完成

- warmup.py - `infrastructure/bootstrap/warmup.py`

### 阶段 17：API DTO 定义 ✅ 已完成

所有 DTO 已实现：
- question_dto.py
- chat_dto.py
- interview_dto.py
- extract_dto.py
- search_dto.py
- favorite_dto.py

### 阶段 18：API Routes ✅ 已完成

所有 Routes 直接使用新架构：
- questions.py
- chat.py
- interview.py
- extract.py
- score.py
- search.py
- favorites.py
- conversations.py
- stats.py
- speech.py

### 阶段 19：清理旧代码 ✅ 已完成

| 任务 | 状态 |
|------|------|
| 删除 `models/` | **已完成** |
| 删除 `pipelines/` | **已完成** |
| 删除 `db/` | **已完成** |
| 删除 `mq/` | **已完成** |
| 删除 `agents/` | **已完成** |
| 删除 `tools/` | **已完成** |
| 删除 `utils/` | **已完成** |
| 删除 `memory/` | **已完成** |

---

## 待完成（可选优化）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| `domain/question/prompts/` | 提示词文件迁移到领域层 | P4 |
| `domain/chat/workflow/` | Workflow 定义迁移到领域层（当前在 application） | P4 |
| `domain/interview/workflow/` | Workflow 定义迁移到领域层 | P4 |
| `application/events/` | 事件发布/处理机制 | P3 |

---

## 架构验证

```bash
uv run python -c "
from app.domain.question import Question, QuestionRepository
from app.domain.interview import InterviewSession, InterviewSessionRepository
from app.domain.chat import Conversation, ConversationRepository
from app.domain.favorite import Favorite, FavoriteRepository
from app.application.services import get_question_service, get_ingestion_service
from app.infrastructure.persistence.qdrant import get_question_repository
print('All DDD imports OK')
"
```

---

## 备注

### 重构成果

1. **清晰的分层架构**：Domain → Application → Infrastructure → API
2. **依赖倒置**：Domain 定义 Protocol，Infrastructure 实现
3. **聚合设计**：每个领域有明确的聚合根和边界
4. **领域事件**：跨聚合通信机制已定义
5. **清理完成**：所有旧转发层已删除

### 与设计文档的差异

1. **Workflow 位置**：设计文档建议 workflow 在 domain 层，实际放在 application/agents/（功能正常）
2. **记忆领域**：已删除，待重新设计
3. **事件机制**：事件定义完成，但发布/处理机制未实现（可选）
4. **新增领域**：favorite 领域为新增内容

### 相关文档

- [DDD重构设计.md](DDD重构设计.md) - 详细设计方案
- [CLAUDE.md](../CLAUDE.md) - 项目编码规范