# Interview Agent 设计文档

## 概述

Interview Agent 是 AI 模拟面试官，提供模拟面试能力，支持多轮对话、追问、评估。核心设计目标是实现**掌握度驱动的自适应面试引擎**，形成"对话即评估，面试即练习"的自适应学习闭环。

---

## 核心设计

### 1. 掌握度三级模型

定义用户对题目的掌握程度，用于追踪学习进度和驱动出题策略。

```python
class MasteryLevel(int, Enum):
    LEVEL_0 = 0  # 未掌握/未复习
    LEVEL_1 = 1  # 比较熟悉
    LEVEL_2 = 2  # 已掌握
```

掌握度存储在 Qdrant Payload 的 `mastery_level` 字段中（INTEGER 索引）。

### 2. 掌握度驱动的自适应出题策略

模拟面试创建时，优先从用户薄弱题目池抽题，形成针对性练习。

#### 权重分配策略

| 掌握度 | 权重 | 说明 |
|--------|------|------|
| LEVEL_0 | 60% | 未掌握题目优先 |
| LEVEL_1 | 30% | 基本了解题目次优 |
| LEVEL_2 | 10% | 已掌握题目少量 |

#### 出题算法流程

```
1. 统计各掌握度池的题目数量
   ├─ 调用 Qdrant count API + Payload 过滤
   └─ 返回: {LEVEL_0: count_0, LEVEL_1: count_1, LEVEL_2: count_2}

2. 按权重分配题目数量
   ├─ desired = total_questions × weight[level]
   ├─ actual = min(desired, available, remaining)
   └─ 某池不足时从 LEVEL_0 补充

3. 从各池检索题目
   ├─ 向量相似度 + Payload 硬过滤
   └─ 检索 2× 配额数量作为候选

4. 随机打乱并选取
   └─ shuffle(all_candidates)
   └─ 取 top N
```

#### 关键方法

```python
def _count_by_mastery(self, company, position, mastery_level) -> int:
    """统计指定掌握度的题目数量"""
    query_filter = self._question_repo._client.build_filter(
        company=company,
        position=position,
        mastery_level=mastery_level.value,
    )
    return self._question_repo._client.count(query_filter)

def _fetch_by_mastery(self, company, position, mastery_level, query_vector, limit):
    """从指定掌握度池检索题目"""
    filter_conditions = {
        "company": company,
        "position": position,
        "mastery_level": mastery_level.value,
    }
    return self._question_repo.search(
        query_vector=query_vector,
        filter_conditions=filter_conditions,
        limit=limit,
    )
```

### 3. 评分闭环同步题库

面试评分后，自动调用 Scorer Agent 更新题库 mastery_level，形成学习闭环。

#### 评分状态机

根据评分分数计算新的掌握度等级：

```
LEVEL_0 → LEVEL_2: score >= 85 (跨级升级)
LEVEL_0 → LEVEL_1: score >= 60
LEVEL_1 → LEVEL_2: score >= 85
LEVEL_2 保持不变
score < 60 保持当前等级
```

```python
def calculate_new_level(current_level: MasteryLevel, score: int) -> MasteryLevel:
    if current_level == MasteryLevel.LEVEL_0:
        if score >= 85:
            return MasteryLevel.LEVEL_2
        elif score >= 60:
            return MasteryLevel.LEVEL_1
    elif current_level == MasteryLevel.LEVEL_1:
        if score >= 85:
            return MasteryLevel.LEVEL_2
    return current_level
```

#### 评分流程

```
process_answer_stream(answer)
    │
    ├─ if scorer_agent:
    │   ├─ 查询题目获取原始 mastery_level
    │   ├─ await scorer_agent.score(question_id, answer)
    │   │   └─ Scorer Agent 内部更新题库 mastery_level
    │   ├─ 返回 ScoreResult: {score, mastery_level, strengths, improvements, feedback}
    │   └─ 记录 mastery_before → mastery_after 变化
    │
    └─ else (降级方案):
    │   └─ 调用 LLM 流式评估 + parse_evaluation 解析
    │
    └─ 决定下一步:
        ├─ score >= 70: 进入下一题
        └─ score < 70: 继续追问（检查追问次数限制）
```

