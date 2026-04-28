# 记忆模块 LLM-as-Judge 评测方案

> 版本：v1.0
> 日期：2026-04-27
> 目标：使用真实 LLM API 作为 Judge，对记忆 Agent 进行端到端评测

---

## 一、评测框架调研总结

### 1.1 主流 Agent 评测框架对比

| 框架 | 特点 | 适用场景 | 推荐度 |
|------|------|----------|--------|
| **DeepEval** | pytest-native，50+ 指标，支持 G-Eval 自定义评估 | Agent/RAG/Safety 全覆盖 | ⭐⭐⭐⭐⭐ |
| **Ragas** | RAG 专项评测，faithfulness/relevance 指标 | RAG 系统评测 | ⭐⭐⭐⭐ |
| **OpenAI Evals** | OpenAI 官方，YAML 配置，可自定义 | OpenAI 模型评测 | ⭐⭐⭐⭐ |
| **LangSmith** | LangChain 原生，tracing + evaluation | LangChain 应用 | ⭐⭐⭐⭐ |
| **LangFuse** | 开源，OTel 兼容，框架无关 | 生产监控 | ⭐⭐⭐ |
| **MLflow** | 多框架集成，LLM-as-Judge 支持 | 全流程评测 | ⭐⭐⭐⭐ |

### 1.2 记忆专项评测 Benchmark

| Benchmark | 特点 | 核心指标 |
|-----------|------|----------|
| **LoCoMo** | 长期对话记忆评测，5 种推理类型 | Single-hop/Multi-hop/Temporal/Adversarial QA |
| **Memora** | 记忆遗忘评测，FAMA 指标 | Forgetting-Aware Memory Accuracy |
| **LongMemEval** | 多会话记忆评测，时间感知 | Indexing/Retrieval/Reading Strategy |
| **MemoryBench** | 用户反馈持续学习评测 | Continual Learning Accuracy |

### 1.3 推荐方案

**采用 DeepEval + 自定义 G-Eval + 真实 API**：

1. **DeepEval 提供 pytest-native 评测体验**，易于集成 CI/CD
2. **G-Eval 支持自定义评估标准**，可定义记忆专用指标
3. **真实 API（GPT-4o/Claude）作为 Judge**，替代 mock 评估

---

## 二、评测架构设计

### 2.1 评测流程图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    LLM-as-Judge Memory Evaluation Pipeline               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │ Test Dataset │───▶│ Memory Agent │───▶│  Judge LLM   │              │
│  │  (37 cases)  │    │  (Real API)  │    │ (GPT-4o-mini)│              │
│  └──────────────┘    └──────────────┘    └──────────────┘              │
│         │                   │                   │                       │
│         │                   ▼                   │                       │
│         │            ┌──────────────┐           │                       │
│         │            │   Trace      │           │                       │
│         │            │  (Tool Calls)│───────────│                       │
│         │            └──────────────┘           │                       │
│         │                   │                   │                       │
│         ▼                   ▼                   ▼                       │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │                    Evaluation Report                       │          │
│  │  - Extraction Accuracy: P/R/F1                            │          │
│  │  - Boundary Error Rate: Temporary vs Long-term            │          │
│  │  - Dedup Success Rate                                     │          │
│  │  - Memory Utilization Score                               │          │
│  └──────────────────────────────────────────────────────────┘          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 评测层级

| 层级 | 评测目标 | Judge 类型 | 指标 |
|------|----------|------------|------|
| **Layer 1: Extraction** | 记忆提取决策是否正确 | G-Eval (分类判断) | Precision/Recall/Boundary Error |
| **Layer 2: Content Quality** | 提取内容是否完整准确 | G-Eval (语义评估) | Content Match Score |
| **Layer 3: Utilization** | 记忆是否改善回答质量 | Pairwise Judge | Win Rate/Delta Score |
| **Layer 4: Session-level** | 多轮对话记忆一致性 | Multi-turn G-Eval | Consistency/Drift Rate |

---

## 三、Judge LLM 配置

### 3.1 Judge 模型选择

```python
# Judge 模型配置
JUDGE_CONFIG = {
    # 主 Judge（高精度）
    "primary_judge": {
        "model": "gpt-4o-mini",  # 性价比高，评测准确
        "provider": "openai",
        "temperature": 0.0,  # 确定性评分
        "max_tokens": 1000,
    },
    
    # 辅助 Judge（Claude 视角）
    "secondary_judge": {
        "model": "claude-3-5-haiku",
        "provider": "anthropic",
        "temperature": 0.0,
        "max_tokens": 1000,
    },
    
    # Pairwise Judge（对比评测）
    "pairwise_judge": {
        "model": "gpt-4o",
        "provider": "openai",
        "temperature": 0.0,
        "max_tokens": 500,
    },
}
```

