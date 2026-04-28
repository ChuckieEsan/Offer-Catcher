# Offer-Catcher Java 重构方案

## 1. 项目概述

### 1.1 当前 Python 项目技术栈

| 层级 | 技术选型 |
|------|----------|
| 后端框架 | FastAPI + Uvicorn |
| AI Agent | LangChain + LangGraph（StateGraph + Checkpointer） |
| 向量数据库 | Qdrant（1024 维 bge-m3） |
| 关系数据库 | PostgreSQL + pgvector |
| 图数据库 | Neo4j（考频关系、知识点图谱） |
| 消息队列 | RabbitMQ（异步答案生成） |
| 缓存 | Redis（Session + 检索结果缓存） |
| Embedding | 本地 bge-m3 模型 |
| Reranker | 本地 bge-reranker-base |
| OCR | PaddleOCR / EasyOCR |
| LLM Provider | DeepSeek / OpenAI / SiliconFlow（多 Provider 切换） |
| ASR | 讯飞语音识别 |
| Web Search | Tavily |
| 可观测性 | OpenTelemetry + Prometheus + Pyroscope |
| 前端 | Next.js 16 + React 19 + Ant Design 6 + Tailwind CSS 4 |

### 1.2 DDD 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                       API Layer                              │
│  REST Controllers + SSE Streaming + DTO Validation           │
├─────────────────────────────────────────────────────────────┤
│                    Application Layer                         │
│  Services + Agents (LangGraph) + Workers + Event Handlers    │
├─────────────────────────────────────────────────────────────┤
│                      Domain Layer                            │
│  Aggregates + Repository Interfaces + Domain Services        │
│  (Question, Cluster, ExtractTask, Memory, Interview)         │
├─────────────────────────────────────────────────────────────┤
│                   Infrastructure Layer                       │
│  Repository Implementations + External Adapters + Messaging  │
│  (Qdrant, PostgreSQL, Neo4j, Redis, RabbitMQ, LLM)          │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Java 技术栈选型

### 2.1 核心框架

| 模块 | Python | Java 选型 | 理由 |
|------|--------|-----------|------|
| Web 框架 | FastAPI | **Spring Boot 3.4 + WebFlux** | 非阻塞 IO 支持流式响应，生态成熟 |
| AI Agent | LangGraph | **Spring AI + 自研 Agent Framework** | Spring AI 提供基础 LLM 集成，Agent 状态机需自研 |
| 数据校验 | Pydantic v2 | **Jakarta Validation + Hibernate Validator** | Bean Validation 标准 |
| 配置管理 | pydantic-settings | **Spring Boot Configuration Properties** | 类型安全配置绑定 |
| 依赖注入 | 手动单例 | **Spring IoC Container** | 自动装配、生命周期管理 |

### 2.2 数据存储

| 模块 | Python | Java 选型 | 理由 |
|------|--------|-----------|------|
| 向量数据库 | qdrant-client | **Qdrant Java Client (Official)** | 官方 SDK，支持 gRPC + REST |
| 关系数据库 | psycopg + SQLAlchemy | **Spring Data JPA + PostgreSQL JDBC** | JPA 标准，Hibernate 实现 |
| 向量扩展 | pgvector | **pgvector-jdbc (Community)** | 支持 PostgreSQL 向量操作 |
| 图数据库 | neo4j-driver | **Spring Data Neo4j 7** | 官方 Spring 集成，RxJava 支持 |
| 缓存 | redis-py | **Spring Data Redis + Lettuce** | 非阻塞客户端 |
| 消息队列 | aio-pika | **Spring AMQP + RabbitMQ Java Client** | 消息确认机制完善 |

### 2.3 AI 相关

| 模块 | Python | Java 选型 | 理由 |
|------|--------|-----------|------|
| LLM 调用 | langchain-openai/deepseek | **Spring AI (OpenAI/DeepSeek Module)** | 统一 API，支持多 Provider |
| Embedding | HuggingFace Transformers | **ONNX Runtime + DJL (Deep Java Library)** | 本地推理，避免 Python 依赖 |
| Reranker | 同上 | **ONNX Runtime** | 导出 ONNX 模型，Java 推理 |
| OCR | PaddleOCR | **保留 Python 微服务 + HTTP API** | OCR 生态不成熟，建议独立服务 |
| ASR | 讯飞 SDK | **讯飞 Java SDK** | 官方提供 Java 版本 |
| Web Search | Tavily | **自研 HTTP Client + Jackson** | 简单 REST 调用 |

### 2.4 可观测性

| 模块 | Python | Java 选型 | 理由 |
|------|--------|-----------|------|
| Metrics | Prometheus Client | **Micrometer + Prometheus Registry** | Spring Boot 内置支持 |
| Tracing | OpenTelemetry SDK | **Spring Boot 3 OTel Integration** | 自动埋点 |
| Profiling | Pyroscope | **Java Flight Recorder + Async Profiler** | JVM 内置工具 |
| Logging | 自研 Logger | **SLF4J + Logback** | 标准 Logging 门面 |

### 2.5 前端

保持 Next.js 前端不变，仅需调整 API 调用适配。

---

## 3. 模块设计

### 3.1 Domain Layer（领域层）

**设计原则：**
- 零外部依赖（除 Java 标准库）
- Repository 定义为 Interface（依赖倒置）
- 聚合根包含业务方法，不暴露 setter

**领域模块划分：**