### 4. 追问次数限制

为避免无限追问循环，设置追问上限。配置项 `interview_max_follow_ups` 默认值为 3。

#### 配置位置

```python
# 文件: infrastructure/config/settings.py

class Settings(BaseSettings):
    # 面试模块配置
    interview_max_follow_ups: int = Field(default=3, description="追问次数上限")
```

可通过环境变量 `INTERVIEW_MAX_FOLLOW_UPS` 覆盖。

#### Agent 使用

```python
class InterviewAgent:
    def __init__(
        self,
        ...
        max_follow_ups: Optional[int] = None,
    ):
        # 从配置读取，支持构造时覆盖
        self._max_follow_ups = max_follow_ups or get_settings().interview_max_follow_ups
```

#### 设计逻辑

```
回答评分 < 70 时：
    │
    ├─ 检查当前追问次数 follow_up_count
    │   ├─ follow_up_count >= 3: 强制进入下一题
    │   │   ├─ 追加本次评估到 follow_ups
    │   │   ├─ 生成总结性诊断反馈
    │   │   └─ 标记题目状态为 SCORED
    │   │
    │   └─ follow_up_count < 3: 继续追问
    │       ├─ 追加本次评估到 follow_ups
    │       ├─ new_count = follow_up_count + 1
    │       └─ 返回 follow_up 类型消息（含剩余追问次数）
```

#### 总结性反馈

当达到追问上限时，根据最终评分给出诊断性反馈：

| 最终评分范围 | 反馈策略 |
|-------------|---------|
| < 40 | 建议系统学习相关知识点，从基础开始 |
| 40-59 | 建议加强核心原理和实际应用场景学习 |
| 60-69 | 建议巩固细节，确保清晰完整表达 |

```python
def _generate_follow_up_summary(self, question, final_score) -> str:
    if final_score < 40:
        return "经过3次追问，你对这道题的掌握程度仍然较低..."
    elif final_score < 60:
        return "经过3次追问，你对这道题的理解还不够深入..."
    else:
        return "经过3次追问，你的回答已经接近要求..."
```

---

## 架构设计

### 依赖注入

```python
class InterviewAgent:
    def __init__(
        self,
        llm: LLMType,                      # LLM 实例
        question_repo: QuestionRepository,  # 题目仓库
        embedding_adapter: EmbeddingAdapter, # 向量嵌入
        scorer_agent: Optional[ScorerAgent], # 评分 Agent（可选）
        prompts_dir: Any,
    ):
        ...
```

### Agent 边界清晰

| Agent | 职责 |
|-------|------|
| **Interview Agent** | 面试流程编排、出题策略、会话管理 |
| **Scorer Agent** | 专业评分、mastery_level 更新、反馈生成 |

Interview Agent 负责编排，Scorer Agent 负责评分和 mastery 更新，两者通过依赖注入解耦。

---

## 关键方法

### create_session

创建面试会话，预加载题目。

```python
def create_session(self, user_id, request: InterviewSessionCreate) -> InterviewSession:
    session = InterviewSession(...)
    self._preload_questions(session)
    
    if not session.questions:
        raise ValueError("题库中没有足够的题目")
    
    return session
```

### process_answer_stream

流式处理用户回答，集成 Scorer Agent。

```python
async def process_answer_stream(self, session_id, answer) -> AsyncIterator[str]:
    # 使用 Scorer Agent 评分
    if self._scorer_agent:
        score_result = await self._scorer_agent.score(question_id, answer)
        # Scorer Agent 内部自动更新 mastery_level
        
    # 输出评分结果（包含掌握度变化）
    yield json.dumps({
        "type": "score_result",
        "score": score,
        "mastery_before": ...,
        "mastery_after": ...,
        "strengths": [...],
        "improvements": [...],
    })
```

### get_report

生成面试报告，包含掌握度变化历史。