### 3.2 Judge API 调用适配器

```python
"""Judge API 适配器 - 支持多模型"""

from abc import ABC, abstractmethod
from typing import Any
import os

class JudgeAdapter(ABC):
    """Judge LLM 适配器基类"""
    
    @abstractmethod
    async def evaluate(self, prompt: str) -> dict:
        """执行评估，返回结构化结果"""
        pass


class OpenAIJudgeAdapter(JudgeAdapter):
    """OpenAI Judge 适配器"""
    
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.0):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model
        self.temperature = temperature
    
    async def evaluate(self, prompt: str) -> dict:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )
        import json
        return json.loads(response.choices[0].message.content)


class AnthropicJudgeAdapter(JudgeAdapter):
    """Anthropic Judge 适配器"""
    
    def __init__(self, model: str = "claude-3-5-haiku-20241022", temperature: float = 0.0):
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = model
        self.temperature = temperature
    
    async def evaluate(self, prompt: str) -> dict:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        # Claude 返回纯文本，需要解析 JSON
        content = response.content[0].text
        return json.loads(content)


class DeepSeekJudgeAdapter(JudgeAdapter):
    """DeepSeek Judge 适配器（使用项目现有配置）"""
    
    def __init__(self, model: str = "deepseek-chat", temperature: float = 0.0):
        from openai import AsyncOpenAI
        # 使用项目配置的 DeepSeek endpoint
        self.client = AsyncOpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
        self.model = model
        self.temperature = temperature
    
    async def evaluate(self, prompt: str) -> dict:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
        )
        import json
        return json.loads(response.choices[0].message.content)


def get_judge_adapter(provider: str = "openai", **kwargs) -> JudgeAdapter:
    """获取 Judge 适配器"""
    adapters = {
        "openai": OpenAIJudgeAdapter,
        "anthropic": AnthropicJudgeAdapter,
        "deepseek": DeepSeekJudgeAdapter,
    }
    return adapters.get(provider, OpenAIJudgeAdapter)(**kwargs)
```

---

## 四、自定义 G-Eval 指标设计

### 4.1 记忆提取决策评估

```python
"""记忆提取决策 G-Eval"""

EXTRACTION_DECISION_CRITERIA = """
你是一个记忆系统评测专家。请评估 Memory Agent 的决策是否正确。

## 评估维度

1. **应该记忆判断** (should_remember): 
   - 用户是否表达了值得长期记忆的信息？
   - 显式偏好、行为模式、深度讨论 → 应记
   - 临时约束、闲聊、隐私 → 不应记

2. **记忆类型判断** (memory_type_correct):
   - preferences: 用户主动表达的偏好/反馈
   - behaviors: 观察到的重复行为模式（需 >= 2 次）
   - session_summary: 深度讨论或有结论的对话

3. **临时约束识别** (temporary_constraint_detected):
   - "这次"、"这道题"、"先"等临时性表达
   - 临时约束不应写入长期记忆

4. **去重判断** (dedup_correct):
   - 新内容是否与已有内容语义相似？
   - 相似则应跳过，不应重复写入

## 输入信息

对话内容：
{conversation}

已有记忆：
{existing_memory}

Agent 实际决策：
{agent_decision}

## 输出格式

请输出 JSON：
```json
{
  "should_remember_score": 1-5,
  "memory_type_correct": true/false,
  "memory_type_expected": "preferences|behaviors|session_summary|none",
  "temporary_constraint_detected": true/false,
  "dedup_correct": true/false,
  "overall_score": 1-5,
  "reason": "简短解释"
}
```
"""

EXTRACTION_DECISION_PARAMS = ["conversation", "existing_memory", "agent_decision"]
```

### 4.2 记忆内容质量评估

