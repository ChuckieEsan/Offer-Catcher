# Agent DDD 重构计划

## Context

当前项目中的 Agent 实现（VisionExtractor、AnswerSpecialist、TitleGenerator、Scorer）直接放在 `domain/*/services.py` 中，并直接依赖 Infrastructure 层的组件（LLMAdapter、OCRAdapter、QdrantManager）。

这违反了 DDD 的依赖倒置原则：Domain 层应该只定义接口，Infrastructure 层负责实现。

**问题现状**：
- `domain/shared/agent_base.py` 直接 import `create_llm` from `infrastructure.adapters.llm_adapter`
- `domain/question/services.py` 包含完整 Agent 实现而非接口
- `domain/chat/services.py` 同样包含 TitleGeneratorAgent 实现
- `domain/interview/services.py` 包含 ScorerAgent 实现，还直接调用 QdrantManager
- `tools/` 目录存在冗余封装层，部分工具只是对 Adapter 的无意义包装

**目标**：
采用混合方案（CAA + DDD），将 Agent 作为 Application 层组件，通过依赖注入实现 Domain 与 Infrastructure 的解耦。同时清理 tools 层的冗余封装。

## Tools 层分析

当前 `app/tools/` 目录包含两类内容：

### 类型1: 无意义封装层（应移除）
| 文件 | 问题 |
|------|------|
| `embedding_tool.py` | 只是调用 `EmbeddingAdapter.embed()` 的封装，无额外逻辑 |
| `reranker_tool.py` | 只是调用 `RerankerAdapter.rerank()` 的封装，无额外逻辑 |

**处理方案**：移除这些文件，调用方直接使用 `EmbeddingAdapter` 和 `RerankerAdapter`。

### 类型2: 有额外逻辑的封装（评估保留）
| 文件 | 分析 |
|------|------|
| `web_search_tool.py` | 有 `search_for_answer` 方法（拼接上下文），还有 LangChain @tool |

**处理方案**：`WebSearchTool` 类可合并到 `WebSearchAdapter`，LangChain @tool `search_web` 移到 `application/agents/shared/tools/`。

### 类型3: LangChain @tool 函数（给 Agent 用）
| 文件 | 说明 |
|------|------|
| `search_question_tool.py` | 本地题目搜索，调用 RetrievalApplicationService |
| `vision_extractor_tool.py` | 面经提取，调用 VisionExtractor（需要更新导入路径）|
| `query_graph_tool.py` | 图数据库查询，调用 GraphClient |
| `interview_tools.py` | 面试相关工具集 |

**处理方案**：这些是 LangChain @tool 装饰器函数，供 Agent 调用。按归属放入对应 Agent 目录：
- `search_questions` → `application/agents/shared/tools/`（通用工具）
- `search_web` → `application/agents/shared/tools/`（通用工具）
- `query_graph` → `application/agents/shared/tools/`（通用工具）
- `extract_interview_questions` → `application/agents/vision_extractor/tools/`
- `interview_tools.py` → `application/agents/interview/tools/`

## 目标架构