```python
def get_report(self, session_id) -> InterviewReport:
    # 分析知识点
    for q in answered:
        if q.score >= 80:
            strong_points.extend(q.knowledge_points)
        elif q.score < 60:
            weak_points.extend(q.knowledge_points)
    
    return InterviewReport(
        strengths=strong_points,
        weaknesses=weak_points,
        question_details=[...],  # 包含 mastery_before/after
    )
```

---

## 数据模型

### InterviewQuestion

面试题目实体，包含掌握度追踪字段：

```python
class InterviewQuestion(BaseModel):
    question_id: str
    question_text: str
    question_type: str
    difficulty: DifficultyLevel
    knowledge_points: list[str]
    
    # 评分相关
    user_answer: Optional[str]
    score: Optional[int]        # 0-100
    feedback: Optional[str]
    
    # 掌握度追踪
    mastery_before: Optional[int]  # 答题前掌握度 (0/1/2)
    mastery_after: Optional[int]   # 答题后掌握度 (0/1/2)
    
    status: QuestionStatus
    answered_at: Optional[datetime]
```

### InterviewSession

面试会话聚合根：

```python
class InterviewSession(BaseModel):
    session_id: str
    user_id: str
    company: str
    position: str
    difficulty: DifficultyLevel
    total_questions: int
    
    status: SessionStatus  # active/paused/completed
    questions: list[InterviewQuestion]
    current_question_idx: int
    
    correct_count: int      # score >= 70 的题目数
    started_at: datetime
    ended_at: Optional[datetime]
```

---

## 面试风格适配

根据目标公司调整面试官风格：

```python
COMPANY_STYLES = {
    "字节跳动": "务实、注重细节和深度",
    "阿里巴巴": "注重价值观匹配和系统性思维",
    "腾讯": "温和但有深度，注重实际应用",
    "百度": "注重技术细节和底层原理",
    "美团": "务实、注重业务理解",
    ...
}
```

---

## 设计原则

1. **复用现有组件**：QuestionRepository、ScorerAgent、calculate_new_level 状态机
2. **保持边界清晰**：Interview Agent 编排，Scorer Agent 评分
3. **防御性编程**：Scorer Agent 失败时 Fallback 到 LLM 评估
4. **DDD 分层**：Application 层调用 Domain/Infrastructure，不跨层调用
5. **题库为空抛异常**：不生成默认题目，确保题目来源于真实题库

---

## 相关文件

| 文件路径 | 内容 |
|----------|------|
| `application/agents/interview/agent.py` | Interview Agent 实现（追问上限可配置） |
| `application/agents/scorer/agent.py` | Scorer Agent 实现 |
| `application/agents/factory.py` | Agent 组装和依赖注入 |
| `domain/interview/aggregates.py` | InterviewSession, InterviewQuestion 聚合 |
| `domain/interview/services.py` | calculate_new_level 状态机 |
| `domain/shared/enums.py` | MasteryLevel, QuestionStatus, SessionStatus |
| `infrastructure/persistence/qdrant/question_repository.py` | 题目仓库实现 |
| `tests/agents/test_interview_agent.py` | 单元测试（含追问限制测试） |

---

## 测试验证

```bash
# 运行面试 Agent 测试
cd backend
uv run pytest tests/agents/test_interview_agent.py -v

# 测试掌握度统计（真实 API）
uv run pytest tests/agents/test_interview_agent.py::TestMasteryDrivenQuestionSelection::test_count_by_mastery -v

# 测试评分闭环（需要题库数据）
uv run pytest tests/agents/test_interview_agent.py::TestScorerIntegration -v

# 测试追问次数限制
uv run pytest tests/agents/test_interview_agent.py::TestFollowUpLimit -v
```

---

## 未来扩展

1. **用户维度 mastery**：当前 mastery_level 题目级别，未来可扩展到用户-题目维度
2. **动态权重调整**：根据用户历史表现动态调整出题权重
3. **知识点关联**：结合 Neo4j 知识图谱，关联考察知识点
4. **多轮 mastery 追踪**：记录多次答题的 mastery 变化曲线
5. **追问策略优化**：根据用户回答质量动态调整追问深度和内容