```python
"""记忆内容质量 G-Eval"""

CONTENT_QUALITY_CRITERIA = """
你是一个记忆系统评测专家。请评估提取的记忆内容质量。

## 评估维度

1. **完整性** (completeness):
   - 是否捕获了关键信息？
   - 是否遗漏重要细节？

2. **准确性** (accuracy):
   - 内容是否准确反映用户意图？
   - 是否有误解或歪曲？

3. **结构化** (structured):
   - 是否符合记忆格式规范？
   - Why/How to apply 是否清晰？

4. **去噪性** (noise_free):
   - 是否过滤了无关信息？
   - 是否包含冗余内容？

## 输入信息

原始对话：
{conversation}

提取的记忆内容：
{extracted_content}

记忆类型：
{memory_type}

## 输出格式

请输出 JSON：
```json
{
  "completeness": 1-5,
  "accuracy": 1-5,
  "structured": 1-5,
  "noise_free": 1-5,
  "overall_score": 1-5,
  "missing_keywords": ["关键词1", "关键词2"],
  "extra_noise": ["噪音1"],
  "reason": "简短解释"
}
```
"""

CONTENT_QUALITY_PARAMS = ["conversation", "extracted_content", "memory_type"]
```

### 4.3 记忆利用效果评估（Pairwise）

```python
"""记忆利用效果 Pairwise Judge"""

UTILIZATION_PAIRWISE_CRITERIA = """
你是一个回答质量评估专家。请对比两个回答的质量。

## 背景

用户有一个偏好/历史记忆。我们评估两个回答：
- 回答 A：使用记忆系统的回答
- 回答 B：不使用记忆系统的回答

## 评估维度

1. **任务正确性** (task_correctness): 
   - 回答是否正确解决了用户问题？

2. **个性化匹配** (personalization_fit):
   - 回答是否符合用户偏好？
   - 是否体现了对用户偏好的理解？

3. **历史一致性** (historical_consistency):
   - 是否正确引用了历史讨论？
   - 是否与之前的对话一致？

4. **记忆利用** (memory_utilization):
   - 记忆是否被有效利用？
   - 是否只是简单提及而没有真正使用？

5. **噪音排除** (noise_exclusion):
   - 是否避免了引用无关记忆？

## 输入信息

用户问题：
{query}

用户记忆：
{memory}

回答 A（有记忆）：
{answer_a}

回答 B（无记忆）：
{answer_b}

## 输出格式

请输出 JSON：
```json
{
  "winner": "A" | "B" | "tie",
  "task_correctness": { "a": 1-5, "b": 1-5 },
  "personalization_fit": { "a": 1-5, "b": 1-5 },
  "historical_consistency": { "a": 1-5, "b": 1-5 },
  "memory_utilization": { "a": 1-5 },
  "reason": "简短解释为什么 A/B 更好"
}
```
"""

UTILIZATION_PAIRWISE_PARAMS = ["query", "memory", "answer_a", "answer_b"]
```

### 4.4 多轮对话一致性评估

```python
"""多轮对话一致性 G-Eval"""

MULTI_TURN_CONSISTENCY_CRITERIA = """
你是一个对话一致性评估专家。请评估多轮对话中记忆的使用一致性。

## 评估维度

1. **记忆状态一致性** (memory_state_consistent):
   - 新记忆是否与已有记忆冲突？
   - 冲突时是否正确更新而非矛盾？

2. **引用一致性** (reference_consistent):
   - 对同一历史事件的引用是否一致？
   - 是否有前后矛盾？

3. **偏好演进** (preference_evolution):
   - 偏好变化是否有清晰轨迹？
   - 是否正确处理偏好更新？

4. **遗忘检测** (forgetting_detected):
   - 是否正确遗忘过时信息？
   - 是否错误遗忘重要信息？

## 输入信息

对话历史：
{conversation_history}

记忆演进轨迹：
{memory_evolution}

当前回答：
{current_response}

## 输出格式

请输出 JSON：
```json
{
  "memory_state_consistent": true/false,
  "reference_consistent": true/false,
  "preference_evolution": "correct|incorrect|none",
  "forgetting_detected": true/false,
  "forgetting_type": "correct|incorrect|none",
  "consistency_score": 1-5,
  "conflicts_found": ["冲突描述"],
  "reason": "简短解释"
}
```
"""

MULTI_TURN_CONSISTENCY_PARAMS = ["conversation_history", "memory_evolution", "current_response"]
```

---

## 五、评测代码实现

### 5.1 评测测试文件结构

