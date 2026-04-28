# 项目 Skill 设计文档

本文档记录 Claude Code Skills 的设计方案，用于企业级 CI/CD 流程中的 AI Agent 自动化。

---

## 实现状态

**已实现 Skills（13个）**：位于 `.claude/skills/<name>/SKILL.md`

| Skill | 状态 | 分类 |
|-------|------|------|
| `/ddd-check` | ✅ 已实现 | 代码质量 |
| `/review-pr` | ✅ 已实现 | 代码质量 |
| `/prompt-check` | ✅ 已实现 | 代码质量 |
| `/qdrant-sync` | ✅ 已实现 | 代码质量 |
| `/security-scan` | ✅ 已实现 | 代码质量 |
| `/gen-tests` | ✅ 已实现 | 测试自动化 |
| `/agent-test` | ✅ 已实现 | 测试自动化 |
| `/deploy-check` | ✅ 已实现 | 部署运维 |
| `/mq-check` | ✅ 已实现 | 部署运维 |
| `/agent-debug` | ✅ 已实现 | 部署运维 |
| `/pitfall-learn` | ✅ 已实现 | 知识管理 |
| `/quick-fix` | ✅ 已实现 | 效率提升 |
| `/new-agent` | ✅ 已实现 | 效率提升 |

**待实现 Skills**：可在后续需要时添加

| Skill | 状态 | 分类 |
|-------|------|------|
| `/audit-pipeline` | 待实现 | 代码质量 |
| `/test-selector` | 待实现 | 测试自动化 |
| `/rollback-plan` | 待实现 | 部署运维 |
| `/health-check` | 待实现 | 部署运维 |
| `/update-docs` | 待实现 | 知识管理 |
| `/triage-issue` | 待实现 | 任务管理 |
| `/estimate-task` | 待实现 | 任务管理 |

---

## 设计原则

Skills 应遵循以下原则：

1. **聚焦不可自动化的部分** — CI pipeline 已有自动化测试、构建、部署，Skills 补充的是需要"判断"的环节
2. **触发器明确** — 每个 Skill 有清晰的触发场景，避免过度使用
3. **输出可验证** — Skill 输出应结构化，便于人工审核或集成到 CI gate
4. **持续学习** — 解决问题后可更新 `<pitfalls>`，形成闭环

---

## Skill 分类与设计

### 一、代码质量与审查类

#### `/ddd-check`

**描述**：检查当前分支是否符合 DDD 分层规则

**触发场景**：
- PR 提交前
- 修改 Domain/Application 层代码后

**执行内容**：
1. 扫描 `domain/` 目录下所有 import，检查是否有 `infrastructure` 或 `application` 引用
2. 检查 `domain/*/repositories.py` 是否为 Protocol（`@runtime_checkable`）
3. 检查 `infrastructure/persistence/` 是否有对应实现
4. 输出违规列表：文件路径 + 行号 + 违规类型

**输出格式**：
```
DDD Compliance Report
======================
✅ Domain Layer: 0 violations
❌ Infrastructure Layer: 2 violations
  - infrastructure/persistence/qdrant/question_repository.py:15
    Missing Protocol definition in domain/question/repositories.py
  - infrastructure/adapters/embedding_adapter.py:23
    Direct import from application layer detected

Recommended Actions:
1. Add Protocol definition for QuestionRepository
2. Move embedding logic to domain service
```

---

#### `/review-pr`

**描述**：自动审查 PR，聚焦架构合规与常见问题

**触发场景**：
- PR 创建或更新时
- 手动调用 `/review-pr <PR号>`

**执行内容**：
1. 获取 PR 变更文件列表
2. 对每个文件执行：
   - DDD 分层检查（调用 `/ddd-check` 子逻辑）
   - 类型标注检查（函数是否有 Type Hints）
   - Prompt 硬编码检查（是否有长字符串 prompt）
   - 安全漏洞检查（SQL 注入、XSS、命令注入模式）
   - 日志规范检查（是否有 `print()` 调用）
