# 📄 Offer-Catcher: 面经复习与对练 Agent 产品设计文档 (PRD)

**文档版本**：v1.0 (MVP)
**目标用户**：AI Agent / LLM 应用开发求职者
**核心定位**：基于 Multi-Agent 架构与混合 RAG 的高并发面经收集、结构化图谱分析与智能对练系统。

---

## 一、 产品背景与核心价值 (Background & Value)

### 1.1 痛点分析
当前求职者在复习“大模型/Agent开发”面经时面临三大痛点：
1. **数据非结构化与噪音大**：小红书/牛客网面经多为长截图，包含大量寒暄废话，难以提取结构化考点。
2. **缺乏时效性与标准答案**：LLM 技术迭代极快（如 MCP、Agentic RAG 等），依靠死记硬背或大模型幻觉生成的答案往往是过时或错误的。
3. **缺乏宏观统计与个性化追踪**：无法得知“字节最近最爱考什么”，也无法追踪自己对某道题的掌握程度（熟练度状态机缺失）。

### 1.2 核心价值与解决方案
* **多模态与分类熔断提取**：支持图文混排输入，利用 Vision LLM 进行结构化提取，并对题目进行智能分类（客观八股/项目深挖），过滤无效生成。
* **消息队列与 Multi-Agent 异步答疑**：引入 RabbitMQ 削峰填谷，由主 Agent 调度带联网搜索（Web Search）能力的子 Agent 异步生成最新标准答案。
* **混合存储架构 (Hybrid Storage)**：Qdrant 向量库（支撑细粒度混合检索） + 图数据库（支撑宏观考频统计）。

---

## 二、 系统架构设计 (System Architecture)

系统采用 **“读写分离、主从智能体解耦、消息驱动”** 的微服务级架构。

```text
[ 输入层 ] (文本 / 本地图片路径)
       |
       v
+---------------------------------------------------+
|  1. 视觉与提取层 (Vision Extractor)               |
|  - 多模态 JSON 结构化提取                         |
|  - 静态词表对齐 (如 "鹅厂" -> "腾讯")             |
|  - 意图分类熔断 (Knowledge / Project / Behavioral)|
+---------------------------------------------------+
       | (拆分为单题粒度 JSON)
       |
       +-------------------[ 双写路由 ]-------------------+
       |                                                  |
       v                                                  v[ 2. 异步答疑子系统 (Async Answering) ]        [ 3. 图谱统计子系统 ]
       |                                                  |
+--------------------+                            +--------------------+
| RabbitMQ (Task Q)  |                            |   Graph Database   |
| 削峰填谷、防止限流 |                            | (Neo4j / NetworkX) |
+--------------------+                            +--------------------+
       | (消费 Task: 包含完整元数据)                      ^
       v                                                  | 每日凌晨 3 点
+--------------------+                            +--------------------+
| Web Search Agent   |                            |   Nightly Batch    |
| (联网检索最新答案) |                            |  (离线实体消歧合并)|
+--------------------+                            +--------------------+
       | 
       | (写回/更新答案)
       v
+---------------------------------------------------+
|  4. 向量检索底座 (Vector Database - Qdrant)       |
|  - Question-Level Embedding (上下文拼接策略)      |
|  - Payload 索引建立 (公司、岗位、掌握程度)        |
|  - Deterministic ID (MD5 主键保证 Upsert 一致性)  |
+---------------------------------------------------+
```

---

## 三、 核心数据流转设计 (Data Pipeline) —— MVP 核心重点

### 3.1 数据总线协议 (Data Schema)
Vision Extractor 输出的 JSON 为全系统数据总线。关键设计在于 **`question_type` (题目分类)** 和 **`requires_async_answer` (是否需要异步答疑)**。

```json
{
  "source_type": "image",
  "company": "字节跳动",
  "position": "Agent应用开发",
  "questions":[
    {
      "question_id": "md5(字节跳动+qlora优化显存)",
      "question_text": "qlora怎么优化显存？",
      "question_type": "knowledge",
      "requires_async_answer": true,
      "core_entities":["qlora", "显存优化", "模型微调"],
      "mastery_level": 0
    },
    {
      "question_id": "md5(字节跳动+项目拷打)",
      "question_text": "讲讲你的 Agent 项目？",
      "question_type": "project",
      "requires_async_answer": false,
      "core_entities": ["项目经历"],
      "mastery_level": 0
    }
  ]
}
```