```
app/
│
├── domain/                      # Layer 1: 核心业务 + 接口定义
│   ├── question/
│   │   ├── aggregates.py        # Question, ExtractTask（保持不变）
│   │   ├── repositories.py      # Protocol（保持不变）
│   │   ├── services.py          # ⭐ 改为只有 Protocol 接口
│   │   │   ├── AnswerGenerator(Protocol)
│   │   │   └── InterviewExtractor(Protocol)
│   │   ├── prompts/             # Prompt 文件（保持）
│   │   └── utils.py             # 工具函数（保持）
│   │
│   ├── chat/
│   │   ├── aggregates.py        # Conversation（保持不变）
│   │   ├── repositories.py      # Protocol（保持不变）
│   │   ├── services.py          # ⭐ 改为只有 Protocol
│   │   │   └── TitleGenerator(Protocol)
│   │   ├── prompts/
│   │
│   ├── interview/
│   │   ├── aggregates.py        # InterviewSession（保持不变）
│   │   ├── repositories.py      # Protocol（保持不变）
│   │   ├── services.py          # ⭐ 改为只包含 Protocol + 纯函数
│   │   │   ├── AnswerScorer(Protocol)
│   │   │   └── MasteryCalculator（纯函数，保留）
│   │   ├── prompts/
│   │
│   └── shared/
│       ├── agent_base.py        # ⭐ 删除（移到 application）
│       ├── prompts/             # 删除（不再需要）
│       ├── enums.py             # 保持
│       └── exceptions.py        # 保持
│
├── application/                 # Layer 2: 编排 + Agent 实现
│   ├── services/                # Application Service（保持不变）
│   │   ├── question_service.py
│   │   ├── chat_service.py
│   │   ├── interview_service.py
│   │   ├── extract_task_service.py
│   │   ├── ingestion_service.py
│   │   ├── retrieval_service.py
│   │
│   ├── agents/                  # ⭐ 新增：Agent 实现
│   │   ├── answer_specialist/
│   │   │   ├── agent.py         # AnswerSpecialistAgent 实现
│   │   │   ├── prompts/
│   │   │   │   └── answer_specialist.md
│   │   │   ├── schemas.py       # AnswerGenerationSchema
│   │   │   └── tools/           # Agent 特定工具
│   │   │
│   │   ├── vision_extractor/
│   │   │   ├── agent.py         # VisionExtractor 实现
│   │   │   ├── prompts/
│   │   │   │   └── vision_extractor.md
│   │   │   ├── schemas.py       # ExtractedInterviewSchema
│   │   │   ├── tools/
│   │   │   │   └── extract_interview_questions.py  # LangChain @tool
│   │   │
│   │   ├── title_generator/
│   │   │   ├── agent.py
│   │   │   ├── prompts/
│   │   │   │   └── title_generator.md
│   │   │
│   │   ├── scorer/
│   │   │   ├── agent.py
│   │   │   ├── prompts/
│   │   │   │   └── scorer.md
│   │   │   ├── schemas.py       # ScoreResultSchema
│   │   │   ├── tools/
│   │   │   │   └── mastery_calculator.py
│   │   │
│   │   ├── interview/           # 面试 Agent
│   │   │   ├── agent.py
│   │   │   ├── prompts/
│   │   │   ├── tools/
│   │   │   │   └── interview_tools.py  # LangChain @tool
│   │   │
│   │   ├── shared/              # 共享组件（Rule of Three）
│   │   │   ├── base_agent.py    # BaseAgent 基类
│   │   │   ├── prompts/         # 共享 prompts
│   │   │   └── tools/           # 共享 LangChain @tool
│   │   │       ├── search_web.py
│   │   │       ├── search_questions.py
│   │   │       └── query_graph.py
│   │   │
│   │   └── factory.py           # ⭐ 组装代码
│   │       def get_answer_generator() -> AnswerGenerator
│   │       def get_vision_extractor() -> InterviewExtractor
│   │       def get_title_generator() -> TitleGenerator
│   │       def get_answer_scorer() -> AnswerScorer
│   │
│   └── wiring.py                # 全局组装入口
│
├── infrastructure/              # Layer 3: 基础设施
│   ├── adapters/                # Adapter（保持不变，部分增强）
│   │   ├── llm_adapter.py
│   │   ├── web_search_adapter.py  # 可合并 search_for_answer 方法
│   │   ├── ocr_adapter.py
│   │   ├── embedding_adapter.py
│   │   ├── reranker_adapter.py
│   │
│   ├── persistence/             # 保持不变
│   │   ├── postgres/
│   │   ├── qdrant/
│   │   ├── neo4j/
│   │
│   └── common/                  # 保持不变
│       ├── logger.py
│       ├── prompt.py
│       ├── retry.py
│       ├── cache.py
│
├── tools/                       # ⭐ 删除整个目录
│   └── (迁移内容到 application/agents/ 和 infrastructure/adapters/)
│
└── api/                         # API（保持不变）
    ├── routes/
    ├── dto/
```

## 重构步骤

### Phase 0: Tools 层清理