```
com.offercatcher.domain/
├── shared/
│   ├── enums/
│   │   ├── QuestionType.java          // 题目类型枚举
│   │   ├── MasteryLevel.java          // 熟练度等级
│   │   ├── SessionStatus.java         // 面试会话状态
│   │   ├── MemoryType.java            // 记忆类型
│   │   └── MemoryLayer.java           // 记忆层级 (STM/LTM)
│   └── exception/
│   │   ├── DomainException.java       // 领域异常基类
│   │   ├── QuestionNotFoundException.java
│   │   └── InvalidStateTransitionException.java
│
├── question/
│   ├── aggregates/
│   │   ├── Question.java              // 题目聚合根
│   │   ├── Cluster.java               // 考点簇聚合根
│   │   └── ExtractTask.java           // 提取任务聚合根
│   ├── valueobjects/
│   │   ├── QuestionItem.java          // 提取阶段值对象
│   │   ├── ExtractedInterview.java    // 提取结果值对象
│   │   └── QuestionContext.java       // Embedding 上下文
│   ├── repositories/
│   │   ├── QuestionRepository.java    // Repository Interface
│   │   ├── ClusterRepository.java
│   │   └── ExtractTaskRepository.java
│   ├── services/
│   │   ├── QuestionIdGenerator.java   // MD5 ID 生成
│   │   └── AnswerClassificationService.java  // 分类熔断判断
│   └── events/
│   │   ├── QuestionCreatedEvent.java
│   │   ├── AnswerGeneratedEvent.java
│   │   └── ClusterAssignedEvent.java
│
├── memory/
│   ├── aggregates/
│   │   ├── Memory.java                // 记忆聚合根（主文档）
│   │   ├── MemoryReference.java       // 引用实体
│   │   ├── SessionSummary.java        // 会话摘要实体
│   ├── repositories/
│   │   ├── MemoryRepository.java
│   │   └── SessionSummaryRepository.java
│   ├── services/
│   │   ├── MemoryDecayService.java    // STM 衰减计算
│   │   ├── MemoryUpgradeService.java  // STM -> LTM 升级
│   └── events/
│   │   ├── MemoryCreatedEvent.java
│   │   ├── MemoryReferencedEvent.java
│
├── interview/
│   ├── aggregates/
│   │   ├── InterviewSession.java      // 面试会话聚合根
│   │   ├── SessionQuestion.java       // 面试题目实体
│   ├── repositories/
│   │   ├── InterviewSessionRepository.java
│   ├── services/
│   │   ├── FollowUpDecisionService.java  // 追问决策
│   └── events/
│   │   ├── SessionStartedEvent.java
│   │   ├── QuestionAnsweredEvent.java
│
├── chat/
│   ├── aggregates/
│   │   ├── Conversation.java          // 对话聚合根
│   │   ├── ChatMessage.java           // 消息实体
│   ├── repositories/
│   │   ├── ConversationRepository.java
│   └── events/
│   │   ├── MessageCreatedEvent.java
│
└── favorite/
│   ├── aggregates/
│   │   ├── Favorite.java              // 收藏聚合根
│   ├── repositories/
│   │   ├── FavoriteRepository.java
```

**聚合根示例（Question.java）：**

```java
package com.offercatcher.domain.question.aggregates;

import com.offercatcher.domain.shared.enums.*;
import com.offercatcher.domain.question.valueobjects.*;
import java.time.LocalDateTime;
import java.util.*;

public class Question {
    private final String questionId;      // MD5(company|questionText)
    private String questionText;
    private final QuestionType questionType;
    private MasteryLevel masteryLevel;
    private final String company;
    private final String position;
    private List<String> coreEntities;
    private String answer;
    private List<String> clusterIds;
    private Map<String, Object> metadata;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    // 工厂方法
    public static Question create(String questionText, String company, 
                                   String position, QuestionType type,
                                   List<String> entities) {
        String id = QuestionIdGenerator.generate(company, questionText);
        return new Question(id, questionText, type, company, position, entities);
    }

    // 业务方法（封装状态变更）
    public void updateAnswer(String newAnswer) {
        this.answer = newAnswer;
        this.updatedAt = LocalDateTime.now();
    }

    public void addCluster(String clusterId) {
        if (!this.clusterIds.contains(clusterId)) {
            this.clusterIds.add(clusterId);
        }
    }

    public void updateMastery(MasteryLevel level) {
        this.masteryLevel = level;
    }

    // 分类熔断判断
    public boolean requiresAsyncAnswer() {
        return questionType.requiresAsyncAnswer();
    }

    // 生成 Embedding 上下文
    public String toContext() {
        String entities = coreEntities.isEmpty() ? "综合" : 
                          String.join(",", coreEntities);
        return String.format("公司：%s | 岗位：%s | 类型：%s | 考点：%s | 题目：%s",
                             company, position, questionType.getValue(), 
                             entities, questionText);
    }

    // 无 public setter，保证封装
    private Question(String id, String text, QuestionType type, 
                     String company, String position, List<String> entities) {
        this.questionId = id;
        this.questionText = text;
        this.questionType = type;
        this.company = company;
        this.position = position;
        this.coreEntities = new ArrayList<>(entities);
        this.masteryLevel = MasteryLevel.LEVEL_0;
        this.clusterIds = new ArrayList<>();
        this.metadata = new HashMap<>();
        this.createdAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
    }
}
```

### 3.2 Infrastructure Layer（基础设施层）

**目录结构：**