### 3.2 异步削峰答疑流 (RabbitMQ + Web Search Agent)
1. **入队 (Producer)**：系统解析出 50 道题，筛选出 `requires_async_answer == true` 的 40 道客观题。打包完整的上下文（公司+题目）发送至 RabbitMQ。
2. **消费 (Consumer)**：后台 Worker 匀速消费队列。
3. **联网检索与生成**：Worker 唤醒 `Answer_Specialist_Agent`，调用 Web Search 获取最新资料（防止大模型内部权重过时），生成结构化标准答案。
4. **失败重试**：若大模型 API 触发 `HTTP 429` 限流，Worker 发送 `Nack` 拒绝确认，消息重新入队或进入死信队列（DLX）。
5. **落库更新 (Upsert)**：利用确定性 MD5 ID，将标准答案更新至 Qdrant 中对应的 Payload 字段。

### 3.3 存储底层设计 (Qdrant Schema)
* **Embedding 策略**：Context Enrichment。将 `"公司：字节跳动 | 岗位：Agent应用开发 | 题目：qlora怎么优化显存？"` 作为整体计算向量，防止特征稀释。
* **Payload 索引**：为 `company`, `mastery_level`, `question_type` 建立标量索引，支撑百万级数据下的毫秒级混合检索（Hybrid Search）。

**Qdrant Payload 结构：**
```json
{
  "question_id": "md5哈希值",
  "question_text": "qlora怎么优化显存？",
  "company": "字节跳动",
  "position": "Agent应用开发",
  "mastery_level": 0,
  "question_type": "knowledge",
  "core_entities": ["qlora", "显存优化"],
  "question_answer": "生成的答案内容",
  "created_at": "2024-01-01T00:00:00"
}
```

---

## 四、 项目开发排期与版本规划 (Roadmap)

秉承敏捷开发思想，严格界定 MVP 边界，优先跑通核心数据飞轮。

### 🟢 Phase 1: MVP 核心数据流 (预计 1-2 周) —— **当前阶段目标**
* **目标**：跑通“提取 -> 分发 -> 异步生成 -> 存储”的后端全链路，脱离 UI 在本地终端运行。
* **任务清单**：
  1. 编写 Vision Extractor Prompt，完成多模态到 JSON 的结构化提取及智能分类。
  2. 搭建 Qdrant 本地环境，定义 Schema，实现带 Payload 的向量入库逻辑。
  3. 搭建 RabbitMQ，编写 Producer 和 Consumer 脚本，跑通异步队列。
  4. 封装 `Web_Search_Agent`，在 Worker 中调用并把答案写回 Qdrant。

### 🟡 Phase 2: 高级特性与业务闭环 (Post-MVP 规划)
* **任务清单**：
  1. **图谱接入**：部署本地图数据库，双写实体数据，实现每日凌晨大模型离线去重脚本（Nightly Batch Alignment）。
  2. **打分 Agent 与状态机**：引入 `mastery_level` (0/1/2) 评判逻辑，对比用户输入与 Qdrant 中的标准答案进行打分和流转。
  3. **语义缓存**：引入 Redis Semantic Cache 优化查询接口。
  4. **表现层接入**：集成 OpenClaw，打通微信/Telegram Webhook，实现最终的每日主动推题与交互。

---

## 五、 🌟 面试高光抓手 (Interview Flashpoints)

在简历书写或面试讲解时，请重点突出以下架构设计思考（Trade-offs）：

1. **为什么引入 RabbitMQ？而不是直接协程并发？**
   > 面经往往是批量的（如一次解析 50 题）。若直接在代码里开协程调用大模型生成答案，极易触发下游厂商的 API Rate Limit 导致数据丢失。引入 RabbitMQ 实现了**流量削峰填谷**与**失败重试（DLX）机制**，极大提升了系统在高并发场景下的鲁棒性。
2. **如何解决 Agent 答题的“幻觉”与针对个人简历的“乱答”？**
   > 采用了**基于 LLM 意图的前置分类熔断机制**。对于通用客观题，调度带联网工具的子 Agent 生成最新答案；对于“项目深挖”类极具特异性的问题，直接触发熔断不予生成，为系统节省了大量 Token 开销，并保证了知识库数据的纯净度。
