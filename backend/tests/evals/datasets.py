"""Agent 测试数据集

定义三类测试数据：
1. 简单查询（1 步工具调用）
2. 多跳推理（2-3 步）
3. 错误恢复（检测死循环、错误处理）
"""

from typing import TypedDict


class TestCase(TypedDict, total=False):
    """测试用例定义"""
    input: str  # 用户输入
    expected_tools: list[str]  # 预期调用的工具列表
    expected_keywords: list[str]  # 预期输出包含的关键词
    expected_hops: int  # 预期推理跳数
    max_hops: int  # 最大允许跳数
    ground_truth: str  # 标准答案（可选）
    expected_behavior: str  # 预期行为描述
    should_not_loop: bool  # 是否不应该循环
    check_personalization: bool  # 是否检查个性化


# ==================== 简单查询测试集 ====================

SIMPLE_QUERY_DATASET: list[TestCase] = [
    {
        "input": "字节跳动 Agent 开发岗位的面试题",
        "expected_tools": ["search_questions"],
        "expected_keywords": ["字节", "Agent"],
        "max_hops": 1,
    },
    {
        "input": "RAG 和 Vector Database 有什么区别",
        "expected_tools": ["search_questions", "search_web"],
        "expected_keywords": ["RAG", "Vector"],
        "max_hops": 2,
    },
    {
        "input": "腾讯后端开发面试常考什么",
        "expected_tools": ["search_questions"],
        "expected_keywords": ["腾讯"],
        "max_hops": 1,
    },
    {
        "input": "帮我找一下 LangChain 相关的题目",
        "expected_tools": ["search_questions"],
        "expected_keywords": ["LangChain"],
        "max_hops": 1,
    },
]


# ==================== 多跳推理测试集 ====================

MULTI_HOP_DATASET: list[TestCase] = [
    {
        "input": "字节跳动 Agent 岗位最常考的知识点，以及这些知识点和哪些其他知识点一起考察",
        "expected_tools": ["search_questions", "query_graph"],
        "expected_hops": 2,
        "expected_keywords": ["RAG", "LangChain", "共现"],
        "ground_truth": "RAG、LangChain、Agent 常一起考察",
        "max_hops": 3,
    },
    {
        "input": "我正在准备字节跳动的 Agent 岗位面试，请给我推荐复习顺序",
        "expected_tools": ["search_questions", "query_graph", "get_user_memory"],
        "expected_hops": 3,
        "check_personalization": True,
        "max_hops": 4,
    },
    {
        "input": "查询字节跳动 Agent 岗位面试题，并找出高频考点",
        "expected_tools": ["search_questions", "query_graph"],
        "expected_keywords": ["高频", "考点"],
        "max_hops": 3,
    },
]


# ==================== 错误恢复测试集 ====================

ERROR_HANDLING_DATASET: list[TestCase] = [
    {
        "input": "查询一个不存在的公司 xyz123 的面试题",
        "expected_behavior": "告知用户没有数据，建议其他公司",
        "should_not_loop": True,
        "max_hops": 2,
    },
    {
        "input": "帮我搜索一个空的关键词",
        "expected_behavior": "提示用户提供有效关键词",
        "should_not_loop": True,
        "max_hops": 2,
    },
    {
        "input": "查询一个很长的随机字符串 abcdefghijklmnopqrstuvwxyz1234567890",
        "expected_behavior": "正常处理或提示无效",
        "should_not_loop": True,
        "max_hops": 2,
    },
]


# ==================== 长期记忆测试集 ====================

MEMORY_DATASET: list[TestCase] = [
    {
        "input": "记住我偏好简洁的回答",
        "expected_tools": ["save_user_preferences"],
        "expected_keywords": ["记住", "偏好"],
        "max_hops": 1,
    },
    {
        "input": "更新我的目标公司为字节跳动",
        "expected_tools": ["save_user_profile"],
        "expected_keywords": ["字节"],
        "max_hops": 1,
    },
]


# ==================== 合并数据集 ====================

EVAL_DATASETS = {
    "simple_query": SIMPLE_QUERY_DATASET,
    "multi_hop": MULTI_HOP_DATASET,
    "error_handling": ERROR_HANDLING_DATASET,
    "memory": MEMORY_DATASET,
}


def get_dataset(name: str) -> list[TestCase]:
    """获取指定名称的测试数据集"""
    return EVAL_DATASETS.get(name, [])


def get_all_test_cases() -> list[TestCase]:
    """获取所有测试用例"""
    all_cases = []
    for dataset in EVAL_DATASETS.values():
        all_cases.extend(dataset)
    return all_cases


__all__ = [
    "TestCase",
    "EVAL_DATASETS",
    "SIMPLE_QUERY_DATASET",
    "MULTI_HOP_DATASET",
    "ERROR_HANDLING_DATASET",
    "MEMORY_DATASET",
    "get_dataset",
    "get_all_test_cases",
]