3. 汇总输出审查报告

**输出格式**：
```
PR #123 Review Report
=====================
Files Changed: 5

✅ domain/question/aggregates.py
  - Type hints complete
  - No violations

⚠️ application/agents/chat/agent.py
  - Line 45: Long prompt string detected (>200 chars)
    Recommendation: Move to prompts/system.md

❌ infrastructure/tools/query_graph.py
  - Line 23: Potential SQL injection (f-string in query)
  - Line 67: Missing try-except for Neo4j call

Summary: 2 critical issues, 1 warning
Recommendation: Do not merge until critical issues resolved
```

---

#### `/security-scan`

**描述**：扫描代码中的 OWASP Top 10 安全漏洞

**触发场景**：
- 新增 API endpoint 后
- 涉及外部输入处理（LLM API、Qdrant、MQ）时
- 定期安全审计

**执行内容**：
1. 扫描以下模式：
   - SQL 注入：f-string 构建 SQL
   - 命令注入：`subprocess` + 用户输入
   - XSS：未转义的 HTML 输出
   - 硬编码 Secrets：API key、password 在代码中
   - 不安全的反序列化：`pickle.loads`
   - SSRF：用户可控的 URL fetch
2. 检查 LLM API 调用是否有异常处理
3. 检查 Qdrant/MQ 连接是否有认证

**输出格式**：
```
Security Scan Report
====================
Critical: 1
  - api/routes/chat.py:34 - Command Injection
    User input passed to subprocess without validation

High: 2
  - infrastructure/adapters/llm_adapter.py:12 - Missing Exception Handling
    LLM API call without try-except
  - infrastructure/config/settings.py:8 - Hardcoded Secret
    API_KEY = "sk-xxx" exposed in code

Medium: 1
  - api/routes/search.py:56 - Potential SSRF
    User-provided URL used in WebFetch

Recommended Actions:
1. Validate and sanitize user input before subprocess
2. Add try-except with retry logic for LLM calls
3. Move secrets to environment variables
```

---

#### `/audit-pipeline`

**描述**：分析 CI pipeline 执行时间，识别瓶颈

**触发场景**：
- CI 时间超过 10 分钟时
- 季度 pipeline 审计

**执行内容**：
1. 获取最近 10 次 CI 运行记录（通过 GitHub API）
2. 分析各阶段耗时：install、test、build、deploy
3. 识别：
   - 串行执行的可并行步骤
   - 未使用缓存的依赖安装
   - 冗余测试（未变更文件的测试）
4. 输出优化建议

**输出格式**：
```
Pipeline Audit Report
=====================
Average Duration: 18m 32s
Target: < 10m

Bottleneck Analysis:
--------------------
1. Test Stage: 12m 45s (69% of total)
   - Full test suite runs on every PR
   - Recommendation: Use selective test triggering based on changed files

2. Install Dependencies: 3m 20s
   - No caching configured
   - Recommendation: Add uv cache action

3. Build Stage: 2m 07s
   - Sequential Docker builds
   - Recommendation: Use matrix strategy for parallel builds

Optimization Plan:
1. Implement test selector (estimated: -8m)
2. Add dependency caching (estimated: -2m)
3. Parallelize builds (estimated: -1m)

Expected Result: 7m 32s (-59%)
```

---

### 二、测试自动化类

#### `/gen-tests`

**描述**：为新增功能生成单元测试骨架

**触发场景**：
- 新增 domain aggregate、service、repository 后
- 手动调用 `/gen-tests <文件路径>`

**执行内容**：
1. 分析目标文件：
   - 识别类、方法、依赖项
   - 识别外部依赖（LLM、Qdrant、MQ）需 mock
2. 生成测试文件：
   - 遵循 DDD 分层，mock Infrastructure 层
   - 覆盖正常路径和异常路径
   - 使用 pytest 结构
3. 检查现有测试覆盖率，补充缺失场景

