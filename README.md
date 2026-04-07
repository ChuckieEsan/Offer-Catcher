# 📄 Offer-Catcher: 面经复习与对练 Agent 产品设计文档 (PRD)

**文档版本**：v1.1
**目标用户**：AI Agent / LLM 应用开发求职者
**核心定位**：基于 Multi-Agent 架构与混合 RAG 的高并发面经收集、结构化图谱分析与智能对练系统。

---

## 一、 产品背景与核心价值 (Background & Value)

### 1.1 痛点分析
当前求职者在复习”大模型/Agent开发”面经时面临三大痛点：
1. **数据非结构化与噪音大**：小红书/牛客网面经多为长截图，包含大量寒暄废话，难以提取结构化考点。
2. **缺乏时效性与标准答案**：LLM 技术迭代极快（如 MCP、Agentic RAG 等），依靠死记硬背或大模型幻觉生成的答案往往是过时或错误的。
3. **缺乏宏观统计与个性化追踪**：无法得知”字节最近最爱考什么”，也无法追踪自己对某道题的掌握程度（熟练度状态机缺失）。

### 1.2 核心价值与解决方案
* **多模态与分类熔断提取**：支持图文混排输入，利用 Vision LLM 进行结构化提取，并对题目进行智能分类（knowledge/project/behavioral/scenario/algorithm），过滤无效生成。
* **消息队列与 Multi-Agent 异步答疑**：引入 RabbitMQ 削峰填谷，由主 Agent 调度带联网搜索（Web Search）能力的子 Agent 异步生成最新标准答案。
* **混合存储架构 (Hybrid Storage)**：Qdrant 向量库（支撑细粒度混合检索） + Neo4j 图数据库（支撑宏观考频统计与知识点关联分析）。

---

## 二、 系统架构设计 (System Architecture)

系统采用 **”读写分离、主从智能体解耦、消息驱动”** 的微服务级架构。

```text
[ 输入层 ] (文本 / 本地图片路径)
       |
       v
+---------------------------------------------------+
|  1. 视觉与提取层 (Vision Extractor)               |
|  - 多模态 JSON 结构化提取                         |
|  - 静态词表对齐 (如 “鹅厂” -> “腾讯”)             |
|  - 意图分类熔断 (knowledge/project/behavioral/    |
|                   scenario/algorithm)            |
+---------------------------------------------------+
       | (拆分为单题粒度 JSON)
       |
       +-------------------[ 双写路由 ]-------------------+
       |                                                  |
       v                                                  v
[ 2. 异步答疑子系统 ]                              [ 3. 图谱统计子系统 ]
       |                                                  |
+--------------------+                            +--------------------+
| RabbitMQ (Task Q)  |                            |   Neo4j Graph DB   |
| 削峰填谷、防止限流 |                            | 考频统计与关联分析  |
+--------------------+                            +--------------------+
       |                                                  ^
       v                                                  |
+--------------------+                            +--------------------+
| Web Search Agent   |                            |   热门考点查询      |
| (联网检索最新答案) |                            |   知识点关联分析    |
+--------------------+                            |   跨公司通用考点    |
       |                                                  |
       | (写回/更新答案)                                   |
       v                                                  |
+---------------------------------------------------+
|  4. 向量检索底座 (Vector Database - Qdrant)       |
|  - Question-Level Embedding (上下文拼接策略)      |
|  - Payload 索引建立 (公司、岗位、掌握程度)        |
|  - Deterministic ID (MD5 主键保证 Upsert 一致性)  |
+---------------------------------------------------+
       |
       v
+---------------------------------------------------+
|  5. 智能评分与练习 (Scorer Agent)                 |
|  - 用户答案评分 (0-100)                           |
|  - 熟练度状态机 (LEVEL_0 -> LEVEL_1 -> LEVEL_2)  |
|  - 优点与改进建议生成                             |
+---------------------------------------------------+
```

---

## 三、 核心数据流转设计 (Data Pipeline)

### 3.1 数据总线协议 (Data Schema)
Vision Extractor 输出的 JSON 为全系统数据总线。关键设计在于 **`question_type` (题目分类)** 和 **`requires_async_answer` (是否需要异步答疑)**。

```json
{
  “source_type”: “image”,
  “company”: “字节跳动”,
  “position”: “Agent应用开发”,
  “questions”:[
    {
      “question_id”: “md5(字节跳动+qlora优化显存)”,
      “question_text”: “qlora怎么优化显存？”,
      “question_type”: “knowledge”,
      “requires_async_answer”: true,
      “core_entities”:[“qlora”, “显存优化”, “模型微调”],
      “mastery_level”: 0
    },
    {
      “question_id”: “md5(字节跳动+项目拷打)”,
      “question_text”: “讲讲你的 Agent 项目？”,
      “question_type”: “project”,
      “requires_async_answer”: false,
      “core_entities”: [“项目经历”],
      “mastery_level”: 0
    }
  ]
}
```