**删除冗余封装**：
1. 删除 `tools/embedding_tool.py` - 调用方改为使用 `EmbeddingAdapter`
2. 删除 `tools/reranker_tool.py` - 调用方改为使用 `RerankerAdapter`

**迁移 LangChain @tool**：
1. `tools/web_search_tool.py` 中的 `search_web` → `application/agents/shared/tools/search_web.py`
2. `tools/search_question_tool.py` → `application/agents/shared/tools/search_questions.py`
3. `tools/query_graph_tool.py` → `application/agents/shared/tools/query_graph.py`
4. `tools/vision_extractor_tool.py` → `application/agents/vision_extractor/tools/extract_questions.py`
5. `tools/interview_tools.py` → `application/agents/interview/tools/interview_tools.py`

**更新调用方**：
- `pipelines/ingestion.py`: `get_embedding_tool()` → `get_embedding_adapter()`
- `pipelines/retrieval.py`: `get_reranker_tool()` → `get_reranker_adapter()`
- 其他引用处更新导入路径

**删除 tools 目录**：
```bash
rm -rf app/tools/
```

### Phase 1: Domain 层改造 - 定义接口

**文件修改**：

1. **`domain/question/services.py`** - 改为只包含 Protocol
   ```python
   """Question Domain Services - 接口定义"""

   from typing import Protocol
   from app.domain.question.aggregates import Question
   from app.models import ExtractedInterview, QuestionItem

   class AnswerGenerator(Protocol):
       """答案生成器接口"""
       def generate(self, question: QuestionItem) -> str: ...

   class InterviewExtractor(Protocol):
       """面经提取器接口"""
       def extract(self, source: str | list[str], source_type: str) -> ExtractedInterview: ...
   ```

2. **`domain/chat/services.py`** - 改为只包含 Protocol
   ```python
   """Chat Domain Services - 接口定义"""

   from typing import Protocol, List

   class TitleGenerator(Protocol):
       """标题生成器接口"""
       def generate_title(self, messages: List) -> str: ...
   ```

3. **`domain/interview/services.py`** - 改为只包含 Protocol + 纯函数
   ```python
   """Interview Domain Services - 接口定义"""

   from typing import Protocol
   from app.models import ScoreResult
   from app.models.question import MasteryLevel

   # 纯函数保留（状态机逻辑）
   def calculate_new_level(current_level: MasteryLevel, score: int) -> MasteryLevel: ...

   class AnswerScorer(Protocol):
       """答案评分器接口"""
       async def score(self, question_id: str, user_answer: str) -> ScoreResult: ...
   ```

4. **删除 `domain/shared/agent_base.py`**
5. **删除 `domain/shared/prompts/`**

### Phase 2: Application 层 - 创建 Agent 目录

**新建目录结构**：

```
application/agents/
├── answer_specialist/
│   ├── __init__.py
│   ├── agent.py          # AnswerSpecialistAgent 实现
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── answer_specialist.md
│   ├── schemas.py        # 输入/输出 Schema
│   └── tools/            # Agent 特定工具
│
├── vision_extractor/
│   ├── __init__.py
│   ├── agent.py
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── vision_extractor.md
│   ├── schemas.py        # ExtractedQuestion, ExtractedInterviewSchema
│   ├── tools/
│   │   └── extract_questions.py   # LangChain @tool
│
├── title_generator/
│   ├── __init__.py
│   ├── agent.py
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── title_generator.md
│
├── scorer/
│   ├── __init__.py
│   ├── agent.py
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── scorer.md
│   ├── schemas.py
│   ├── tools/
│   │   └── mastery_calculator.py
│
├── interview/
│   ├── __init__.py
│   ├── agent.py
│   ├── prompts/
│   ├── tools/
│   │   └── interview_tools.py
│
├── shared/
│   ├── __init__.py
│   ├── base_agent.py     # BaseAgent 基类（依赖注入 LLM）
│   ├── prompts/          # 共享 prompts（如需要）
│   └── tools/            # 共享 LangChain @tool
│       ├── search_web.py
│       ├── search_questions.py
│       ├── query_graph.py
│
├── factory.py            # 组装函数
└── wiring.py             # 全局组装入口
```

### Phase 3: 实现 Agent