**输出格式**：
```python
# tests/domain/question/test_question_service.py
# Generated by Claude Code

import pytest
from unittest.mock import Mock, AsyncMock
from app.domain.question.services import QuestionService
from app.domain.question.repositories import QuestionRepository

class TestQuestionService:
    @pytest.fixture
    def mock_repo(self):
        return Mock(spec=QuestionRepository)
    
    @pytest.fixture
    def service(self, mock_repo):
        return QuestionService(repository=mock_repo)
    
    def test_create_question_success(self, service, mock_repo):
        # TODO: Implement test
        pass
    
    def test_create_question_duplicate_id(self, service, mock_repo):
        # TODO: Test MD5 collision handling
        pass
    
    async def test_async_operations(self, service, mock_repo):
        # TODO: Test async repository calls
        pass
```

---

#### `/test-selector`

**描述**：智能选择相关测试运行，减少 CI 时间

**触发场景**：
- PR 提交时自动触发
- 手动调用 `/test-selector --changed-files`

**执行内容**：
1. 分析 PR 变更文件
2. 构建依赖图：
   - 文件 → 导入的模块
   - 文件 → 测试文件映射
3. 选择：
   - 直接测试：变更文件的测试
   - 间接测试：依赖变更文件的模块的测试
4. 输出测试列表

**输出格式**：
```
Test Selection Report
=====================
Changed Files: 3
  - domain/question/aggregates.py
  - application/services/question_service.py
  - infrastructure/persistence/qdrant/question_repository.py

Selected Tests: 8
  Direct: 3
    - tests/domain/question/test_aggregates.py
    - tests/application/test_question_service.py
    - tests/infrastructure/qdrant/test_question_repository.py
  
  Indirect: 5
    - tests/application/test_ingestion_service.py (depends on question_service)
    - tests/api/test_questions_routes.py (depends on aggregates)
    - tests/application/agents/test_vision_extractor.py (uses Question)
    - tests/integration/test_question_flow.py
    - tests/application/workers/test_answer_worker.py

Skipped Tests: 45 (estimated time saved: 8m)
Command: pytest tests/domain/question/test_aggregates.py tests/application/test_question_service.py ...
```

---

#### `/agent-test`

**描述**：针对 AI Agent 的行为边界测试

**触发场景**：
- 新增或修改 Agent 后
- Agent prompt 变更后

**执行内容**：
1. 分析 Agent 定义：
   - 输入类型（HumanMessage、图片）
   - 工具列表（search_questions、search_web）
   - 输出约束（JSON schema、消息类型）
2. 生成测试场景：
   - 正常输入 → 验证输出格式
   - 边界输入（空、超长、异常格式）→ 验证 fallback
   - 工具调用 → 验证参数正确性
   - 并发调用 → 验证状态隔离
3. 检查非确定性输出边界

**输出格式**：
```python
# tests/application/agents/test_chat_agent.py
# Generated by Claude Code - Agent Behavior Tests

import pytest
from langchain_core.messages import HumanMessage, AIMessage
from app.application.agents.chat.agent import ChatAgent

class TestChatAgentBehavior:
    @pytest.fixture
    def agent(self):
        return ChatAgent()
    
    async def test_normal_input_returns_aimessage(self, agent):
        """正常输入应返回 AIMessage"""
        result = await agent.achat([HumanMessage(content="测试问题")])
        assert isinstance(result, AIMessage)
    
    async def test_empty_input_fallback(self, agent):
        """空输入应有 fallback 行为"""
        result = await agent.achat([HumanMessage(content="")])
        # Agent should not crash, return graceful response
        assert result.content is not None
    
    async def test_tool_call_parameters(self, agent):
        """工具调用参数应符合预期"""
        # Mock tools, verify parameters passed correctly
        pass
    
    async def test_concurrent_sessions_isolated(self, agent):
        """并发 session 状态应隔离"""
        # Create two sessions, verify no state leakage
        pass
```

---

### 三、部署与运维类

#### `/deploy-check`

**描述**：检查部署前置条件