```text
backend/tests/memory/
  ├── llm_judge/
  │   ├── __init__.py
  │   ├── judge_adapter.py       # Judge API 适配器
  │   ├── g_eval_metrics.py      # G-Eval 指标定义
  │   ├── eval_prompts.py        # Judge Prompt 模板
  │   ├── run_extraction_eval.py # Extraction Harness
  │   ├── run_utilization_eval.py # Utilization Harness
  │   └── run_multi_turn_eval.py # Multi-turn Harness
  │   ├── reports/
  │   │   ├── aggregate.py       # 结果聚合
  │   │   ├── dashboard.py       # Dashboard 渲染
  │   │   └── export.py          # 结果导出
  │   └── config/
  │   │   ├── judge_config.yaml  # Judge 配置
  │   │   └── thresholds.yaml    # 发布门槛
  │   └── artifacts/
  │   │   ├── traces/            # Trace 存储
  │   │   └── judgments/         # Judge 结果
```

### 5.2 Extraction Harness 实现

```python
"""Extraction Harness - 使用真实 API Judge"""

import asyncio
import json
from pathlib import Path
from typing import Any
from dataclasses import dataclass

import pytest

# Judge 适配器
from .judge_adapter import get_judge_adapter
from .eval_prompts import (
    EXTRACTION_DECISION_CRITERIA,
    EXTRACTION_DECISION_PARAMS,
    CONTENT_QUALITY_CRITERIA,
    CONTENT_QUALITY_PARAMS,
)


@dataclass
class ExtractionEvalResult:
    """Extraction 评估结果"""
    case_id: str
    scenario_name: str
    
    # 决策评估
    should_remember_score: int
    memory_type_correct: bool
    memory_type_expected: str
    temporary_constraint_detected: bool
    dedup_correct: bool
    decision_overall_score: int
    
    # 内容评估（如果写入了）
    content_completeness: int | None
    content_accuracy: int | None
    content_structured: int | None
    content_noise_free: int | None
    content_overall_score: int | None
    
    # 元数据
    tool_calls: list[str]
    judge_reason: str
    passed: bool


class ExtractionHarness:
    """Extraction Harness - 评测记忆提取决策"""
    
    def __init__(self, judge_provider: str = "openai"):
        self.judge = get_judge_adapter(provider=judge_provider)
    
    async def evaluate_decision(
        self,
        conversation: str,
        existing_memory: str,
        agent_decision: dict,
    ) -> dict:
        """评估 Agent 决策"""
        
        # 构建 Judge Prompt
        prompt = EXTRACTION_DECISION_CRITERIA.format(
            conversation=conversation,
            existing_memory=existing_memory,
            agent_decision=json.dumps(agent_decision, ensure_ascii=False),
        )
        
        result = await self.judge.evaluate(prompt)
        return result
    
    async def evaluate_content(
        self,
        conversation: str,
        extracted_content: str,
        memory_type: str,
    ) -> dict:
        """评估提取内容质量"""
        
        prompt = CONTENT_QUALITY_CRITERIA.format(
            conversation=conversation,
            extracted_content=extracted_content,
            memory_type=memory_type,
        )
        
        result = await self.judge.evaluate(prompt)
        return result
    
    async def run_case(
        self,
        scenario,  # EvalScenario
        agent_result: dict,
    ) -> ExtractionEvalResult:
        """运行单个场景评估"""
        
        # 格式化对话
        conversation = self._format_conversation(scenario.messages)
        
        # 格式化已有记忆
        existing_memory = f"""
Preferences: {scenario.current_preferences or '（无）'}
Behaviors: {scenario.current_behaviors or '（无）'}
"""
        
        # Agent 决策信息
        tool_calls = [tc[0] for tc in agent_result.get("tool_calls", [])]
        agent_decision = {
            "tools_called": tool_calls,
            "wrote_preferences": "update_preferences" in tool_calls,
            "wrote_behaviors": "update_behaviors" in tool_calls,
            "wrote_session_summary": "write_session_summary" in tool_calls,
            "only_cursor": len(tool_calls) == 1 and tool_calls[0] == "update_cursor",
        }
        
        # 评估决策
        decision_result = await self.evaluate_decision(
            conversation, existing_memory, agent_decision
        )
        
        # 如果写入了记忆，评估内容质量
        content_result = None
        if not agent_decision["only_cursor"]:
            extracted_content = self._extract_written_content(agent_result)
            memory_type = "preferences" if agent_decision["wrote_preferences"] else \
                         "behaviors" if agent_decision["wrote_behaviors"] else \
                         "session_summary"
            
            content_result = await self.evaluate_content(
                conversation, extracted_content, memory_type
            )
        
        # 构建结果
        return ExtractionEvalResult(
            case_id=scenario.name,
            scenario_name=scenario.name,
            should_remember_score=decision_result.get("should_remember_score", 0),
            memory_type_correct=decision_result.get("memory_type_correct", False),
            memory_type_expected=decision_result.get("memory_type_expected", "none"),
            temporary_constraint_detected=decision_result.get("temporary_constraint_detected", False),
            dedup_correct=decision_result.get("dedup_correct", True),
            decision_overall_score=decision_result.get("overall_score", 0),
            content_completeness=content_result.get("completeness") if content_result else None,
            content_accuracy=content_result.get("accuracy") if content_result else None,
            content_structured=content_result.get("structured") if content_result else None,
            content_noise_free=content_result.get("noise_free") if content_result else None,
            content_overall_score=content_result.get("overall_score") if content_result else None,
            tool_calls=tool_calls,
            judge_reason=decision_result.get("reason", ""),
            passed=self._check_passed(decision_result, content_result, scenario),
        )
    
    def _format_conversation(self, messages: list) -> str:
        """格式化对话"""
        lines = []
        for role, content in messages:
            speaker = "用户" if role == "human" else "AI"
            lines.append(f"{speaker}: {content}")
        return "\n".join(lines)
    
    def _extract_written_content(self, agent_result: dict) -> str:
        """提取写入的内容"""
        tool_calls = agent_result.get("tool_calls", [])
        for name, args in tool_calls:
            if name in ["update_preferences", "update_behaviors"]:
                return args.get("content", "")
            if name == "write_session_summary":
                return args.get("summary", "")
        return ""
    
    def _check_passed(
        self,
        decision_result: dict,
        content_result: dict | None,
        scenario,
    ) -> bool:
        """判断是否通过"""
        # 决策得分 >= 4
        if decision_result.get("overall_score", 0) < 4:
            return False
        
        # 类型正确
        if not decision_result.get("memory_type_correct", True):
            return False
        
        # 临时约束检测
        if "temporary" in scenario.name.lower():
            if not decision_result.get("temporary_constraint_detected", False):
                return False
        
        # 内容质量（如果有）
        if content_result and content_result.get("overall_score", 5) < 3:
            return False
        
        return True


# ============================================================================
# Pytest 测试类
# ============================================================================

@pytest.mark.llm_judge
class TestMemoryExtractionLLMJudge:
    """使用 LLM-as-Judge 评测记忆提取"""
    
    @pytest.fixture
    def harness(self):
        """创建 Extraction Harness"""
        return ExtractionHarness(judge_provider="openai")
    
    @pytest.fixture
    def agent_runner(self):
        """Agent 执行器（真实 API）"""
        from app.application.agents.memory.agent import run_memory_agent
        return run_memory_agent
    
    @pytest.mark.asyncio
    async def test_extraction_single_case(self, harness, agent_runner):
        """单场景评测示例"""
        from tests.memory.test_memory_eval import SCENARIO_1_PREF_FEEDBACK
        
        # 执行 Agent（真实 API）
        # agent_result = await agent_runner(...)
        agent_result = {
            "tool_calls": [
                ("update_preferences", {"content": "偏好简洁回答"}),
                ("update_memory_index", {}),
                ("update_cursor", {}),
            ]
        }
        
        # LLM Judge 评估
        result = await harness.run_case(SCENARIO_1_PREF_FEEDBACK, agent_result)
        
        assert result.decision_overall_score >= 4
        assert result.memory_type_correct
        assert result.passed
    
    @pytest.mark.asyncio
    async def test_extraction_all_cases(self, harness):
        """批量评测所有场景"""
        from tests.memory.test_memory_eval import ALL_SCENARIOS_FULL
        
        results = []
        for scenario in ALL_SCENARIOS_FULL:
            # 模拟 Agent 结果（实际运行时替换）
            agent_result = self._mock_agent_result_for_scenario(scenario)
            
            eval_result = await harness.run_case(scenario, agent_result)
            results.append(eval_result)
        
        # 生成报告
        report = self._generate_report(results)
        print(report)
        
        # 断言通过率
        pass_rate = sum(1 for r in results if r.passed) / len(results)
        assert pass_rate >= 0.8
    
    def _mock_agent_result_for_scenario(self, scenario):
        """根据场景生成模拟 Agent 结果"""
        # 实际评测时替换为真实 Agent 执行
        expected_actions = scenario.expected_actions
        
        tool_calls = []
        from tests.memory.test_memory_eval import ExpectedAction
        for action in expected_actions:
            if action == ExpectedAction.WRITE_PREFERENCES:
                tool_calls.append(("update_preferences", {"content": "..."}))
            elif action == ExpectedAction.WRITE_BEHAVIORS:
                tool_calls.append(("update_behaviors", {"content": "..."}))
            elif action == ExpectedAction.WRITE_SESSION_SUMMARY:
                tool_calls.append(("write_session_summary", {"summary": "..."}))
            elif action == ExpectedAction.UPDATE_MEMORY_INDEX:
                tool_calls.append(("update_memory_index", {}))
            elif action == ExpectedAction.ONLY_UPDATE_CURSOR:
                pass  # cursor 是最后
        
        tool_calls.append(("update_cursor", {}))
        return {"tool_calls": tool_calls}
    
    def _generate_report(self, results: list) -> str:
        """生成评估报告"""
        passed = sum(1 for r in results if r.passed)
        total = len(results)
        
        lines = [
            "=" * 70,
            "LLM-as-Judge Extraction 评估报告",
            "=" * 70,
            f"总计: {passed}/{total} 通过 ({passed/total:.1%})",
            "-" * 70,
        ]
        
        # 按类别统计
        categories = {}
        for r in results:
            cat = self._get_category(r.scenario_name)
            if cat not in categories:
                categories[cat] = {"passed": 0, "total": 0}
            categories[cat]["total"] += 1
            if r.passed:
                categories[cat]["passed"] += 1
        
        lines.append("按类别统计：")
        for cat, stats in sorted(categories.items()):
            rate = stats["passed"] / stats["total"]
            lines.append(f"  {cat}: {stats['passed']}/{stats['total']} ({rate:.1%})")
        
        lines.append("-" * 70)
        lines.append("详细结果：")
        
        for r in results:
            status = "✓" if r.passed else "✗"
            lines.append(f"{status} {r.scenario_name}")
            lines.append(f"    决策得分: {r.decision_overall_score}/5")
            lines.append(f"    类型正确: {r.memory_type_correct}")
            if r.content_overall_score:
                lines.append(f"    内容得分: {r.content_overall_score}/5")
            if not r.passed:
                lines.append(f"    原因: {r.judge_reason}")
        
        lines.append("=" * 70)
        return "\n".join(lines)
    
    def _get_category(self, name: str) -> str:
        """获取场景类别"""
        if "preference" in name.lower() or "pref" in name.lower():
            return "偏好类"
        elif "temporary" in name.lower():
            return "临时约束类"
        elif "behavior" in name.lower():
            return "行为模式类"
        elif "session" in name.lower() or "summary" in name.lower():
            return "会话摘要类"
        elif "private" in name.lower() or "skip" in name.lower():
            return "应跳过类"
        else:
            return "其他"


# ============================================================================
# 手动运行入口
# ============================================================================

async def run_extraction_harness():
    """手动运行 Extraction Harness"""
    harness = ExtractionHarness(judge_provider="openai")
    
    from tests.memory.test_memory_eval import ALL_SCENARIOS_FULL
    
    results = []
    for scenario in ALL_SCENARIOS_FULL[:10]:  # 先测试 10 个
        agent_result = {
            "tool_calls": [("update_cursor", {})]  # 简化模拟
        }
        result = await harness.run_case(scenario, agent_result)
        results.append(result)
        print(f"✓ {scenario.name}: {result.decision_overall_score}/5")
    
    # 输出报告
    passed = sum(1 for r in results if r.passed)
    print(f"\n通过率: {passed}/{len(results)}")


if __name__ == "__main__":
    asyncio.run(run_extraction_harness())
```