**关键文件**：

1. **`application/agents/shared/base_agent.py`**
   ```python
   """Agent 基类 - 使用依赖注入"""

   from typing import Any, Generic, Optional, TypeVar
   from langchain_openai import ChatOpenAI
   from app.infrastructure.common.logger import logger
   from app.infrastructure.common.retry import retry

   T = TypeVar("T")

   class BaseAgent(Generic[T]):
       _prompt_filename: str = ""
       _prompts_dir: Any = None
       _structured_output_schema: Optional[type] = None

       def __init__(
           self,
           llm: ChatOpenAI,          # 依赖注入
           prompts_dir: Any,
       ) -> None:
           self._llm = llm
           self._prompts_dir = prompts_dir
           self._structured_llm: Optional[ChatOpenAI] = None

       # ... 其他方法保持不变
   ```

2. **`application/agents/answer_specialist/agent.py`**
   ```python
   class AnswerSpecialistAgent(BaseAgent[str]):
       _prompt_filename = "answer_specialist.md"
       _structured_output_schema = None

       def __init__(
           self,
           llm: ChatOpenAI,
           web_search: WebSearchAdapter,  # 依赖注入
           prompts_dir: Path,
       ):
           super().__init__(llm, prompts_dir)
           self.web_search = web_search

       def generate(self, question: QuestionItem) -> str:
           # 实现逻辑
   ```

3. **`application/agents/vision_extractor/agent.py`**
   ```python
   class VisionExtractor(BaseAgent[ExtractedInterviewSchema]):
       def __init__(
           self,
           llm: ChatOpenAI,
           ocr_adapter: OCRAdapter,  # 依赖注入
           prompts_dir: Path,
       ):
           super().__init__(llm, prompts_dir)
           self.ocr_adapter = ocr_adapter

       def extract(self, source, source_type) -> ExtractedInterview:
           # 实现逻辑
   ```

### Phase 4: 组装代码

**`application/agents/factory.py`**：

```python
"""Agent 组装函数"""

from pathlib import Path

from app.infrastructure.adapters.llm_adapter import get_llm
from app.infrastructure.adapters.web_search_adapter import get_web_search_adapter
from app.infrastructure.adapters.ocr_adapter import get_ocr_adapter
from app.infrastructure.persistence.qdrant import get_qdrant_manager

from app.application.agents.answer_specialist.agent import AnswerSpecialistAgent
from app.application.agents.vision_extractor.agent import VisionExtractor
from app.application.agents.title_generator.agent import TitleGeneratorAgent
from app.application.agents.scorer.agent import ScorerAgent

from app.application.agents.answer_specialist.prompts import PROMPTS_DIR as ANSWER_PROMPTS
from app.application.agents.vision_extractor.prompts import PROMPTS_DIR as VISION_PROMPTS
from app.application.agents.title_generator.prompts import PROMPTS_DIR as TITLE_PROMPTS
from app.application.agents.scorer.prompts import PROMPTS_DIR as SCORER_PROMPTS


def get_answer_specialist() -> AnswerSpecialistAgent:
    """组装 AnswerSpecialistAgent"""
    llm = get_llm("deepseek", "chat")
    web_search = get_web_search_adapter()
    return AnswerSpecialistAgent(llm, web_search, ANSWER_PROMPTS)


def get_vision_extractor() -> VisionExtractor:
    """组装 VisionExtractor"""
    llm = get_llm("deepseek", "chat")
    ocr = get_ocr_adapter()
    return VisionExtractor(llm, ocr, VISION_PROMPTS)


def get_title_generator() -> TitleGeneratorAgent:
    """组装 TitleGeneratorAgent"""
    llm = get_llm("deepseek", "chat")
    return TitleGeneratorAgent(llm, TITLE_PROMPTS)


def get_scorer_agent() -> ScorerAgent:
    """组装 ScorerAgent"""
    llm = get_llm("deepseek", "chat")
    qdrant = get_qdrant_manager()
    return ScorerAgent(llm, qdrant, SCORER_PROMPTS)


# Domain Service 接口适配器
def get_answer_generator() -> AnswerGenerator:
    """获取 AnswerGenerator（Domain Service 接口）"""
    return get_answer_specialist()


def get_interview_extractor() -> InterviewExtractor:
    """获取 InterviewExtractor（Domain Service 接口）"""
    return get_vision_extractor()
```