```
com.offercatcher.infrastructure/
├── config/
│   ├── OfferCatcherProperties.java    // 配置类
│   ├── QdrantConfig.java
│   ├── Neo4jConfig.java
│   ├── RedisConfig.java
│   └── RabbitMQConfig.java
│
├── persistence/
│   ├── qdrant/
│   │   ├── QdrantClient.java          // Qdrant 连接封装
│   │   ├── QdrantQuestionRepositoryImpl.java
│   │   ├── QdrantPayloadMapper.java   // Payload 转换
│   │   └── QdrantFilterBuilder.java   // 过滤条件构建
│   ├── postgres/
│   │   ├── JpaConfig.java
│   │   ├── ConversationRepositoryImpl.java
│   │   ├── FavoriteRepositoryImpl.java
│   │   ├── MemoryRepositoryImpl.java
│   │   ├── SessionSummaryRepositoryImpl.java
│   │   ├── ExtractTaskRepositoryImpl.java
│   │   └── InterviewSessionRepositoryImpl.java
│   ├── neo4j/
│   │   ├── Neo4jClient.java
│   │   ├── GraphRepositoryImpl.java
│   │   └── CypherQueryBuilder.java
│   └── redis/
│   │   ├── RedisCacheClient.java
│   │   ├── RedisKeys.java             // Key 规范
│
├── adapters/
│   ├── llm/
│   │   ├── LLMAdapter.java            // 统一 LLM 接口
│   │   ├── DeepSeekAdapter.java       // DeepSeek 实现
│   │   ├── OpenAIAdapter.java         // OpenAI 实现
│   │   ├── SiliconFlowAdapter.java    // SiliconFlow 实现
│   │   ├── LLMProviderFactory.java    // Provider 工厂
│   ├── embedding/
│   │   ├── EmbeddingAdapter.java
│   │   ├── OnnxEmbeddingModel.java    // ONNX Runtime 推理
│   │   ├── EmbeddingBatchProcessor.java
│   ├── reranker/
│   │   ├── RerankerAdapter.java
│   │   ├── OnnxRerankerModel.java
│   ├── asr/
│   │   ├── XfyunAsrAdapter.java       // 讯飞 ASR
│   ├── search/
│   │   ├── TavilySearchAdapter.java
│
├── messaging/
│   ├── RabbitMQConfig.java
│   ├── MessageProducer.java
│   ├── MessageConsumer.java
│   ├── AnswerTaskConsumer.java        // 答案生成 Consumer
│   ├── ExtractTaskConsumer.java       // OCR 提取 Consumer
│   ├── MessageHelper.java             // DLQ、重试机制
│   ├── messages/
│   │   ├── MQTaskMessage.java         // MQ 消息 DTO
│
├── common/
│   ├── cache/
│   │   ├── CacheService.java          // 缓存服务
│   │   ├── CircuitBreaker.java        // 熔断器
│   ├── retry/
│   │   ├── RetryPolicy.java
│   ├── logger/
│   │   ├── StructuredLogger.java      // 结构化日志
│   ├── prompt/
│   │   ├── PromptTemplateLoader.java  // Prompt 加载
│
├── tools/
│   ├── SearchQuestionsTool.java       // LangChain Tool 实现
│   ├── GetCompanyHotTopicsTool.java
│   ├── GetCrossCompanyTrendsTool.java
│   ├── GetKnowledgeRelationsTool.java
│   ├── MemoryRetrieveTool.java
│   ├── WebSearchTool.java
│
└── observability/
    ├── MetricsConfig.java
    ├── TracingConfig.java
    ├── TelemetryService.java
```

**Repository 实现示例：**

```java
package com.offercatcher.infrastructure.persistence.qdrant;

import com.offercatcher.domain.question.aggregates.*;
import com.offercatcher.domain.question.repositories.*;
import com.offercatcher.infrastructure.adapters.embedding.*;
import io.qdrant.client.QdrantClient;
import io.qdrant.client.grpc.Points.PointStruct;
import org.springframework.stereotype.Repository;

@Repository
public class QdrantQuestionRepositoryImpl implements QuestionRepository {

    private final QdrantClient qdrantClient;
    private final EmbeddingAdapter embeddingAdapter;
    private final QdrantPayloadMapper payloadMapper;
    private final QdrantFilterBuilder filterBuilder;

    public QdrantQuestionRepositoryImpl(QdrantClient client,
                                        EmbeddingAdapter embedding,
                                        QdrantPayloadMapper mapper) {
        this.qdrantClient = client;
        this.embeddingAdapter = embedding;
        this.payloadMapper = mapper;
        this.filterBuilder = new QdrantFilterBuilder();
    }

    @Override
    public Question findById(String questionId) {
        var result = qdrantClient.retrieveAsync(questionId);
        if (result.isEmpty()) return null;
        return payloadMapper.toDomain(result.get().payload);
    }

    @Override
    public void save(Question question) {
        // 计算 Embedding
        String context = question.toContext();
        float[] vector = embeddingAdapter.embed(context);

        // 构建 Point
        PointStruct point = PointStruct.newBuilder()
            .setId(question.getQuestionId())
            .setVectors(Vectors.newBuilder().setVector(Vector.newBuilder()
                .addAllData(Arrays.asList(vector))))
            .setPayload(payloadMapper.toPayload(question))
            .build();

        // Upsert
        qdrantClient.upsertAsync(point);
    }

    @Override
    public List<QuestionWithScore> search(float[] queryVector,
                                          Map<String, Object> filters,
                                          int limit) {
        var queryFilter = filterBuilder.build(filters);
        var results = qdrantClient.searchAsync(queryVector, queryFilter, limit);

        return results.stream()
            .map(r -> new QuestionWithScore(
                payloadMapper.toDomain(r.payload),
                r.score))
            .toList();
    }

    @Override
    public void updateAnswer(String questionId, String answer) {
        qdrantClient.setPayloadAsync(questionId, 
            Map.of("question_answer", answer));
    }
}
```

### 3.3 Application Layer（应用层）

**目录结构：**