### 3.2 题目类型说明

| 类型 | 描述 | 异步生成答案 |
|------|------|-------------|
| `knowledge` | 客观基础题（八股文） | ✅ |
| `project` | 项目深挖题 | ❌ |
| `behavioral` | 行为/软技能题 | ❌ |
| `scenario` | 场景题 | ✅ |
| `algorithm` | 算法题（Leetcode） | ✅ |

### 3.3 异步削峰答疑流 (RabbitMQ + Web Search Agent)
1. **入队 (Producer)**：系统解析出 N 道题，筛选出 `requires_async_answer == true` 的题目。打包完整的上下文（公司+题目）发送至 RabbitMQ。
2. **消费 (Consumer)**：后台 Worker 匀速消费队列，支持断路器与降级机制。
3. **联网检索与生成**：Worker 唤醒 `Answer_Specialist_Agent`，调用 Web Search 获取最新资料，生成结构化标准答案。
4. **失败重试**：若大模型 API 触发限流，消息重新入队或进入死信队列（DLQ）。
5. **落库更新 (Upsert)**：利用确定性 MD5 ID，将标准答案更新至 Qdrant 中对应的 Payload 字段。

### 3.4 存储底层设计 (Qdrant Schema)
* **Embedding 策略**：Context Enrichment。将 `”公司：字节跳动 | 岗位：Agent应用开发 | 题目：qlora怎么优化显存？”` 作为整体计算向量。
* **Payload 索引**：为 `company`, `mastery_level`, `question_type` 建立标量索引，支撑百万级数据下的毫秒级混合检索。

---

## 四、 项目开发排期与版本规划 (Roadmap)

### 🟢 Phase 1: MVP 核心数据流 —— **已完成**
* **目标**：跑通”提取 -> 分类 -> 入库 -> 异步生成 -> 存储”的后端全链路
* **已完成功能**：
  1. Vision Extractor 多模态 JSON 结构化提取
  2. Qdrant 向量库 + 混合检索
  3. RabbitMQ 异步队列 + 断路器机制
  4. Web Search Agent 联网生成答案
  5. Streamlit Web 界面

### 🟢 Phase 2: 高级特性与业务闭环 —— **已完成**
* **已完成功能**：
  1. **图数据库接入**：Neo4j 考频统计、知识点关联分析、跨公司通用考点
  2. **打分 Agent 与状态机**：`mastery_level` (0/1/2) 评判逻辑
  3. **答案复用机制**：相似题目自动复用已有答案（节省 Token）
  4. **意图路由 Agent**：用户输入意图分类
  5. **LangGraph 工作流**：基于 LangGraph 的 ReAct 模式，支持流式输出
  6. **会话管理**：Redis 短期记忆 + PostgreSQL 历史对话
  7. **组件缓存优化**：LLM、Prompt、Agent 实例缓存，避免重复创建
  8. **多页面 Streamlit UI**：聊天、录入、练习、管理、仪表盘

### 🔵 Phase 3: 未来规划
- 微信/Telegram Webhook 接入
- Redis 语义缓存优化
- 用户认证与数据隔离

---

## 五、 🌟 面试高光抓手 (Interview Flashpoints)

1. **为什么引入 RabbitMQ？而不是直接协程并发？**
   > 面经往往是批量的（如一次解析 50 题）。若直接在代码里开协程调用大模型生成答案，极易触发下游厂商的 API Rate Limit。引入 RabbitMQ 实现了**流量削峰填谷**与**失败重试（DLQ）机制**。

2. **如何解决 Agent 答题的”幻觉”与针对个人简历的”乱答”？**
   > 采用**基于 LLM 意图的前置分类熔断机制**。对于 knowledge/scenario/algorithm 类型，调度带联网工具的子 Agent 生成最新答案；对于 project/behavioral 类型，直接触发熔断不予生成。

3. **Qdrant 向量库的数据粒度是如何设计的？**
   > 抛弃粗暴的 Document-level 切分，采用 **Question-level Chunking + 上下文拼接** 策略，结合 Qdrant Payload 标量索引实现 Pre-filtering + 向量比对的混合检索。

4. **图数据库在面试场景中的价值？**
   > 通过 Neo4j 实现**考频统计**（各公司热门考点）、**知识点关联分析**（常一起考察的知识点）、**跨公司通用考点**识别。

---

## 六、项目结构