### 5.3 Utilization Harness 实现

```python
"""Utilization Harness - 评测记忆是否改善回答"""

import asyncio
from dataclasses import dataclass

from .judge_adapter import get_judge_adapter
from .eval_prompts import (
    UTILIZATION_PAIRWISE_CRITERIA,
    UTILIZATION_PAIRWISE_PARAMS,
)


@dataclass
class UtilizationEvalResult:
    """Utilization 评估结果"""
    case_id: str
    winner: str  # "A" | "B" | "tie"
    
    # 分数对比
    task_correctness_a: int
    task_correctness_b: int
    personalization_fit_a: int
    personalization_fit_b: int
    historical_consistency_a: int
    historical_consistency_b: int
    memory_utilization_a: int
    
    # 判断
    memory_helpful: bool  # 记忆是否有帮助
    passed: bool
    reason: str


class UtilizationHarness:
    """Utilization Harness - Pairwise 对比评测"""
    
    def __init__(self, judge_provider: str = "openai", judge_model: str = "gpt-4o"):
        self.judge = get_judge_adapter(
            provider=judge_provider,
            model=judge_model,
        )
    
    async def compare_answers(
        self,
        query: str,
        memory: str,
        answer_with_memory: str,
        answer_without_memory: str,
    ) -> UtilizationEvalResult:
        """对比两个回答"""
        
        prompt = UTILIZATION_PAIRWISE_CRITERIA.format(
            query=query,
            memory=memory,
            answer_a=answer_with_memory,
            answer_b=answer_without_memory,
        )
        
        result = await self.judge.evaluate(prompt)
        
        return UtilizationEvalResult(
            case_id="util_001",
            winner=result.get("winner", "tie"),
            task_correctness_a=result.get("task_correctness", {}).get("a", 0),
            task_correctness_b=result.get("task_correctness", {}).get("b", 0),
            personalization_fit_a=result.get("personalization_fit", {}).get("a", 0),
            personalization_fit_b=result.get("personalization_fit", {}).get("b", 0),
            historical_consistency_a=result.get("historical_consistency", {}).get("a", 0),
            historical_consistency_b=result.get("historical_consistency", {}).get("b", 0),
            memory_utilization_a=result.get("memory_utilization", {}).get("a", 0),
            memory_helpful=result.get("winner") == "A",
            passed=result.get("winner") in ["A", "tie"],
            reason=result.get("reason", ""),
        )
    
    async def run_utilization_eval(
        self,
        test_cases: list[dict],
        chat_agent_with_memory,
        chat_agent_without_memory,
    ) -> list[UtilizationEvalResult]:
        """运行 Utilization 评测"""
        
        results = []
        
        for case in test_cases:
            query = case["query"]
            memory = case["memory_artifacts"]
            
            # 生成两个回答
            answer_a = await chat_agent_with_memory(query, memory)
            answer_b = await chat_agent_without_memory(query)
            
            # Judge 对比
            result = await self.compare_answers(
                query=query,
                memory=json.dumps(memory, ensure_ascii=False),
                answer_with_memory=answer_a,
                answer_without_memory=answer_b,
            )
            
            result.case_id = case["case_id"]
            results.append(result)
        
        return results


# ============================================================================
# Utilization 测试用例
# ============================================================================

UTILIZATION_TEST_CASES = [
    {
        "case_id": "util_001",
        "query": "RAG 的召回阈值一般怎么设？",
        "memory_artifacts": {
            "preferences": "RAG 问题偏好代码示例，涉及阈值时给具体数值范围",
            "session_summaries": [
                {"summary": "讨论 RAG 召回阈值，推荐范围 0.7-0.85"}
            ]
        },
        "gold_output": {
            "must_include": ["0.7-0.85", "代码示例"],
        }
    },
    {
        "case_id": "util_002",
        "query": "怎么优化向量检索的召回率？",
        "memory_artifacts": {
            "behaviors": "关注向量检索领域，偏好实践导向",
        },
        "gold_output": {
            "must_include": ["实践方法"],
        }
    },
]


@pytest.mark.llm_judge
class TestMemoryUtilizationLLMJudge:
    """使用 LLM-as-Judge 评测记忆利用效果"""
    
    @pytest.fixture
    def harness(self):
        return UtilizationHarness()
    
    @pytest.mark.asyncio
    async def test_utilization_single(self, harness):
        """单场景 Utilization 评测"""
        case = UTILIZATION_TEST_CASES[0]
        
        # 模拟两个回答
        answer_with_memory = "RAG 召回阈值建议设置在 0.7-0.85 范围。\n\n```python\nthreshold = 0.75\n```"
        answer_without_memory = "召回阈值取决于你的场景，建议根据实际情况调整。"
        
        result = await harness.compare_answers(
            query=case["query"],
            memory=json.dumps(case["memory_artifacts"]),
            answer_with_memory=answer_with_memory,
            answer_without_memory=answer_without_memory,
        )
        
        print(f"Winner: {result.winner}")
        print(f"Memory Utilization Score: {result.memory_utilization_a}/5")
        print(f"Reason: {result.reason}")
        
        assert result.memory_helpful or result.winner == "tie"
```