**触发场景**：
- 合并到 main 分支后
- 手动调用 `/deploy-check --env staging`

**执行内容**：
1. 检查：
   - 环境变量完整性（对照 `settings.py`）
   - 配置一致性（staging vs production）
   - 数据库迁移脚本存在性
   - 依赖版本兼容性
2. 对比上次部署配置，识别差异
3. 检查 secrets 是否在环境变量中（非硬编码）

**输出格式**：
```
Deploy Pre-Check Report
=======================
Target: staging
Status: ❌ NOT READY

Missing Environment Variables:
  - OPENAI_API_KEY (required for llm_adapter)
  - QDRANT_URL (required for question_repository)
  - NEO4J_PASSWORD (required for graph queries)

Configuration Differences (vs last deploy):
  - QDRANT_COLLECTION: "questions_v1" → "questions_v2"
    ⚠️ Collection change may require data migration
  
  - EMBEDDING_MODEL: "text-embedding-3-small" → "text-embedding-3-large"
    ⚠️ Model change requires re-embedding all questions

Pending Migrations:
  - backend/migrations/003_add_user_table.sql (not executed)

Recommended Actions:
1. Set missing environment variables
2. Run migration script before deploy
3. Re-embed questions if embedding model changed
```

---

#### `/rollback-plan`

**描述**：生成 rollback 方案

**触发场景**：
- Production 部署前
- 手动调用 `/rollback-plan --version v1.2.3`

**执行内容**：
1. 记录：
   - 当前版本号、commit hash
   - 当前配置快照
   - 数据库状态（迁移版本）
2. 识别风险变更：
   - Schema 变更
   - 配置变更
   - 新依赖引入
3. 生成 rollback 步骤

**输出格式**：
```
Rollback Plan for v1.2.4
========================
Current Version: v1.2.3 (commit: a46b0bd)
Target Version: v1.2.4 (commit: fd66be3)

Risk Changes Identified:
------------------------
1. Schema Change: users table added
   Migration: backend/migrations/003_add_user_table.sql
   Rollback: backend/migrations/003_add_user_table.rollback.sql

2. Config Change: QDRANT_COLLECTION renamed
   Rollback: Restore QDRANT_COLLECTION to "questions_v1"

3. New Dependency: langgraph-checkpointer-postgres
   Rollback: Remove from pyproject.toml

Rollback Steps:
---------------
1. git checkout v1.2.3
2. git revert fd66be3
3. Run rollback migration:
   psql -f backend/migrations/003_add_user_table.rollback.sql
4. Restore environment variables:
   QDRANT_COLLECTION=questions_v1
5. Restart services:
   systemctl restart offer-catcher-api
   systemctl restart offer-catcher-worker
6. Verify rollback:
   curl http://localhost:8000/health

Estimated Rollback Time: 5 minutes
```

---

#### `/health-check`

**描述**：生成服务健康检查脚本

**触发场景**：
- 部署后验证
- 定期巡检

**执行内容**：
1. 根据项目配置生成检查项：
   - API 端点可达性
   - 数据库连接（PostgreSQL、Qdrant、Neo4j）
   - MQ 连接（RabbitMQ）
   - 外部服务（LLM API、Embedding API）
2. 输出健康检查脚本

**输出格式**：
```bash
#!/bin/bash
# health_check.sh - Generated by Claude Code

API_URL="${API_URL:-http://localhost:8000}"

echo "Offer-Catcher Health Check"
echo "==========================="

# API Health
echo -n "API Status: "
curl -sf "${API_URL}/health" > /dev/null && echo "✅ OK" || echo "❌ FAIL"

# PostgreSQL
echo -n "PostgreSQL: "
pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" && echo "✅ OK" || echo "❌ FAIL"

# Qdrant
echo -n "Qdrant: "
curl -sf "${QDRANT_URL}/collections" > /dev/null && echo "✅ OK" || echo "❌ FAIL"

# Neo4j
echo -n "Neo4j: "
curl -sf "${NEO4J_URI}" -u "${NEO4J_USER}:${NEO4J_PASSWORD}" > /dev/null && echo "✅ OK" || echo "❌ FAIL"

# RabbitMQ
echo -n "RabbitMQ: "
curl -sf "${RABBITMQ_URL}/api/overview" -u "${RABBITMQ_USER}:${RABBITMQ_PASSWORD}" > /dev/null && echo "✅ OK" || echo "❌ FAIL"

# LLM API (test call)
echo -n "LLM API: "
curl -sf -X POST "${LLM_API_URL}" \
  -H "Authorization: Bearer ${OPENAI_API_KEY}" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"test"}],"max_tokens":5}' \
  > /dev/null && echo "✅ OK" || echo "❌ FAIL"

echo ""
echo "Health check complete."
```