```
com.offercatcher.application/
├── services/
│   ├── QuestionService.java            // 题目 CRUD
│   ├── IngestionService.java           // 入库编排
│   ├── RetrievalService.java           // 检索 + Rerank
│   ├── ChatService.java                // 对话编排
│   ├── InterviewService.java           // 面试编排
│   ├── MemoryService.java              // 记忆管理
│   ├── FavoriteService.java            // 收藏管理
│   ├── CacheService.java               // 缓存管理
│   ├── ClusteringService.java          // 聚类服务
│   ├── ExtractTaskService.java         // 提取任务管理
│   ├── StatsService.java               // 统计服务
│
├── agents/
│   ├── core/
│   │   ├── AgentExecutor.java         // Agent 执行器接口
│   │   ├── AgentState.java            // 状态定义
│   │   ├── AgentWorkflow.java         // 工作流编排（替代 LangGraph）
│   │   ├── StateTransition.java       // 状态转移规则
│   │   ├── Checkpointer.java          // 状态持久化接口
│   │   ├── PostgresCheckpointer.java  // PostgreSQL 实现
│   │
│   ├── chat/
│   │   ├── ChatAgent.java             // 对话 Agent
│   │   ├── ChatWorkflow.java          // StateGraph 替代
│   │   ├── ChatNodes.java             // 节点实现
│   │   ├── ChatEdges.java             // 路由条件
│   │   ├── ChatState.java             // 状态定义
│   │   └── prompts/
│   │       ├── RouterPrompt.java
│   │       ├── ExtractPrompt.java
│   │       ├── ReactPrompt.java
│   │
│   ├── answer/
│   │   ├── AnswerSpecialist.java      // 答案生成 Agent
│   │   ├── prompts/
│   │       ├── AnswerPrompt.java
│   │
│   ├── interview/
│   │   ├── InterviewAgent.java        // 面试 Agent
│   │   ├── InterviewState.java
│   │   ├── prompts/
│   │       ├── InterviewPrompt.java
│   │       ├── FollowUpPrompt.java
│   │       ├── ScorePrompt.java
│   │
│   ├── memory/
│   │   ├── MemoryAgent.java           // 记忆提取 Agent
│   │   ├── MemoryState.java
│   │   ├── MemoryHooks.java           // 对话后提取 Hook
│   │   ├── prompts/
│   │       ├── MemoryPrompt.java
│   │
│   ├── scorer/
│   │   ├── ScorerAgent.java           // 评分 Agent
│   │   ├── ScoringResult.java
│   │
│   ├── vision/
│   │   ├── VisionExtractorAgent.java  // OCR 提取 Agent
│   │   ├── ClassificationService.java // 分类熔断
│   │
│   ├── title/
│   │   ├── TitleGeneratorAgent.java
│   │
│   └── factory/
│       ├── AgentFactory.java          // Agent 工厂
│       ├── AgentRegistry.java         // Agent 注册表
│
├── workers/
│   ├── AnswerWorker.java              // 答案生成 Worker
│   ├── ExtractWorker.java             // OCR 提取 Worker
│   ├── ClusteringWorker.java          // 聚类 Worker
│   ├── ReEmbedWorker.java             // 重向量 Worker
│   ├── MemoryRetrievalWorker.java     // 记忆检索 Worker
│
├── eventhandlers/
│   ├── QuestionEventHandler.java
│   ├── MemoryEventHandler.java
│   ├── InterviewEventHandler.java
│
└── dto/
    ├── ChatRequestDto.java
    ├── ChatResponseDto.java
    ├── ExtractRequestDto.java
    ├── InterviewRequestDto.java
    ├── MemoryRequestDto.java
    ├── SearchRequestDto.java
    ├── SearchResponseDto.java
```

**Agent Workflow 设计（替代 LangGraph）：**

由于 Java 没有 LangGraph 等成熟 Agent 框架，需要自研状态机：

```java
package com.offercatcher.application.agents.core;

import java.util.*;
import java.util.function.*;

public class AgentWorkflow<T extends AgentState> {

    private final Map<String, Function<T, T>> nodes = new HashMap<>();
    private final Map<String, BiFunction<T, String>> edges = new HashMap<>();
    private final String entryPoint;
    private final Checkpointer<T> checkpointer;

    public AgentWorkflow(String entryPoint, Checkpointer<T> checkpointer) {
        this.entryPoint = entryPoint;
        this.checkpointer = checkpointer;
    }

    // 添加节点
    public AgentWorkflow<T> addNode(String name, Function<T, T> action) {
        nodes.put(name, action);
        return this;
    }

    // 添加条件边
    public AgentWorkflow<T> addConditionalEdges(
            String from,
            BiFunction<T, String> router,
            Map<String, String> routes) {
        edges.put(from, router);
        return this;
    }

    // 添加固定边
    public AgentWorkflow<T> addEdge(String from, String to) {
        edges.put(from, (state) -> to);
        return this;
    }

    // 执行工作流
    public T execute(T initialState, String threadId) {
        // 从 Checkpointer 恢复状态
        T state = checkpointer.restore(threadId)
            .orElse(initialState);

        String currentNode = entryPoint;

        while (currentNode != null && !currentNode.equals("END")) {
            // 执行节点
            Function<T, T> action = nodes.get(currentNode);
            if (action == null) {
                throw new IllegalStateException("Node not found: " + currentNode);
            }
            state = action.apply(state);

            // 确定下一个节点
            BiFunction<T, String> router = edges.get(currentNode);
            if (router != null) {
                currentNode = router.apply(state);
            } else {
                currentNode = null; // 终止
            }

            // 保存状态到 Checkpointer
            checkpointer.save(threadId, state);
        }

        return state;
    }

    // 流式执行（SSE）
    public Flux<AgentEvent> executeStreaming(T initialState, String threadId) {
        return Flux.create(emitter -> {
            T state = checkpointer.restore(threadId)
                .orElse(initialState);
            String currentNode = entryPoint;

            while (currentNode != null && !currentNode.equals("END")) {
                emitter.next(new AgentEvent("node_start", currentNode, null));

                Function<T, T> action = nodes.get(currentNode);
                state = action.apply(state);

                // 发送节点完成事件
                emitter.next(new AgentEvent("node_end", currentNode, 
                    state.getResponseToUser()));

                BiFunction<T, String> router = edges.get(currentNode);
                if (router != null) {
                    currentNode = router.apply(state);
                } else {
                    currentNode = null;
                }

                checkpointer.save(threadId, state);
            }

            emitter.complete();
        });
    }
}
```