### Phase 5: 更新 Application Service

**修改 `application/services/question_service.py`**：

```python
class QuestionApplicationService:
    def __init__(
        self,
        question_repo: QuestionRepository,
        cache: CacheApplicationService,
        answer_generator: AnswerGenerator,  # ⭐ 依赖注入
    ):
        self._question_repo = question_repo
        self._cache = cache
        self._answer_generator = answer_generator

    def regenerate_answer(self, question_id: str, preview: bool = True) -> str | None:
        question = self._question_repo.find_by_id(question_id)
        if not question:
            return None

        question_item = QuestionItem(...)
        answer = self._answer_generator.generate(question_item)  # 使用接口

        if not preview:
            question.update_answer(answer)
            self._question_repo.update_answer(question_id, answer)

        return answer


def get_question_service() -> QuestionApplicationService:
    from app.application.agents.factory import get_answer_generator
    return QuestionApplicationService(
        question_repo=get_question_repository(),
        cache=get_cache_service(),
        answer_generator=get_answer_generator(),  # 组装
    )
```

### Phase 6: 更新导入路径

**更新 API 路由**：
- `app/api/routes/score.py`: `from app.application.agents.factory import get_scorer_agent`
- `app/api/routes/extract.py`: `from app.application.agents.factory import get_vision_extractor`
- `app/api/routes/conversations.py`: `from app.application.agents.factory import get_title_generator`

**更新 Workers**：
- `workers/answer_worker.py`: 导入路径调整
- `workers/extract_worker.py`: 导入路径调整

**更新旧兼容层**：
- `app/agents/__init__.py`: 提供向后兼容导入

### Phase 7: 移动 Prompt 文件

复制 prompt 文件到新位置：

```
app/application/agents/
├── answer_specialist/prompts/answer_specialist.md
├── vision_extractor/prompts/vision_extractor.md
├── title_generator/prompts/title_generator.md
├── scorer/prompts/scorer.md
```

保留旧位置 `app/agents/prompts/` 作为兼容。

## 文件修改清单

### 新建文件

| 文件 | 内容 |
|------|------|
| `application/agents/__init__.py` | 模块初始化 |
| `application/agents/shared/__init__.py` | 共享模块初始化 |
| `application/agents/shared/base_agent.py` | BaseAgent 基类（依赖注入版本） |
| `application/agents/shared/tools/__init__.py` | 共享工具初始化 |
| `application/agents/shared/tools/search_web.py` | search_web LangChain @tool |
| `application/agents/shared/tools/search_questions.py` | search_questions LangChain @tool |
| `application/agents/shared/tools/query_graph.py` | query_graph LangChain @tool |
| `application/agents/answer_specialist/__init__.py` | 模块初始化 |
| `application/agents/answer_specialist/agent.py` | AnswerSpecialistAgent 实现 |
| `application/agents/answer_specialist/prompts/__init__.py` | PROMPTS_DIR 定义 |
| `application/agents/answer_specialist/schemas.py` | Schema 定义 |
| `application/agents/vision_extractor/__init__.py` | 模块初始化 |
| `application/agents/vision_extractor/agent.py` | VisionExtractor 实现 |
| `application/agents/vision_extractor/prompts/__init__.py` | PROMPTS_DIR 定义 |
| `application/agents/vision_extractor/schemas.py` | Schema 定义 |
| `application/agents/vision_extractor/tools/extract_questions.py` | extract_interview_questions |
| `application/agents/title_generator/__init__.py` | 模块初始化 |
| `application/agents/title_generator/agent.py` | TitleGeneratorAgent 实现 |
| `application/agents/title_generator/prompts/__init__.py` | PROMPTS_DIR 定义 |
| `application/agents/scorer/__init__.py` | 模块初始化 |
| `application/agents/scorer/agent.py` | ScorerAgent 实现 |
| `application/agents/scorer/prompts/__init__.py` | PROMPTS_DIR 定义 |
| `application/agents/scorer/schemas.py` | Schema 定义 |
| `application/agents/interview/__init__.py` | 模块初始化 |
| `application/agents/interview/tools/interview_tools.py` | 面试相关 LangChain @tool |
| `application/agents/factory.py` | 组装函数 |

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `domain/question/services.py` | 改为 Protocol 接口定义 |
| `domain/chat/services.py` | 改为 Protocol 接口定义 |
| `domain/interview/services.py` | 改为 Protocol + 纯函数 |
| `application/services/question_service.py` | 添加依赖注入参数 |
| `api/routes/score.py` | 更新导入路径 |
| `api/routes/extract.py` | 更新导入路径 |
| `api/routes/conversations.py` | 更新导入路径 |
| `infrastructure/bootstrap/warmup.py` | 更新导入路径 |
| `pipelines/ingestion.py` | embedding_tool → embedding_adapter |
| `pipelines/retrieval.py` | reranker_tool → reranker_adapter |
| `tools/interview_tools.py` | 更新导入路径（迁移前）|

