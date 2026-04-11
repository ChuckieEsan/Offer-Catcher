"""Agent 评估框架测试

验证评估框架的核心功能：
1. 测试数据集是否可正确加载
2. 任务完成率评估是否返回有效分数
3. 工具提取是否正确
4. 综合评估是否正常工作
"""

import pytest

from tests.evals.datasets import (
    EVAL_DATASETS,
    get_dataset,
    get_all_test_cases,
    SIMPLE_QUERY_DATASET,
    MULTI_HOP_DATASET,
)
from tests.evals.metrics import (
    extract_tools_from_result,
    tool_correctness_score,
    task_completion_score,
    detect_repeated_calls,
    evaluate_agent_trajectory,
)


class TestDatasets:
    """测试数据集测试"""

    def test_datasets_loaded(self):
        """测试数据集已加载"""
        assert EVAL_DATASETS is not None
        assert len(EVAL_DATASETS) >= 4

    def test_simple_query_dataset(self):
        """测试简单查询数据集"""
        assert len(SIMPLE_QUERY_DATASET) >= 1
        first_case = SIMPLE_QUERY_DATASET[0]
        assert "input" in first_case
        assert "expected_tools" in first_case

    def test_multi_hop_dataset(self):
        """测试多跳推理数据集"""
        assert len(MULTI_HOP_DATASET) >= 1
        first_case = MULTI_HOP_DATASET[0]
        assert "expected_hops" in first_case

    def test_get_dataset(self):
        """测试获取特定数据集"""
        simple = get_dataset("simple_query")
        assert simple == SIMPLE_QUERY_DATASET

        # 不存在的数据集
        empty = get_dataset("nonexistent")
        assert empty == []

    def test_get_all_test_cases(self):
        """测试获取所有测试用例"""
        all_cases = get_all_test_cases()
        assert len(all_cases) >= len(SIMPLE_QUERY_DATASET)


class TestToolExtraction:
    """工具提取测试"""

    def test_extract_from_empty_result(self):
        """测试从空结果提取"""
        result = {"messages": []}
        tools = extract_tools_from_result(result)
        assert tools == []

    def test_extract_from_result_without_tools(self):
        """测试从无工具调用的结果提取"""
        from langchain_core.messages import HumanMessage, AIMessage

        result = {
            "messages": [
                HumanMessage(content="问题"),
                AIMessage(content="回答"),
            ]
        }
        tools = extract_tools_from_result(result)
        assert tools == []

    def test_extract_from_result_with_tools(self):
        """测试从有工具调用的结果提取"""
        from langchain_core.messages import AIMessage

        result = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "search_questions", "args": {"query": "test"}, "id": "call_1"},
                        {"name": "query_graph", "args": {"entity": "RAG"}, "id": "call_2"},
                    ]
                )
            ]
        }
        tools = extract_tools_from_result(result)
        assert tools == ["search_questions", "query_graph"]


class TestToolCorrectnessScore:
    """工具正确性评分测试"""

    def test_exact_match(self):
        """测试完全匹配"""
        result = tool_correctness_score(
            ["search_questions", "query_graph"],
            ["search_questions", "query_graph"],
        )
        assert result["score"] == 1.0
        assert result["correct"] is True

    def test_partial_match(self):
        """测试部分匹配"""
        result = tool_correctness_score(
            ["search_questions"],
            ["search_questions", "query_graph"],
        )
        assert result["score"] < 1.0
        assert result["recall"] == 0.5

    def test_extra_tools(self):
        """测试额外工具"""
        result = tool_correctness_score(
            ["search_questions", "search_web", "unexpected_tool"],
            ["search_questions"],
        )
        assert result["precision"] < 1.0
        assert "extra" in result["reason"]

    def test_no_expected_tools(self):
        """测试无预期工具"""
        result = tool_correctness_score(
            ["search_questions"],
            [],
        )
        assert result["score"] == 1.0
        assert result["correct"] is True


class TestTaskCompletionScore:
    """任务完成率评分测试"""

    def test_successful_completion(self):
        """测试成功完成"""
        result = task_completion_score(
            "找到了 10 道字节跳动的面试题，包含 RAG 和 Agent 相关内容",
            "查询字节跳动面试题",
            expected_keywords=["字节", "RAG", "Agent"],
        )
        assert result["score"] >= 0.8
        assert result["completed"] is True

    def test_partial_completion(self):
        """测试部分完成"""
        result = task_completion_score(
            "找到了一些题目",
            "查询字节跳动面试题",
            expected_keywords=["字节", "RAG"],
        )
        assert result["score"] < 0.8
        assert "字节" in result["reason"] or result["keyword_score"] < 1.0

    def test_empty_output(self):
        """测试空输出"""
        result = task_completion_score(
            "",
            "查询题目",
        )
        assert result["score"] == 0.0
        assert result["completed"] is False

    def test_with_ground_truth(self):
        """测试有标准答案"""
        result = task_completion_score(
            "RAG 和 LangChain 常一起考察",
            "查询共现知识点",
            ground_truth="RAG、LangChain、Agent 常一起考察",
        )
        assert result["score"] >= 0.5


class TestDetectRepeatedCalls:
    """死循环检测测试"""

    def test_no_repetition(self):
        """测试无重复"""
        tools = ["search_questions", "query_graph", "search_web"]
        repeated = detect_repeated_calls(tools)
        assert repeated == []

    def test_with_repetition(self):
        """测试有重复"""
        tools = ["search_questions", "search_questions", "search_questions", "query_graph"]
        repeated = detect_repeated_calls(tools)
        assert "search_questions" in repeated

    def test_custom_threshold(self):
        """测试自定义阈值"""
        tools = ["a", "a", "b", "b"]
        repeated = detect_repeated_calls(tools, threshold=1)
        assert "a" in repeated
        assert "b" in repeated


class TestEvaluateAgentTrajectory:
    """综合轨迹评估测试"""

    def test_successful_trajectory(self):
        """测试成功轨迹"""
        from langchain_core.messages import AIMessage

        result = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "search_questions", "args": {}, "id": "1"}]
                ),
            ],
            "last_tool_result": "找到了字节跳动的面试题，包含 RAG 和 Agent",
        }

        test_case = {
            "input": "查询字节跳动面试题",
            "expected_tools": ["search_questions"],
            "expected_keywords": ["字节", "RAG"],
        }

        eval_result = evaluate_agent_trajectory(result, test_case)

        assert eval_result["passed"] is True
        assert eval_result["overall_score"] >= 0.7

    def test_failed_trajectory(self):
        """测试失败轨迹"""
        result = {
            "messages": [],
            "last_tool_result": "",
        }

        test_case = {
            "input": "查询题目",
            "expected_tools": ["search_questions"],
        }

        eval_result = evaluate_agent_trajectory(result, test_case)

        assert eval_result["passed"] is False

    def test_loop_detection(self):
        """测试死循环检测"""
        from langchain_core.messages import AIMessage

        result = {
            "messages": [
                AIMessage(content="", tool_calls=[{"name": "search", "args": {}, "id": "1"}]),
                AIMessage(content="", tool_calls=[{"name": "search", "args": {}, "id": "2"}]),
                AIMessage(content="", tool_calls=[{"name": "search", "args": {}, "id": "3"}]),
            ],
            "last_tool_result": "结果",
        }

        test_case = {
            "input": "查询",
            "should_not_loop": True,
        }

        eval_result = evaluate_agent_trajectory(result, test_case)

        assert eval_result["has_loop"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])