**ChatWorkflow 实现：**

```java
package com.offercatcher.application.agents.chat;

import com.offercatcher.application.agents.core.*;
import org.springframework.stereotype.Component;

@Component
public class ChatWorkflow extends AgentWorkflow<ChatState> {

    public ChatWorkflow(PostgresCheckpointer<ChatState> checkpointer,
                        ChatNodes nodes) {
        super("state_gate", checkpointer);

        // 注册节点
        addNode("state_gate", nodes::stateGate);
        addNode("router", nodes::router);
        addNode("extract", nodes::extract);
        addNode("confirm", nodes::confirm);
        addNode("handle_confirmation", nodes::handleConfirmation);
        addNode("store_and_mq", nodes::storeAndMQ);
        addNode("react_loop", nodes::reactLoop);

        // 条件边
        addConditionalEdges("state_gate", 
            ChatEdges::stateGate, 
            Map.of("handle_confirmation", "handle_confirmation",
                   "router", "router"));

        addConditionalEdges("router",
            ChatEdges::routeByIntent,
            Map.of("ingest_flow", "extract",
                   "react_flow", "react_loop"));

        addConditionalEdges("handle_confirmation",
            ChatEdges::routeByConfirmation,
            Map.of("store_and_mq", "store_and_mq",
                   "extract", "extract"));

        // 固定边
        addEdge("extract", "confirm");
        addEdge("confirm", "END");
        addEdge("store_and_mq", "END");
        addEdge("react_loop", "END");
    }
}
```

### 3.4 API Layer（接口层）

**目录结构：**

```
com.offercatcher.api/
├── controller/
│   ├── ChatController.java            // 对话 API（SSE）
│   ├── ExtractController.java         // 图片提取 API
│   ├── SearchController.java          // 检索 API
│   ├── InterviewController.java       // 面试 API
│   ├── QuestionController.java        // 题目 CRUD
│   ├── MemoryController.java          // 记忆 API
│   ├── FavoriteController.java        // 收藏 API
│   ├── StatsController.java           // 统计 API
│   ├── SpeechController.java          // 语音 API
│   ├── ConversationController.java    // 会话历史
│
├── dto/
│   ├── request/
│   │   ├── ChatRequest.java
│   │   ├── ExtractRequest.java
│   │   ├── SearchRequest.java
│   │   ├── InterviewRequest.java
│   │   ├── MemoryRequest.java
│   ├── response/
│   │   ├── ChatResponse.java
│   │   ├── SearchResponse.java
│   │   ├── InterviewResponse.java
│   │   ├── ExtractResponse.java
│   │   ├── ApiErrorResponse.java
│
├── config/
│   ├── WebConfig.java                 // CORS、拦截器
│   ├── AsyncConfig.java               // 异步配置
│   ├── SSEConfig.java                 // SSE 配置
│   ├── OpenAPIConfig.java             // Swagger 配置
│
├── exception/
│   ├── GlobalExceptionHandler.java
│   ├── DomainExceptionMapper.java
│
├── filter/
│   ├── RequestLoggingFilter.java
│   ├── UserIdInjectionFilter.java
│
└── streaming/
    ├── SSEEmitterFactory.java
    ├── StreamingResponseBuilder.java
```

**Controller 示例（流式对话）：**

```java
package com.offercatcher.api.controller;

import com.offercatcher.application.services.*;
import com.offercatcher.api.dto.request.*;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/v1/chat")
public class ChatController {

    private final ChatService chatService;

    public ChatController(ChatService chatService) {
        this.chatService = chatService;
    }

    @PostMapping("/stream")
    public Flux<String> chatStream(@RequestBody ChatRequest request) {
        return chatService.streamChat(
            request.getMessage(),
            request.getConversationId(),
            request.getUserId()
        ).map(event -> "data: " + event.toJson() + "\n\n")
         .concatWith(Flux.just("data: [DONE]\n\n"));
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok", "service", "offer-catcher-api");
    }
}
```

---

## 4. 核心业务流程迁移

### 4.1 面经图片提取流程

**Python 流程：**
```
用户上传图片 → OCR → VisionExtractor Agent → 用户确认 → IngestionService → Qdrant + RabbitMQ
```

**Java 流程（保持不变）：**
```
前端上传图片 → ExtractController → ExtractTaskService
    → 调用 Python OCR 微服务（HTTP API）
    → VisionExtractorAgent (Java)
    → 用户确认 → IngestionService
    → QdrantQuestionRepository.save()
    → MessageProducer.publish(AnswerTaskMessage)
```

**OCR 微服务设计：**
```yaml
# docker-compose.yml
services:
  ocr-service:
    build: ./ocr-service  # Python FastAPI
    ports:
      - "8001:8001"
    environment:
      - OCR_MODEL=paddleocr
```

OCR 服务保持 Python 实现（PaddleOCR），Java 通过 HTTP 调用。