```
offer_catcher/
├── app/
│   ├── agents/                 # 智能体层
│   │   ├── base.py           # Agent 基类（LLM调用、重试、Structured Output）
│   │   ├── chat_agent.py     # 聊天 Agent（流式输出、会话管理）
│   │   ├── vision_extractor.py # 视觉提取 Agent
│   │   ├── router.py         # 意图路由 Agent
│   │   ├── scorer.py         # 答题评分 Agent
│   │   ├── answer_specialist.py # 异步答案生成 Agent
│   │   └── graph/            # LangGraph 工作流
│   │       ├── state.py      # 状态定义
│   │       ├── nodes.py      # 节点实现
│   │       ├── edges.py      # 边（路由逻辑）
│   │       └── workflow.py   # 工作流组装
│   │
│   ├── tools/                # 工具箱
│   │   ├── embedding_tool.py # 向量嵌入工具 (BGE-M3)
│   │   ├── web_search_tool.py # 联网搜索工具 (Tavily)
│   │   ├── search_question_tool.py # 题目搜索工具
│   │   ├── vision_extractor_tool.py # 图片提取工具
│   │   └── query_graph_tool.py # 图数据库查询工具
│   │
│   ├── pipelines/            # 业务流水线
│   │   ├── ingestion.py     # 入库流水线
│   │   └── retrieval.py       # 检索流水线
│   │
│   ├── db/                   # 数据库层
│   │   ├── qdrant_client.py  # Qdrant 向量数据库客户端
│   │   ├── graph_client.py   # Neo4j 图数据库客户端
│   │   ├── redis_client.py   # Redis 短期记忆客户端
│   │   └── postgres_client.py # PostgreSQL 历史对话客户端
│   │
│   ├── mq/                   # 消息队列层
│   │   ├── producer.py       # RabbitMQ 生产者
│   │   ├── consumer.py        # RabbitMQ 异步消费者（带熔断）
│   │   ├── thread_pool_consumer.py # 线程池消费者
│   │   └── message_helper.py # MQ 消息处理辅助类
│   │
│   ├── models/               # 数据模型
│   │   ├── schemas.py        # Pydantic 模型
│   │   └── enums.py          # 枚举类
│   │
│   ├── prompts/              # Prompt 模板（外置）
│   │   ├── vision_extractor.md
│   │   ├── answer_specialist.md
│   │   ├── router.md
│   │   ├── scorer.md
│   │   ├── react_agent.md    # ReAct Agent 系统提示词
│   │   └── chat_agent.md     # Chat Agent 系统提示词
│   │
│   ├── skills/               # Skills 加载器
│   │   └── __init__.py       # 加载 SKILL.md 文件
│   │
│   ├── services/             # 业务服务
│   │   └── clustering_service.py # 题目聚类服务
│   │
│   ├── llm/                  # LLM 工厂模块
│   │   └── __init__.py       # create_llm, get_llm (带缓存)
│   │
│   ├── config/               # 配置
│   │   └── settings.py       # Pydantic Settings
│   │
│   └── utils/                # 工具
│       ├── hasher.py         # MD5 哈希工具
│       ├── logger.py         # 日志工具
│       ├── retry.py         # 重试装饰器
│       ├── circuit_breaker.py # 熔断器
│       ├── cache.py         # 通用缓存装饰器
│       ├── agent.py         # Agent 通用工具
│       ├── ocr.py           # OCR 工具
│       └── image.py         # 图片处理工具
│
├── workers/                   # 后台进程
│   ├── answer_worker.py     # 异步答案生成 Worker
│   └── clustering_worker.py # 聚类定时任务 Worker
│
├── gateways/                 # 接入层
│   ├── cli_chat.py         # Streamlit 主入口
│   └── pages/              # Streamlit 多页面
│       ├── 0_chat.py         # AI 聊天
│       ├── 1_interview_input.py # 录入面经
│       ├── 2_practice.py      # 练习答题
│       ├── 3_question_management.py # 题目管理
│       ├── 4_dashboard.py     # 仪表盘
│       └── 5_cluster_view.py  # 考点聚类
│
├── scripts/                  # 脚本
│   ├── resend_to_queue.py  # 重新发送任务到队列
│   ├── import_qdrant.py    # 导入数据到 Qdrant
│   └── export_qdrant.py    # 导出 Qdrant 数据
│
├── tests/                    # 测试用例
│   ├── test_qdrant_client.py
│   ├── test_graph_client.py
│   ├── test_vision_extractor.py
│   ├── test_scorer.py
│   ├── test_router.py
│   ├── test_tools.py
│   ├── test_answer_worker.py
│   ├── test_e2e.py
│   └── test_schemas.py
│
└── pyproject.toml            # 项目配置
```

### 技术栈