3. **Qdrant 向量库的数据粒度是如何设计的？**
   > 抛弃了粗暴的 Document-level 切分，采用 **Question-level Chunking + 上下文拼接** 的策略，并结合 Qdrant 强大的 Payload 标量索引机制，实现了先条件过滤（Pre-filtering）再向量比对的高效混合检索（Hybrid Search）。

---

## 六、项目结构

```
offer_catcher/
├── app/
│   ├── agents/                 # 智能体层
│   │   ├── vision_extractor.py # 视觉提取 Agent
│   │   └── answer_specialist.py # 答题专员 Agent
│   │
│   ├── tools/                  # 工具箱
│   │   ├── embedding.py         # 向量嵌入工具
│   │   └── web_search.py        # 联网搜索工具
│   │
│   ├── pipelines/               # 业务流水线
│   │   ├── ingestion.py         # 入库流水线
│   │   └── retrieval.py         # 检索流水线
│   │
│   ├── db/                     # 数据库层
│   │   └── qdrant_client.py    # Qdrant 客户端
│   │
│   ├── mq/                     # 消息队列层
│   │   ├── producer.py         # RabbitMQ 生产者
│   │   └── consumer.py         # RabbitMQ 消费者
│   │
│   ├── models/                 # 数据模型
│   │   ├── schemas.py          # Pydantic 模型
│   │   └── enums.py            # 枚举类
│   │
│   ├── prompts/                # Prompt 模板
│   │   ├── vision_extractor.md
│   │   └── answer_specialist.md
│   │
│   ├── config/                 # 配置
│   │   └── settings.py
│   │
│   └── utils/                  # 工具
│       ├── hasher.py           # MD5 哈希工具
│       └── logger.py           # 日志工具
│
├── workers/                    # 后台进程
│   └── answer_worker.py        # 异步答案生成 Worker
│
├── gateways/                   # 接入层
│   └── cli_chat.py            # Streamlit Web 界面
│
├── tests/                      # 测试用例
└── pyproject.toml             # 项目配置
```

### 技术栈

- **Python 3.10+** - 核心语言
- **Qdrant** - 向量数据库
- **RabbitMQ** - 消息队列
- **LangChain** - Agent 开发框架
- **DashScope** - 阿里云大模型
- **Streamlit** - Web UI 框架

### 预留接口（Phase 2）

- `app/agents/router.py` - 意图路由 Agent
- `app/agents/scorer.py` - 打分 Agent
- `app/db/graph_client.py` - 图数据库客户端

---

## 七、快速开始 (Quick Start)

### 环境要求

- Python 3.10+
- Docker (用于运行 Qdrant 和 RabbitMQ)
- uv (包管理工具)

### 1. 启动依赖服务

```bash
# 启动 Qdrant 和 RabbitMQ
docker-compose up -d

# 验证服务启动
# Qdrant: http://localhost:6333
# RabbitMQ: http://localhost:15672 (guest/guest)
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
```

### 4. 启动 Web 界面

```bash
# 启动 Streamlit Web 界面
PYTHONPATH=. uv run streamlit run gateways/cli_chat.py --server.port 8501
```

然后在浏览器访问 http://localhost:8501

### 功能说明

- **📝 录入面经**：输入文本或上传图片，自动提取题目并入库，触发异步答案生成
- **🔍 搜索题目**：语义搜索 + 公司/熟练度过滤
- **📋 题目管理**：查看所有题目，编辑修改，删除
- **📊 仪表盘**：数据统计图表

---

## 八、开发指南

### 运行测试

```bash
# 运行所有测试
uv run pytest tests/ -v

# 运行特定测试
uv run pytest tests/test_qdrant_client.py -v
```

### 项目结构说明

- `app/agents/` - AI 智能体（Vision Extractor, Answer Specialist）
- `app/pipelines/` - 业务流水线（Ingestion, Retrieval）
- `app/db/` - 数据库客户端（Qdrant）
- `app/mq/` - 消息队列（Producer, Consumer）
- `app/tools/` - 工具（Embedding, Web Search）
- `workers/` - 后台 Worker
- `gateways/` - Web 入口（Streamlit）
- `tests/` - 测试用例