### 4.2 AI 对话流程

**Python 流程（LangGraph）：**
```
用户消息 → ChatAgent.astream_workflow()
    → StateGate → Router → (Extract/ReactLoop)
    → Memory Hook（异步）
    → Postgres Checkpointer
```

**Java 流程（自研 Workflow）：**
```java
@Service
public class ChatService {

    private final ChatWorkflow chatWorkflow;
    private final MemoryHooks memoryHooks;

    public Flux<AgentEvent> streamChat(String message, 
                                        String conversationId,
                                        String userId) {
        ChatState initialState = new ChatState(
            List.of(new HumanMessage(message)),
            new SessionContext(userId));

        // Fire-and-forget: 触发记忆检索
        memoryHooks.triggerRetrieval(userId, conversationId, message);

        return chatWorkflow.executeStreaming(initialState, conversationId)
            .doOnComplete(() -> {
                // Fire-and-forget: 触发记忆提取
                ChatState finalState = chatWorkflow.getFinalState();
                memoryHooks.extractMemories(userId, conversationId, 
                    finalState.getMessages());
            });
    }
}
```

### 4.3 答案异步生成流程

**Python Worker：**
```python
# answer_worker.py
def process_answer_task(task: MQTaskMessage):
    question_repo.find_by_id(task.question_id)
    if existing.answer: return True  # 幂等
    agent.generate_answer(question)
    question_repo.update_answer(id, answer)
```

**Java Worker：**
```java
@Component
public class AnswerWorker {

    private final QuestionRepository questionRepo;
    private final AnswerSpecialist answerAgent;

    @RabbitListener(queues = "answer_tasks")
    public void processAnswerTask(MQTaskMessage task) {
        // 幂等检查
        Question existing = questionRepo.findById(task.getQuestionId());
        if (existing != null && existing.getAnswer() != null) {
            log.info("Answer already exists: {}", task.getQuestionId());
            return;
        }

        // 生成答案
        String answer = answerAgent.generateAnswer(
            task.getQuestionText(),
            task.getCoreEntities(),
            task.getCompany(),
            task.getPosition()
        );

        // 更新
        questionRepo.updateAnswer(task.getQuestionId(), answer);
    }
}
```

### 4.4 向量检索流程

**Python 流程：**
```python
# retrieval_service.py
def search(query, filters):
    vector = embedding_adapter.embed(query)
    results = qdrant_repo.search(vector, filters)
    reranked = reranker.rerank(results, query)
    return reranked
```

**Java 流程：**
```java
@Service
public class RetrievalService {

    private final EmbeddingAdapter embeddingAdapter;
    private final QuestionRepository questionRepo;
    private final RerankerAdapter reranker;

    public List<QuestionWithScore> search(String query, 
                                          Map<String, Object> filters,
                                          int topK) {
        // Embedding
        float[] vector = embeddingAdapter.embed(query);

        // Qdrant 搜索
        List<QuestionWithScore> results = 
            questionRepo.search(vector, filters, topK * 2);

        // Rerank
        return reranker.rerank(results, query, topK);
    }
}
```

### 4.5 记忆系统流程

**STM/LTM 衰减机制：**
```java
@Service
public class MemoryDecayService {

    @Scheduled(fixedRate = 86400000)  // 每天执行
    public void applyDecay() {
        List<SessionSummary> stmSummaries = summaryRepo.findByLayer(MemoryLayer.STM);
        
        for (SessionSummary summary : stmSummaries) {
            summary.applyDecay(0.1);  // 衰减率 10%
            
            if (summary.getDecayFactor() < 0.1) {
                summaryRepo.delete(summary.getId());
            } else {
                summaryRepo.save(summary);
            }
        }
    }

    public void upgradeToLtm(String summaryId) {
        SessionSummary summary = summaryRepo.findById(summaryId);
        summary.upgradeToLtm();
        summaryRepo.save(summary);
    }
}
```

---

## 5. Embedding 模型迁移方案

### 5.1 ONNX Runtime 方案

**步骤：**

1. **导出 ONNX 模型（Python）：**
```python
# scripts/export_onnx.py
from transformers import AutoModel
import torch

model = AutoModel.from_pretrained("BAAI/bge-m3")
model.eval()

# 导出为 ONNX
torch.onnx.export(
    model,
    torch.randn(1, 512),  # dummy input
    "bge-m3.onnx",
    input_names=["input_ids", "attention_mask"],
    output_names=["embeddings"],
    dynamic_axes={"input_ids": {0: "batch", 1: "seq"}}
)
```

2. **Java ONNX 推理：**
```java
@Component
public class OnnxEmbeddingModel implements EmbeddingAdapter {

    private final OrtSession session;
    private final Tokenizer tokenizer;  // 使用 DJL 或 SentencePiece

    @PostConstruct
    public void init() throws OrtException {
        OrtEnvironment env = OrtEnvironment.getEnvironment();
        session = env.createSession("models/bge-m3.onnx");
        tokenizer = new SentencePieceTokenizer("models/bge-m3.vocab");
    }

    @Override
    public float[] embed(String text) {
        // Tokenize
        long[] tokens = tokenizer.encode(text);
        
        // ONNX 推理
        OrtSession.Result result = session.run(
            Map.of("input_ids", OnnxTensor.createTensor(env, tokens)));
        
        // 提取向量
        float[][] embeddings = (float[][]) result.get(0).getValue();
        return embeddings[0];
    }

    @Override
    public List<float[]> embedBatch(List<String> texts) {
        // 批量推理
        return texts.stream().map(this::embed).toList();
    }
}
```

### 5.2 DJL (Deep Java Library) 方案

