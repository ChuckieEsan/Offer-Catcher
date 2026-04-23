"""答案价值实验测试用例

测试核心功能：
1. extract_metric_value：从 MetricResult 提取数值
2. load_user_queries：从 JSON 加载 Query 数据
3. context 构建：对照组 vs 实验组
4. ragas 评测：验证指标计算逻辑
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock

# 导入被测试模块
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.answer_value_experiment import (
    extract_metric_value,
    extract_metric_reason,
    load_user_queries,
    UserQuery,
    ExperimentResult,
    RAGExperiment,
    RAG_PROMPT_TEMPLATE,
    ANSWER_QUALITY_RUBRIC,
    CORRECTNESS_RUBRIC,
    COMPLETENESS_RUBRIC,
    PROFESSIONALISM_RUBRIC,
)


# ============================================================================
# 单元测试：extract_metric_value
# ============================================================================

class TestExtractMetricValue:
    """测试 MetricResult 值提取"""

    def test_extract_from_float(self):
        """直接传入 float 值"""
        result = extract_metric_value(0.85)
        assert result == 0.85

    def test_extract_from_int(self):
        """直接传入 int 值"""
        result = extract_metric_value(1)
        assert result == 1.0

    def test_extract_from_none(self):
        """传入 None 返回默认值"""
        result = extract_metric_value(None)
        assert result == 0.5

    def test_extract_from_metric_result_with_value(self):
        """从有 value 属性的 MetricResult 对象提取值"""
        mock_result = Mock()
        mock_result.value = 0.75
        result = extract_metric_value(mock_result)
        assert result == 0.75

    def test_extract_from_object_without_value(self):
        """对象没有 value 属性时尝试转为 float"""
        # 传入一个可以转为 float 的值
        result = extract_metric_value(0.6)
        assert result == 0.6

    def test_extract_from_mock_without_value_returns_default(self):
        """Mock 没有 value 属性且无法转 float 时返回默认值"""
        mock_result = Mock(spec=[])  # 空 spec，没有任何属性
        # Mock 对象无法转为 float，应该返回默认值
        result = extract_metric_value(mock_result)
        assert result == 0.5


# ============================================================================
# 单元测试：load_user_queries
# ============================================================================

class TestLoadUserQueries:
    """测试 Query 数据加载"""

    def test_load_existing_file(self):
        """加载存在的文件"""
        queries = load_user_queries()
        assert len(queries) > 0
        assert all(isinstance(q, UserQuery) for q in queries)

    def test_query_structure(self):
        """验证 Query 数据结构"""
        queries = load_user_queries()
        if queries:
            first_query = queries[0]
            assert first_query.id >= 1
            assert len(first_query.query) > 0
            assert first_query.category in ["knowledge", "scenario", "project", "behavioral", "algorithm"]
            assert first_query.domain in ["agent", "database", "architecture", "network", "troubleshooting"]

    def test_agent_queries_present(self):
        """验证 Agent 相关 Query 存在"""
        queries = load_user_queries()
        agent_queries = [q for q in queries if q.domain == "agent"]
        assert len(agent_queries) >= 5, "应该至少有 5 条 Agent 相关 Query"

    def test_queries_have_valid_ids(self):
        """验证 Query ID 连续递增"""
        queries = load_user_queries()
        ids = [q.id for q in queries]
        assert ids == sorted(ids), "ID 应该按顺序排列"
        assert ids[0] == 1, "第一个 ID 应为 1"


# ============================================================================
# 单元测试：Context 构建
# ============================================================================

class TestContextBuilding:
    """测试 context 构建逻辑"""

    @pytest.fixture
    def mock_questions(self):
        """创建模拟题目数据"""
        questions = []
        for i in range(3):
            q = Mock()
            q.question_id = f"q_{i+1}"
            q.question_text = f"这是第{i+1}个测试题目，内容较长需要截断"
            q.company = "测试公司"
            q.position = "测试岗位"
            q.answer = f"这是第{i+1}个答案，包含详细的解释内容"
            questions.append(q)
        return questions

    def test_context_without_answer(self, mock_questions):
        """测试对照组 context（无答案）"""
        experiment = RAGExperiment.__new__(RAGExperiment)
        context = experiment.build_context_without_answer(mock_questions)

        # 验证不包含答案
        assert "答案" not in context
        assert "参考答案" not in context

        # 验证包含完整题目信息
        assert "题目" in context
        assert "公司" in context
        assert "岗位" in context

        # 验证不截断题目内容
        assert "这是第1个测试题目，内容较长需要截断" in context

    def test_context_with_answer(self, mock_questions):
        """测试实验组 context（有答案）"""
        experiment = RAGExperiment.__new__(RAGExperiment)
        context = experiment.build_context_with_answer(mock_questions)

        # 验证包含答案
        assert "参考答案" in context

        # 验证包含完整题目信息
        assert "题目" in context
        assert "公司" in context
        assert "岗位" in context

        # 验证不截断答案内容
        assert "这是第1个答案，包含详细的解释内容" in context

    def test_context_format_consistency(self, mock_questions):
        """验证两组 context 格式一致性"""
        experiment = RAGExperiment.__new__(RAGExperiment)
        context_without = experiment.build_context_without_answer(mock_questions)
        context_with = experiment.build_context_with_answer(mock_questions)

        # 两组 context 都应该有相同的题目编号
        for i in range(3):
            assert f"[{i+1}]" in context_without
            assert f"[{i+1}]" in context_with

    def test_context_no_truncation(self, mock_questions):
        """验证 context 不进行截断"""
        experiment = RAGExperiment.__new__(RAGExperiment)
        context_without = experiment.build_context_without_answer(mock_questions)
        context_with = experiment.build_context_with_answer(mock_questions)

        # 验证完整内容存在
        for i, q in enumerate(mock_questions, 1):
            assert q.question_text in context_without
            assert q.question_text in context_with
            assert q.answer in context_with


# ============================================================================
# 单元测试：RAG Prompt 模板
# ============================================================================

class TestPromptTemplate:
    """测试提示词模板"""

    def test_prompt_template_rendering(self):
        """验证模板渲染正确"""
        question = "什么是 LangChain？"
        context = "参考资料：LangChain 是一个 LLM 应用框架"

        prompt = RAG_PROMPT_TEMPLATE.format(
            question=question,
            context=context
        )

        assert question in prompt
        assert context in prompt
        assert "面试辅导助手" in prompt

    def test_prompt_encourages_complete_answer(self):
        """验证提示词要求完整回答"""
        assert "完整" in RAG_PROMPT_TEMPLATE
        assert "专业" in RAG_PROMPT_TEMPLATE
        assert "准确性" in RAG_PROMPT_TEMPLATE


# ============================================================================
# 单元测试：Rubric 评测
# ============================================================================

class TestRubricEvaluation:
    """测试 Rubric 评测逻辑"""

    @pytest.fixture
    def mock_rubric_components(self):
        """模拟 Rubric 评测组件"""
        # 模拟 MetricResult
        mock_quality_result = Mock()
        mock_quality_result.value = 4.0
        mock_quality_result.reason = "回答准确，覆盖关键要点"

        mock_correctness_result = Mock()
        mock_correctness_result.value = 4.5

        mock_completeness_result = Mock()
        mock_completeness_result.value = 3.5

        mock_professionalism_result = Mock()
        mock_professionalism_result.value = 4.0

        return mock_quality_result, mock_correctness_result, mock_completeness_result, mock_professionalism_result

    @pytest.mark.asyncio
    async def test_rubric_evaluate_returns_dict(self, mock_rubric_components):
        """验证 Rubric 评测返回字典格式"""
        quality_result, correctness_result, completeness_result, professionalism_result = mock_rubric_components

        # 创建实验实例（只初始化必要部分）
        experiment = RAGExperiment.__new__(RAGExperiment)
        experiment.quality_metric = Mock()
        experiment.quality_metric.ascore = AsyncMock(return_value=quality_result)
        experiment.correctness_metric = Mock()
        experiment.correctness_metric.ascore = AsyncMock(return_value=correctness_result)
        experiment.completeness_metric = Mock()
        experiment.completeness_metric.ascore = AsyncMock(return_value=completeness_result)
        experiment.professionalism_metric = Mock()
        experiment.professionalism_metric.ascore = AsyncMock(return_value=professionalism_result)

        result = await experiment.evaluate_with_rubric(
            user_query="测试问题",
            response="测试回答",
            reference="参考答案"
        )

        assert isinstance(result, dict)
        assert "quality_score" in result
        assert "correctness" in result
        assert "completeness" in result
        assert "professionalism" in result
        assert isinstance(result["quality_score"], float)
        assert isinstance(result["correctness"], float)

    @pytest.mark.asyncio
    async def test_rubric_evaluate_handles_exception(self):
        """验证 Rubric 评测异常处理"""
        experiment = RAGExperiment.__new__(RAGExperiment)
        experiment.quality_metric = Mock()
        experiment.quality_metric.ascore = AsyncMock(side_effect=Exception("API Error"))
        experiment.correctness_metric = Mock()
        experiment.correctness_metric.ascore = AsyncMock(return_value=Mock(value=3.0))
        experiment.completeness_metric = Mock()
        experiment.completeness_metric.ascore = AsyncMock(return_value=Mock(value=3.0))
        experiment.professionalism_metric = Mock()
        experiment.professionalism_metric.ascore = AsyncMock(return_value=Mock(value=3.0))

        result = await experiment.evaluate_with_rubric(
            user_query="测试问题",
            response="测试回答",
            reference="参考答案"
        )

        # 异常时返回默认值
        assert result["quality_score"] == 3.0
        assert result["correctness"] == 3.0


class TestExtractMetricReason:
    """测试 MetricResult reason 提取"""

    def test_extract_from_result_with_reason(self):
        """从有 reason 属性的 MetricResult 提取原因"""
        mock_result = Mock()
        mock_result.reason = "评分理由"
        result = extract_metric_reason(mock_result)
        assert result == "评分理由"

    def test_extract_from_result_without_reason(self):
        """对象没有 reason 属性时返回空字符串"""
        mock_result = Mock(spec=[])  # 空 spec
        result = extract_metric_reason(mock_result)
        assert result == ""

    def test_extract_from_none_returns_empty(self):
        """传入 None 返回空字符串"""
        result = extract_metric_reason(None)
        assert result == ""


class TestRubricDefinitions:
    """测试 Rubric 定义"""

    def test_answer_quality_rubric_has_5_scores(self):
        """验证整体质量 Rubric 有 5 个评分等级"""
        assert "score1_description" in ANSWER_QUALITY_RUBRIC
        assert "score5_description" in ANSWER_QUALITY_RUBRIC
        assert len(ANSWER_QUALITY_RUBRIC) == 5

    def test_correctness_rubric_has_5_scores(self):
        """验证正确性 Rubric 有 5 个评分等级"""
        assert "score1_description" in CORRECTNESS_RUBRIC
        assert "score5_description" in CORRECTNESS_RUBRIC

    def test_rubric_descriptions_are_valid(self):
        """验证 Rubric 描述合理"""
        # 整体质量 Rubric 应包含关键词
        assert "完全错误" in ANSWER_QUALITY_RUBRIC["score1_description"]
        assert "完全准确" in ANSWER_QUALITY_RUBRIC["score5_description"]


# ============================================================================
# 集成测试：结果分析
# ============================================================================

class TestResultAnalysis:
    """测试结果分析逻辑"""

    @pytest.fixture
    def mock_results(self):
        """创建模拟实验结果"""
        results = []
        for i in range(5):
            r = ExperimentResult(
                query_id=i + 1,
                user_query=f"测试问题{i+1}",
                query_category="knowledge" if i < 3 else "scenario",
                query_domain="agent",
                retrieved_questions=["q_1", "q_2"],
                rubric_score_without=3.0,
                correctness_without=3.0,
                completeness_without=3.0,
                professionalism_without=3.0,
                rubric_score_with=4.0 + i * 0.1,  # 有提升
                correctness_with=4.0 + i * 0.1,
                completeness_with=4.0 + i * 0.1,
                professionalism_with=4.0 + i * 0.1,
            )
            results.append(r)
        return results

    def test_analyze_returns_dict(self, mock_results):
        """验证分析返回字典"""
        experiment = RAGExperiment.__new__(RAGExperiment)
        experiment.top_k = 5

        analysis = experiment.analyze_results(mock_results)

        assert isinstance(analysis, dict)
        assert "num_queries" in analysis
        assert "metrics" in analysis

    def test_analyze_calculates_means(self, mock_results):
        """验证均值计算"""
        experiment = RAGExperiment.__new__(RAGExperiment)
        experiment.top_k = 5

        analysis = experiment.analyze_results(mock_results)

        # 验证 rubric_score 统计
        rs_data = analysis["metrics"]["rubric_score"]
        assert rs_data["without_mean"] == 3.0
        assert rs_data["with_mean"] > 3.0  # 有提升
        assert rs_data["diff"] > 0  # 差值为正

    def test_analyze_counts_wins_losses(self, mock_results):
        """验证胜负计数"""
        experiment = RAGExperiment.__new__(RAGExperiment)
        experiment.top_k = 5

        analysis = experiment.analyze_results(mock_results)

        # 所有结果都有提升，wins 应为 5
        rs_data = analysis["metrics"]["rubric_score"]
        assert rs_data["wins"] == 5
        assert rs_data["losses"] == 0

    def test_analyze_by_category(self, mock_results):
        """验证按类别统计"""
        experiment = RAGExperiment.__new__(RAGExperiment)
        experiment.top_k = 5

        analysis = experiment.analyze_results(mock_results)

        # 应有 knowledge 和 scenario 两个类别
        assert "knowledge" in analysis["by_category"]
        assert "scenario" in analysis["by_category"]


# ============================================================================
# 端到端测试（Mock 外部依赖）
# ============================================================================

class TestEndToEnd:
    """端到端测试"""

    @pytest.mark.asyncio
    async def test_single_query_experiment(self):
        """单条 Query 完整流程测试"""
        # 跳过如果没有 Query 数据
        queries = load_user_queries()
        if not queries:
            pytest.skip("没有 Query 数据")

        # 只测试第一条 Query（避免耗时过长）
        experiment = RAGExperiment.__new__(RAGExperiment)
        experiment.top_k = 3
        experiment.user_queries = [queries[0]]

        # Mock 外部依赖
        experiment.generator_llm = Mock()
        experiment.generator_llm.invoke = Mock(return_value=Mock(content="测试回答内容"))

        experiment.repo = Mock()
        mock_question = Mock()
        mock_question.question_id = "q_1"
        mock_question.question_text = "测试题目内容"
        mock_question.company = "测试公司"
        mock_question.position = "测试岗位"
        mock_question.answer = "测试答案内容"
        experiment.repo.search = Mock(return_value=[(mock_question, 0.9)])

        experiment.embedding_adapter = Mock()
        experiment.embedding_adapter.embed = Mock(return_value=[0.1] * 1024)

        # Mock Rubric 指标 - 使用有 value 属性的 Mock
        mock_quality_result = Mock()
        mock_quality_result.value = 4.0
        mock_quality_result.reason = "回答准确"
        mock_correctness_result = Mock()
        mock_correctness_result.value = 4.0
        mock_completeness_result = Mock()
        mock_completeness_result.value = 4.0
        mock_professionalism_result = Mock()
        mock_professionalism_result.value = 4.0

        experiment.quality_metric = Mock()
        experiment.quality_metric.ascore = AsyncMock(return_value=mock_quality_result)
        experiment.correctness_metric = Mock()
        experiment.correctness_metric.ascore = AsyncMock(return_value=mock_correctness_result)
        experiment.completeness_metric = Mock()
        experiment.completeness_metric.ascore = AsyncMock(return_value=mock_completeness_result)
        experiment.professionalism_metric = Mock()
        experiment.professionalism_metric.ascore = AsyncMock(return_value=mock_professionalism_result)

        # 运行实验
        results = await experiment.run_experiment()

        # 验证结果
        assert len(results) == 1
        assert results[0].query_id == queries[0].id
        assert results[0].rubric_score_without == 4.0
        assert results[0].rubric_score_with == 4.0
        assert results[0].correctness_without == 4.0
        assert results[0].correctness_with == 4.0


# ============================================================================
# 运行测试
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])