---

### 四、文档与知识管理类

#### `/update-docs`

**描述**：根据代码变更更新文档

**触发场景**：
- PR 合并后（有文档影响）
- 手动调用 `/update-docs --files <变更文件>`

**执行内容**：
1. 分析变更：
   - 新增/删除的文件
   - 新增/修改的 API endpoint
   - 新增/修改的配置项
   - 架构变更（DDD 分层调整）
2. 更新：
   - CLAUDE.md（`<quick_reference>` 块）
   - API 文档（endpoint 描述）
   - 架构图（如需要）

**输出格式**：
```
Documentation Update Report
===========================
Files Changed: 3

CLAUDE.md Updates:
------------------
<quick_reference> block:
  + Added: application/services/stats_service.py
  + Added: infrastructure/tools/query_graph.py

API Documentation Updates:
--------------------------
  + POST /api/stats/distribution - Get question distribution stats
    Parameters: company, position, mastery_level
    Response: {distribution: {knowledge: 100, project: 50, ...}}

  ~ Modified: POST /api/chat/stream
    Added parameter: context_filter (optional)
    New behavior: Filter questions by mastery_level

Architecture Impact: None (no layer boundary changes)
```

---

#### `/pitfall-learn`

**描述**：解决问题后提取可复用经验

**触发场景**：
- 成功解决 bug 或问题后
- 手动调用 `/pitfall-learn "问题描述"`

**执行内容**：
1. 分析问题：
   - 问题现象
   - 根本原因
   - 解决方案
2. 判断是否为可复用经验（非项目特定）
3. 更新 CLAUDE.md `<pitfalls>` 块

**输出格式**：
```
Pitfall Learning Report
=======================
Issue: DeepSeek API 返回格式变更导致 reasoning_content 解析失败

Root Cause: DeepSeek 更新 API，新增 reasoning_content 字段，
            原解析逻辑仅处理 content 字段

Solution: 增加 reasoning_content 字段兼容处理，
          优先使用 content，fallback 到 reasoning_content

Added to <pitfalls>:
--------------------
| DeepSeek API 返回格式变更 | reasoning_content 字段结构变化 | 增加字段兼容处理，优先 content fallback reasoning_content |

Verified: ✅ Tested with both old and new API response formats
```

---

### 五、Issue 与任务管理类

#### `/triage-issue`

**描述**：自动分类 GitHub Issue

**触发场景**：
- 新 Issue 创建时（通过 webhook）
- 手动调用 `/triage-issue <Issue号>`

**执行内容**：
1. 分析 Issue 内容：
   - 关键词识别（bug、feature、question）
   - 代码引用（文件路径、函数名）
   - 错误日志分析
2. 分类：
   - 类型：bug / feature / question / documentation
   - 优先级：P0 (critical) / P1 (high) / P2 (medium) / P3 (low)
   - 建议处理者（根据代码 ownership）
3. 添加标签和建议