DJL 提供更简洁的 Java ML 集成：

```java
@Component
public class DjlEmbeddingModel implements EmbeddingAdapter {

    private final Criteria<String, float[]> criteria;

    @PostConstruct
    public void init() {
        criteria = Criteria.builder()
            .setTypes(String.class, float[].class)
            .optModelPath("models/bge-m3.pt")
            .optEngine("PyTorch")  // 或 ONNX
            .build();
    }

    @Override
    public float[] embed(String text) {
        try (ZooModel<String, float[]> model = criteria.loadModel()) {
            Predictor<String, float[]> predictor = model.newPredictor();
            return predictor.predict(text);
        }
    }
}
```

---

## 6. 部署架构

### 6.1 容器化部署

```yaml
# docker-compose.yml
version: '3.8'

services:
  # Java API 服务
  api:
    build: 
      context: ./backend-java
      dockerfile: Dockerfile
    ports:
      - "8080:8080"
    environment:
      - SPRING_PROFILES_ACTIVE=prod
      - QDRANT_HOST=qdrant
      - NEO4J_URI=bolt://neo4j:7687
      - RABBITMQ_HOST=rabbitmq
      - REDIS_HOST=redis
      - POSTGRES_HOST=postgres
    depends_on:
      - qdrant
      - neo4j
      - rabbitmq
      - redis
      - postgres
      - ocr-service

  # OCR 微服务（Python）
  ocr-service:
    build: ./ocr-service
    ports:
      - "8001:8001"
    environment:
      - OCR_MODEL=paddleocr

  # Qdrant 向量数据库
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant-data:/qdrant/storage

  # PostgreSQL
  postgres:
    image: postgres:16
    environment:
      - POSTGRES_DB=offer_catcher
      - POSTGRES_USER=root
      - POSTGRES_PASSWORD=root
    volumes:
      - postgres-data:/var/lib/postgresql/data

  # Neo4j
  neo4j:
    image: neo4j:5-community
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/password

  # RabbitMQ
  rabbitmq:
    image: rabbitmq:3-management
    ports:
      - "5672:5672"
      - "15672:15672"

  # Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  qdrant-data:
  postgres-data:
```

### 6.2 Spring Boot 配置

```yaml
# application.yml
spring:
  application:
    name: offer-catcher-api
  
  # WebFlux 配置
  webflux:
    base-path: /api/v1
  
  # PostgreSQL
  r2dbc:
    url: r2dbc:postgresql://${POSTGRES_HOST:localhost}:5432/offer_catcher
    username: ${POSTGRES_USER:root}
    password: ${POSTGRES_PASSWORD:root}
  
  # Neo4j
  neo4j:
    uri: ${NEO4J_URI:bolt://localhost:7687}
    authentication:
      username: ${NEO4J_USER:neo4j}
      password: ${NEO4J_PASSWORD:neo4j}
  
  # Redis
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: 6379
  
  # RabbitMQ
  rabbitmq:
    host: ${RABBITMQ_HOST:localhost}
    port: 5672
    username: guest
    password: guest

# 自定义配置
offercatcher:
  qdrant:
    host: ${QDRANT_HOST:localhost}
    port: 6333
    collection: questions
    vector-size: 1024
  
  embedding:
    model-path: models/bge-m3.onnx
    device: cpu
  
  reranker:
    model-path: models/bge-reranker-base.onnx
  
  llm:
    default-provider: deepseek
    deepseek:
      api-key: ${DEEPSEEK_API_KEY}
      model: deepseek-chat
    openai:
      api-key: ${OPENAI_API_KEY}
      model: gpt-4
  
  memory:
    retrieval-top-k: 5
    decay-rate: 0.1
  
  interview:
    max-follow-ups: 3
  
  ocr:
    service-url: ${OCR_SERVICE_URL:http://ocr-service:8001}

# Observability
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  prometheus:
    metrics:
      export:
        enabled: true
```

---

## 7. 迁移路径规划

### 7.1 阶段划分

| 阶段 | 内容 | 预估周期 |
|------|------|----------|
| **Phase 1** | 基础框架搭建 + Domain 层迁移 | 2 周 |
| **Phase 2** | Infrastructure 层（Qdrant/Postgres/Redis） | 2 周 |
| **Phase 3** | Infrastructure 层（Neo4j/RabbitMQ/Embedding） | 2 周 |
| **Phase 4** | Application 层 Services | 2 周 |
| **Phase 5** | Agent Framework + Chat Workflow | 3 周 |
| **Phase 6** | Workers + OCR 微服务 | 1 周 |
| **Phase 7** | API 层 + SSE Streaming | 1 周 |
| **Phase 8** | 集成测试 + 性能调优 | 2 周 |
| **Phase 9** | 前端适配 + 上线部署 | 1 周 |

**总计：约 14 周（3.5 个月）**

### 7.2 Phase 1: 基础框架

**目标：**
- Spring Boot 3.4 + WebFlux 项目初始化
- Domain 层所有聚合根、枚举、值对象迁移
- Repository Interface 定义

**产出：**
```
offer-catcher-java/
├── pom.xml
├── src/main/java/com/offercatcher/
│   ├── domain/
│   │   ├── question/
│   │   ├── memory/
│   │   ├── interview/
│   │   ├── chat/
│   │   ├── favorite/
│   │   └── shared/
│   └── Application.java
```

### 7.3 Phase 2-3: Infrastructure 层

**目标：**
- 所有 Repository 实现
- 外部适配器（LLM、Embedding、Reranker）
- 配置类、连接池

**关键技术点：**
- ONNX 模型导出与 Java 推理
- Qdrant Java Client gRPC 接口
- Neo4j Cypher 查询迁移