- **Python 3.10+** - 核心语言
- **Qdrant** - 向量数据库
- **Neo4j** - 图数据库
- **Redis** - 短期记忆存储
- **PostgreSQL** - 历史对话存储
- **RabbitMQ** - 消息队列
- **LangChain** - Agent 开发框架
- **LangGraph** - 工作流编排框架
- **DashScope/DeepSeek** - 大模型
- **Streamlit** - Web UI 框架
- **Tavily** - Web 搜索 API
- **OpenTelemetry** - 可观测性（全链路追踪、Metrics）
- **Jaeger** - Trace 可视化（本地开发）

---

## 九、快速开始 (Quick Start)

### 环境要求

- Python 3.10+
- Docker (用于运行 Qdrant、RabbitMQ、Neo4j、Redis、PostgreSQL)
- uv (包管理工具)

### 1. 启动依赖服务

```bash
# 启动所有依赖服务 (Qdrant, RabbitMQ, Neo4j, Redis, PostgreSQL, Jaeger)
docker-compose up -d

# 验证服务启动
# Qdrant: http://localhost:6333
# RabbitMQ: http://localhost:15672 (guest/guest)
# Neo4j: http://localhost:7474 (neo4j/neo4j)
# Redis: localhost:6379
# PostgreSQL: localhost:5432 (root/root)
# Jaeger (可选): http://localhost:16686
```

### 2. 配置环境变量

```bash
# 复制并编辑 .env 文件
cp .env.example .env
# 编辑 .env 填入你的 API Keys
```

### 3. 启动异步 Worker（后台运行）

```bash
# 启动 RabbitMQ Consumer，处理异步答案生成任务
PYTHONPATH=. uv run python workers/answer_worker.py &

# 启动聚类定时任务（每天凌晨 2 点执行）
PYTHONPATH=. uv run python workers/clustering_worker.py

# 立即执行一次聚类
PYTHONPATH=. uv run python workers/clustering_worker.py --run-now
```

### 4. 启动 Web 界面

```bash
# 启动 Streamlit Web 界面
PYTHONPATH=. uv run streamlit run gateways/cli_chat.py --server.port 8501
```

然后在浏览器访问 http://localhost:8501

### 功能说明

- **💬 AI 聊天**：智能对话，支持流式输出，自动识别意图（搜索/录入/闲聊），会话历史持久化
- **📝 录入面经**：输入文本或上传图片，自动提取题目并入库，触发异步答案生成
- **📝 练习答题**：选择题目提交答案，AI 评分并给出改进建议
- **📋 题目管理**：查看所有题目，编辑修改，删除
- **📊 仪表盘**：数据统计图表 + 图数据库考频分析
- **🏷️ 考点聚类**：自动聚类相似题目，发现高频考点

---

## 八、可观测性 (Observability)

本项目集成 OpenTelemetry 实现全链路追踪和 Metrics 收集。

### 启用方式

1. 在 `.env` 中启用：
   ```bash
   TELEMETRY_ENABLED=true
   OTLP_ENDPOINT=http://localhost:4317
   ```

2. 启动 Jaeger（本地开发）：
   ```bash
   docker-compose up -d jaeger
   ```

3. 访问 Jaeger UI：http://localhost:16686

### 收集的指标

| 指标 | 类型 | 说明 |
|------|------|------|
| `tool.calls.total` | Counter | 工具调用次数（成功/失败） |
| `tool.calls.duration` | Histogram | 工具调用时长 (ms) |
| `tool.calls.errors` | Counter | 工具调用错误数 |
| `llm.tokens.input` | Counter | LLM 输入 Token 消耗 |
| `llm.tokens.output` | Counter | LLM 输出 Token 消耗 |
| `llm.calls.duration` | Histogram | LLM 调用时长 (ms) |
| `vector.query.duration` | Histogram | 向量检索时长 |
| `vector.query.results` | Histogram | 向量检索结果数 |

### 装饰器使用

```python
from app.utils.telemetry import traced, traced_async

@traced  # 同步函数追踪
def search_questions(query: str) -> str:
    ...

@traced_async  # 异步函数追踪
async def react_loop_node(state, config):
    ...
```

---

## 十、开发指南

### 运行测试

```bash
# 运行所有测试
uv run pytest tests/ -v

# 运行特定测试
uv run pytest tests/test_qdrant_client.py -v

# 测试会使用独立的测试 collection，不影响生产数据
```

### 测试文件说明

| 测试文件 | 说明 |
|----------|------|
| test_qdrant_client.py | 使用 `questions_test` collection |
| test_graph_client.py | 使用生产 Neo4j，测试后自动清理 |
| test_vision_extractor.py | 调用真实 LLM API |
| test_scorer.py | 调用真实 LLM API + Qdrant 只读 |
| test_router.py | 调用真实 LLM API |