**输出格式**：
```
Issue Triage Report
===================
Issue #45: "Chat Agent 无法处理图片输入"

Classification:
  - Type: bug
  - Priority: P1 (high)
  - Labels: bug, agent, chat, vision

Analysis:
  - Referenced code: application/agents/chat/agent.py
  - Error pattern: Vision input not handled in message parsing
  - Likely cause: Missing image handling in message preprocessing

Suggested Assignee: @liuchenyu (owns chat agent)

Recommended Actions:
1. Add image handling to chat agent message parser
2. Vision Extractor pattern may be reusable
3. Test with image input after fix

Auto-applied labels: bug, P1
```

---

#### `/estimate-task`

**描述**：估算任务复杂度和工时

**触发场景**：
- Issue 创建后需要估算
- 手动调用 `/estimate-task <Issue号>`

**执行内容**：
1. 分析任务：
   - 涉及文件数量
   - 涉及层级（domain / application / infrastructure / api）
   - 新增 vs 修改
   - 测试复杂度
2. 参考历史：
   - 类似任务的提交记录
   - 历史耗时数据
3. 输出估算

**输出格式**：
```
Task Estimation Report
======================
Issue #45: "Add image support to Chat Agent"

Complexity Analysis:
--------------------
Files Affected: 3
  - application/agents/chat/agent.py (modify)
  - application/agents/chat/state.py (modify)
  - tests/application/agents/test_chat_agent.py (new)

Layer Distribution:
  - Application: 2 files
  - Test: 1 file

Complexity Factors:
  + Cross-layer change (moderate)
  + New test required (moderate)
  + Existing pattern (Vision Extractor) to reference (reduced)

Historical Reference:
  - Similar task: Vision Extractor implementation
  - Time: 3 days (commit history)

Estimation:
-----------
  - Development: 2 days
  - Testing: 1 day
  - Documentation: 0.5 day
  - Total: 3.5 days

Confidence: 75% (based on similar task history)
```

---

## 优先级排序

### 高优先级（核心价值）

| Skill | 理由 |
|-------|------|
| `/ddd-check` | DDD 是本项目架构核心，违反会导致依赖倒置失效 |
| `/review-pr` | 减少 code review 机械负担，聚焦架构合规 |
| `/gen-tests` | 编码规范要求新功能必须配套测试 |
| `/pitfall-learn` | 持续积累经验，已有 `<pitfalls>` 块承载 |

### 中优先级

| Skill | 理由 |
|-------|------|
| `/security-scan` | 涉及 LLM API、Qdrant、MQ，安全风险点多 |
| `/deploy-check` | 多环境部署（API + Worker），配置复杂 |
| `/agent-test` | 本项目有多个 Agent，需特殊测试策略 |

### 低优先级（锦上添花）

| Skill | 理由 |
|-------|------|
| `/audit-pipeline` | CI 尚未建立，暂无审计需求 |
| `/test-selector` | 测试套件规模较小时收益有限 |
| `/update-docs` | 手动更新文档可接受 |
| `/triage-issue` | Issue 量较小时人工处理可行 |
| `/estimate-task` | 需要积累历史数据后才准确 |
| `/rollback-plan` | 可在部署流程成熟后引入 |
| `/health-check` | 可手动编写检查脚本 |

---

## 配置示例

在 `.claude/settings.json` 中配置：

```json
{
  "skills": {
    "ddd-check": {
      "description": "检查 DDD 分层规则合规性",
      "prompt": "扫描 domain/ 目录下所有 import，检查是否有 infrastructure/application 引用。检查 repositories.py 是否为 Protocol。输出违规列表和建议。"
    },
    "review-pr": {
      "description": "审查 PR 的架构合规、类型标注、安全漏洞",
      "prompt": "获取 PR 变更文件，执行 DDD 检查、类型标注检查、Prompt 硬编码检查、安全漏洞检查、日志规范检查。输出审查报告。"
    }
  }
}
```

---

## 后续演进

1. **集成 CI Pipeline** — Skills 可作为 GitHub Actions step 执行
2. **Webhook 触发** — Issue 创建、PR 提交自动触发对应 Skill
3. **闭环学习** — Skill 执行结果反馈更新 `<pitfalls>`
4. **多 Agent 协作** — 复杂任务可拆分给多个 specialized Agent