### 7.4 Phase 4: Application Services

**目标：**
- 所有 Service 类迁移
- 事件处理机制

**注意：**
- Python 的 `fire-and-forget` 模式用 `@Async` 实现
- Circuit Breaker 用 Resilience4j

### 7.5 Phase 5: Agent Framework

**核心挑战：**
- LangGraph 状态机迁移为自研 Workflow
- Checkpointer 实现（PostgreSQL）
- 节点/边/路由条件迁移

**设计要点：**
- 使用 Reactive Streams 实现流式输出
- 状态持久化使用 R2DBC PostgreSQL

### 7.6 Phase 6: Workers

**目标：**
- RabbitMQ Consumers 迁移
- OCR 微服务独立部署

**OCR 微服务设计：**
```python
# ocr-service/main.py
from fastapi import FastAPI
from paddleocr import PaddleOCR

app = FastAPI()
ocr = PaddleOCR(use_angle_cls=True, lang="ch")

@app.post("/extract")
async def extract(image: UploadFile):
    result = ocr.ocr(image.file.read())
    return {"text": result}
```

### 7.7 Phase 7: API 层

**目标：**
- 所有 Controller 实现
- SSE Streaming 响应
- OpenAPI 文档

**流式响应关键代码：**
```java
@PostMapping("/stream")
public Flux<String> stream(@RequestBody Request req) {
    return service.stream(req)
        .map(event -> "data: " + toJson(event) + "\n\n");
}
```

### 7.8 Phase 8: 测试与调优

**测试策略：**
- Domain 层：纯 Java 单元测试（JUnit 5）
- Infrastructure 层：集成测试（Testcontainers）
- Application 层：Mock LLM/Embedding
- API 层：WebTestClient

**性能调优：**
- ONNX 推理线程池
- Qdrant 批量操作
- Redis 连接池
- JVM 参数调优

---

## 8. 风险与对策

### 8.1 技术风险

| 风险 | 影响 | 对策 |
|------|------|------|
| ONNX 模型导出失败 | Embedding 无法本地推理 | 使用 DJL + PyTorch 原生加载 |
| Agent Workflow 复杂度高 | 开发周期延长 | 先实现核心流程，逐步迭代 |
| OCR Java 生态不成熟 | OCR 功能受限 | Python 独立微服务 |
| Qdrant Java Client 文档不足 | 接口调试困难 | 参考 Python 源码，官方 gRPC |

### 8.2 业务风险

| 风险 | 影响 | 对策 |
|------|------|------|
| 迁移期间服务中断 | 用户无法使用 | 分模块迁移，保持 Python 服务运行 |
| 数据迁移丢失 | 历史数据丢失 | 先导出 Qdrant/Postgres 数据，再导入 |
| 前端兼容问题 | API 响应格式变化 | 保持 DTO 结构一致 |

---

## 9. 附录

### 9.1 依赖清单

```xml
<!-- pom.xml -->
<dependencies>
    <!-- Spring Boot -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    
    <!-- Spring Data Neo4j -->
    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-neo4j-rx</artifactId>
    </dependency>
    
    <!-- Qdrant Client -->
    <dependency>
        <groupId>io.qdrant</groupId>
        <artifactId>client</artifactId>
        <version>1.0.0</dependency>
    </dependency>
    
    <!-- ONNX Runtime -->
    <dependency>
        <groupId>com.microsoft.onnxruntime</groupId>
        <artifactId>onnxruntime</artifactId>
        <version>1.16.0</version>
    </dependency>
    
    <!-- DJL (可选) -->
    <dependency>
        <groupId>ai.djl</groupId>
        <artifactId>api</artifactId>
    </dependency>
    
    <!-- Spring AI -->
    <dependency>
        <groupId>org.springframework.ai</groupId>
        <artifactId>spring-ai-openai-spring-boot-starter</artifactId>
    </dependency>
    
    <!-- Resilience4j -->
    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-circuitbreaker</artifactId>
    </dependency>
    
    <!-- Micrometer -->
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
    
    <!-- R2DBC PostgreSQL -->
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>r2dbc-postgresql</artifactId>
    </dependency>
</dependencies>
```

### 9.2 关键类映射表

| Python | Java |
|--------|------|
| `Question` (Pydantic) | `Question` (Java Bean) |
| `QuestionRepository` (Protocol) | `QuestionRepository` (Interface) |
| `QdrantQuestionRepository` | `QdrantQuestionRepositoryImpl` |
| `EmbeddingAdapter` | `OnnxEmbeddingModel` |
| `ChatWorkflow` (LangGraph) | `ChatWorkflow` (自研) |
| `Checkpointer` | `PostgresCheckpointer` |
| `MQTaskMessage` | `MQTaskMessage` (Java Record) |
| `AgentState` (TypedDict) | `AgentState` (Java Class) |

---

## 10. 总结

本方案将 Offer-Catcher 从 Python FastAPI + LangGraph 重构为 Java Spring Boot 3.4 + WebFlux：

**核心设计决策：**
1. **DDD 架构保持不变**：四层分层、依赖倒置、聚合根设计
2. **LangGraph 替换为自研 Workflow**：状态机 + Checkpointer 模式
3. **Embedding/OCR 分离**：ONNX Runtime + Python 微服务
4. **Reactive Streams**：WebFlux 实现流式响应
5. **可观测性**：Micrometer + OpenTelemetry

**预估工期：3.5 个月**

**关键挑战：**
- Agent Framework 自研
- ONNX 模型导出与推理
- OCR 微服务独立部署

**收益：**
- JVM 性能与稳定性
- Spring Boot 生态成熟度
- 企业级部署友好