---

## 六、评测执行指南

### 6.1 环境配置

```bash
# 安装依赖
pip install deepeval ragas openai anthropic

# 配置 API Key
export OPENAI_API_KEY="your_openai_key"
export ANTHROPIC_API_KEY="your_anthropic_key"
export DEEPSEEK_API_KEY="your_deepseek_key"

# 项目配置（使用已有）
# 见 backend/app/infrastructure/config/settings.py
```

### 6.2 运行评测

```bash
# 运行 Extraction Harness（真实 API + LLM Judge）
cd backend
PYTHONPATH=. uv run pytest tests/memory/llm_judge/run_extraction_eval.py -v -m llm_judge

# 运行 Utilization Harness
PYTHONPATH=. uv run pytest tests/memory/llm_judge/run_utilization_eval.py -v -m llm_judge

# 运行完整评测
PYTHONPATH=. uv run pytest tests/memory/llm_judge/ -v -m llm_judge
```

### 6.3 评测报告输出

```python
def export_evaluation_report(results: list, output_dir: Path):
    """导出评测报告"""
    
    import json
    from datetime import datetime
    
    # JSON 结果
    json_path = output_dir / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(json_path, "w") as f:
        json.dump([r.__dict__ for r in results], f, ensure_ascii=False, indent=2)
    
    # Markdown 报告
    md_path = output_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(md_path, "w") as f:
        f.write(generate_markdown_report(results))
    
    # CSV（便于分析）
    csv_path = output_dir / f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    import csv
    with open(csv_path, "w") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].__dict__.keys())
        writer.writeheader()
        writer.writerows([r.__dict__ for r in results])
    
    return json_path, md_path, csv_path
```