### 删除文件

| 文件 | 原因 |
|------|------|
| `domain/shared/agent_base.py` | 移到 application/agents/shared/ |
| `domain/shared/prompts/__init__.py` | 不再需要 |
| `tools/embedding_tool.py` | 冗余封装，直接用 EmbeddingAdapter |
| `tools/reranker_tool.py` | 冗余封装，直接用 RerankerAdapter |
| `tools/web_search_tool.py` | 迁移 search_web 到 application/agents/shared/tools/ |
| `tools/search_question_tool.py` | 迁移到 application/agents/shared/tools/ |
| `tools/vision_extractor_tool.py` | 迁移到 application/agents/vision_extractor/tools/ |
| `tools/query_graph_tool.py` | 迁移到 application/agents/shared/tools/ |
| `tools/context.py` | 评估是否需要保留或迁移 |
| `tools/__init__.py` | 整个 tools 目录删除 |

## 依赖关系验证

重构后的依赖方向：

```
Infrastructure (LLMAdapter, WebSearchAdapter, EmbeddingAdapter, RerankerAdapter)
       ↓
Application/Agents (AnswerSpecialistAgent, VisionExtractor)
       ↓
Application/Services (QuestionApplicationService)
       ↓
Domain (AnswerGenerator Protocol, Question aggregate)
```

**验证点**：
- Domain 层不 import Infrastructure
- Domain 层只定义 Protocol
- Application Service 通过依赖注入接收接口
- 组装代码允许引用 Infrastructure
- LangChain @tool 函数正确引用新路径

## Verification

1. **导入验证**：
   ```bash
   uv run python -c "
   from app.domain.question.services import AnswerGenerator
   from app.application.agents.factory import get_answer_generator
   from app.application.services.question_service import get_question_service
   print('All imports OK')
   "
   ```

2. **单元测试**：
   ```bash
   uv run pytest tests/domain/ tests/api/ -v
   ```

3. **功能测试**：
   - POST `/extract/tasks` - VisionExtractor
   - POST `/questions/{id}/regenerate-answer` - AnswerSpecialist
   - POST `/score` - ScorerAgent
   - POST `/conversations/{id}/generate-title` - TitleGenerator

## Risks

1. **向后兼容**：旧导入路径 `app.agents.xxx` 需保留兼容层
2. **Workers**：需要同步更新 workers 的导入路径
3. **单例管理**：组装代码需要正确管理单例生命周期
4. **测试覆盖**：需要为新结构编写单元测试
5. **Tools 迁移**：LangChain @tool 函数的导入路径更新影响 Agent

## 时间估算

- Phase 0: Tools 层清理（0.5h）
- Phase 1-2: 创建目录和接口定义（0.5h）
- Phase 3: 实现 Agent（1h）
- Phase 4-5: 组装代码和 Application Service（0.5h）
- Phase 6-7: 更新导入和 Prompt 文件（0.5h）
- Verification: 测试和验证（0.5h）

**总计**：约 3.5 小时