---

## 七、DeepEval 集成方案

### 7.1 使用 DeepEval 框架

```python
"""DeepEval 集成 - 使用官方框架"""

from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase


def create_memory_extraction_metric():
    """创建记忆提取评估指标"""
    
    metric = GEval(
        name="Memory Extraction Correctness",
        criteria="""
评估 Memory Agent 是否正确提取记忆：
1. 判断是否应该记忆（显式偏好 vs 临时约束）
2. 判断记忆类型是否正确（preferences/behaviors/session_summary）
3. 判断去重是否正确执行
""",
        evaluation_params=["Input", "Actual Output", "Expected Output"],
        threshold=0.7,
    )
    return metric


def test_memory_extraction_with_deepeval():
    """使用 DeepEval 测试"""
    
    test_case = LLMTestCase(
        input="用户说：回答简洁一点，不要写那么多废话",
        actual_output="Agent 决策: write_preferences, update_memory_index",
        expected_output="应该写入 preferences，内容包含简洁偏好",
    )
    
    metric = create_memory_extraction_metric()
    assert_test(test_case, [metric])


# 运行方式
# deepeval test run tests/memory/llm_judge/deepeval_integration.py
```

---

## 八、发布门槛

| Harness | 指标 | 门槛 | Judge 模型 |
|---------|------|------|-----------|
| Extraction | decision_overall_score | >= 4/5 | GPT-4o-mini |
| Extraction | memory_type_correct | >= 95% | GPT-4o-mini |
| Extraction | temporary_constraint_detected | >= 90% | GPT-4o-mini |
| Extraction | dedup_correct | >= 85% | GPT-4o-mini |
| Utilization | memory_helpful (A wins or tie) | >= 60% | GPT-4o |
| Utilization | memory_utilization_score | >= 4/5 | GPT-4o |

---

## 九、参考资料

- [DeepEval Documentation](https://deepeval.com/)
- [Ragas Framework](https://docs.ragas.io/)
- [G-Eval Paper](https://arxiv.org/abs/2303.16634)
- [LoCoMo Benchmark](https://snap-research.github.io/locomo/)
- [Memora Benchmark](https://arxiv.org/html/2604.20006v1)
- [OpenAI Evals](https://github.com/openai/evals)
- [MLflow LLM-as-Judge](https://mlflow.org/llm-as-a-judge)

---

## 十、下一步行动

1. **创建 `llm_judge/` 目录结构**
2. **实现 Judge 适配器**（支持 OpenAI/Anthropic/DeepSeek）
3. **编写 G-Eval 指标定义**
4. **集成真实 Agent 执行**（替换 mock）
5. **配置 CI/CD 自动评测**