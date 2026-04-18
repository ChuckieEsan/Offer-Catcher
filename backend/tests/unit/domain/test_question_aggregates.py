"""题库领域聚合单元测试

验证 Question、Cluster、ExtractTask 聚合的业务逻辑正确性。
"""

import pytest
from datetime import datetime

from app.domain.question.aggregates import (
    Cluster,
    ExtractTask,
    ExtractTaskStatus,
    Question,
)
from app.domain.question.utils import (
    generate_question_id,
    generate_short_id,
    verify_question_id,
)
from app.domain.shared.enums import MasteryLevel, QuestionType


class TestQuestionUtils:
    """题目 ID 生成工具测试"""

    def test_generate_question_id_returns_uuid_format(self) -> None:
        """验证返回 UUID 格式"""
        id = generate_question_id("字节跳动", "什么是 RAG？")
        # UUID 格式: 8-4-4-4-12
        assert len(id) == 36
        assert id.count("-") == 4

    def test_generate_question_id_is_deterministic(self) -> None:
        """验证 ID 生成是确定性的（幂等性）"""
        id1 = generate_question_id("字节跳动", "什么是 RAG？")
        id2 = generate_question_id("字节跳动", "什么是 RAG？")
        assert id1 == id2

    def test_generate_question_id_different_inputs(self) -> None:
        """验证不同输入产生不同 ID"""
        id1 = generate_question_id("字节跳动", "什么是 RAG？")
        id2 = generate_question_id("字节跳动", "什么是 LLM？")
        assert id1 != id2

    def test_generate_question_id_different_company(self) -> None:
        """验证不同公司产生不同 ID"""
        id1 = generate_question_id("字节跳动", "什么是 RAG？")
        id2 = generate_question_id("阿里巴巴", "什么是 RAG？")
        assert id1 != id2

    def test_generate_question_id_strips_whitespace(self) -> None:
        """验证去除空白字符"""
        id1 = generate_question_id("字节跳动", "什么是 RAG？")
        id2 = generate_question_id("  字节跳动  ", "  什么是 RAG？  ")
        assert id1 == id2

    def test_generate_short_id(self) -> None:
        """验证短 ID 生成"""
        short_id = generate_short_id("字节跳动", "什么是 RAG？", length=8)
        assert len(short_id) == 8

    def test_verify_question_id_correct(self) -> None:
        """验证 ID 校验正确"""
        id = generate_question_id("字节跳动", "什么是 RAG？")
        assert verify_question_id("字节跳动", "什么是 RAG？", id) is True

    def test_verify_question_id_wrong(self) -> None:
        """验证 ID 校验错误"""
        id = generate_question_id("字节跳动", "什么是 RAG？")
        assert verify_question_id("阿里巴巴", "什么是 RAG？", id) is False


class TestQuestionAggregate:
    """Question 聚合测试"""

    def test_create_question_with_factory_method(self) -> None:
        """验证工厂方法创建题目"""
        question = Question.create(
            question_text="什么是 RAG？",
            company="字节跳动",
            position="Agent 开发",
            question_type=QuestionType.KNOWLEDGE,
            core_entities=["RAG", "LLM"],
        )
        assert question.question_text == "什么是 RAG？"
        assert question.company == "字节跳动"
        assert question.question_type == QuestionType.KNOWLEDGE
        assert question.mastery_level == MasteryLevel.LEVEL_0
        assert question.core_entities == ["RAG", "LLM"]
        assert question.answer is None
        assert question.cluster_ids == []

    def test_create_question_generates_correct_id(self) -> None:
        """验证工厂方法生成正确的 ID"""
        question = Question.create(
            question_text="什么是 RAG？",
            company="字节跳动",
            position="Agent 开发",
            question_type=QuestionType.KNOWLEDGE,
        )
        expected_id = generate_question_id("字节跳动", "什么是 RAG？")
        assert question.question_id == expected_id

    def test_update_answer(self) -> None:
        """验证更新答案"""
        question = Question.create(
            question_text="什么是 RAG？",
            company="字节跳动",
            position="Agent 开发",
            question_type=QuestionType.KNOWLEDGE,
        )
        question.update_answer("RAG 是检索增强生成...")
        assert question.answer == "RAG 是检索增强生成..."

    def test_add_cluster(self) -> None:
        """验证添加考点簇"""
        question = Question.create(
            question_text="什么是 RAG？",
            company="字节跳动",
            position="Agent 开发",
            question_type=QuestionType.KNOWLEDGE,
        )
        question.add_cluster("cluster_rag_001")
        assert "cluster_rag_001" in question.cluster_ids

    def test_add_cluster_no_duplicate(self) -> None:
        """验证添加考点簇不重复"""
        question = Question.create(
            question_text="什么是 RAG？",
            company="字节跳动",
            position="Agent 开发",
            question_type=QuestionType.KNOWLEDGE,
        )
        question.add_cluster("cluster_rag_001")
        question.add_cluster("cluster_rag_001")
        assert len(question.cluster_ids) == 1

    def test_remove_cluster(self) -> None:
        """验证移除考点簇"""
        question = Question.create(
            question_text="什么是 RAG？",
            company="字节跳动",
            position="Agent 开发",
            question_type=QuestionType.KNOWLEDGE,
        )
        question.add_cluster("cluster_rag_001")
        question.add_cluster("cluster_rag_002")
        question.remove_cluster("cluster_rag_001")
        assert "cluster_rag_001" not in question.cluster_ids
        assert "cluster_rag_002" in question.cluster_ids

    def test_update_mastery(self) -> None:
        """验证更新熟练度"""
        question = Question.create(
            question_text="什么是 RAG？",
            company="字节跳动",
            position="Agent 开发",
            question_type=QuestionType.KNOWLEDGE,
        )
        question.update_mastery(MasteryLevel.LEVEL_1)
        assert question.mastery_level == MasteryLevel.LEVEL_1

    def test_requires_async_answer_for_knowledge(self) -> None:
        """验证 knowledge 类型需要异步答案"""
        question = Question.create(
            question_text="什么是 RAG？",
            company="字节跳动",
            position="Agent 开发",
            question_type=QuestionType.KNOWLEDGE,
        )
        assert question.requires_async_answer() is True

    def test_requires_async_answer_for_project(self) -> None:
        """验证 project 类型不需要异步答案（熔断）"""
        question = Question.create(
            question_text="请介绍一下你的项目",
            company="字节跳动",
            position="Agent 开发",
            question_type=QuestionType.PROJECT,
        )
        assert question.requires_async_answer() is False

    def test_to_context(self) -> None:
        """验证 embedding 上下文生成"""
        question = Question.create(
            question_text="什么是 RAG？",
            company="字节跳动",
            position="Agent 开发",
            question_type=QuestionType.KNOWLEDGE,
            core_entities=["RAG", "LLM"],
        )
        context = question.to_context()
        assert "字节跳动" in context
        assert "Agent 开发" in context
        assert "knowledge" in context
        assert "RAG,LLM" in context
        assert "什么是 RAG？" in context

    def test_to_payload_and_from_payload(self) -> None:
        """验证 payload 转换和恢复"""
        question = Question.create(
            question_text="什么是 RAG？",
            company="字节跳动",
            position="Agent 开发",
            question_type=QuestionType.KNOWLEDGE,
            core_entities=["RAG", "LLM"],
        )
        question.update_answer("RAG 是检索增强生成...")
        question.add_cluster("cluster_001")

        payload = question.to_payload()
        restored = Question.from_payload(payload)

        assert restored.question_id == question.question_id
        assert restored.question_text == question.question_text
        assert restored.company == question.company
        assert restored.question_type == question.question_type
        assert restored.mastery_level == question.mastery_level
        assert restored.core_entities == question.core_entities
        assert restored.answer == question.answer
        assert restored.cluster_ids == question.cluster_ids


class TestClusterAggregate:
    """Cluster 聚合测试"""

    def test_create_cluster(self) -> None:
        """验证创建考点簇"""
        cluster = Cluster(
            cluster_id="cluster_rag_001",
            cluster_name="RAG 技术应用",
            summary="RAG 检索增强生成相关题目",
            knowledge_points=["RAG", "向量检索", "LLM"],
        )
        assert cluster.cluster_id == "cluster_rag_001"
        assert cluster.cluster_name == "RAG 技术应用"
        assert cluster.question_ids == []
        assert cluster.frequency == 0

    def test_add_question(self) -> None:
        """验证添加题目引用"""
        cluster = Cluster(
            cluster_id="cluster_rag_001",
            cluster_name="RAG 技术应用",
            summary="RAG 检索增强生成相关题目",
        )
        cluster.add_question("q_001")
        assert "q_001" in cluster.question_ids
        assert cluster.frequency == 1

    def test_add_question_no_duplicate(self) -> None:
        """验证添加题目不重复"""
        cluster = Cluster(
            cluster_id="cluster_rag_001",
            cluster_name="RAG 技术应用",
            summary="RAG 检索增强生成相关题目",
        )
        cluster.add_question("q_001")
        cluster.add_question("q_001")
        assert len(cluster.question_ids) == 1
        assert cluster.frequency == 1

    def test_remove_question(self) -> None:
        """验证移除题目引用"""
        cluster = Cluster(
            cluster_id="cluster_rag_001",
            cluster_name="RAG 技术应用",
            summary="RAG 检索增强生成相关题目",
        )
        cluster.add_question("q_001")
        cluster.add_question("q_002")
        cluster.remove_question("q_001")
        assert "q_001" not in cluster.question_ids
        assert "q_002" in cluster.question_ids
        assert cluster.frequency == 1

    def test_to_payload_and_from_payload(self) -> None:
        """验证 payload 转换和恢复"""
        cluster = Cluster(
            cluster_id="cluster_rag_001",
            cluster_name="RAG 技术应用",
            summary="RAG 检索增强生成相关题目",
            knowledge_points=["RAG", "向量检索"],
        )
        cluster.add_question("q_001")

        payload = cluster.to_payload()
        restored = Cluster.from_payload(payload)

        assert restored.cluster_id == cluster.cluster_id
        assert restored.cluster_name == cluster.cluster_name
        assert restored.summary == cluster.summary
        assert restored.knowledge_points == cluster.knowledge_points
        assert restored.question_ids == cluster.question_ids
        assert restored.frequency == cluster.frequency


class TestExtractTaskAggregate:
    """ExtractTask 聚合测试"""

    def test_create_extract_task(self) -> None:
        """验证创建提取任务"""
        task = ExtractTask(
            task_id="task_001",
            source_type="image",
            source_content="https://example.com/image.jpg",
        )
        assert task.task_id == "task_001"
        assert task.status == ExtractTaskStatus.PENDING
        assert task.extracted_interview is None

    def test_start_processing(self) -> None:
        """验证开始处理"""
        task = ExtractTask(
            task_id="task_001",
            source_type="image",
            source_content="https://example.com/image.jpg",
        )
        task.start_processing()
        assert task.status == ExtractTaskStatus.PROCESSING

    def test_complete(self) -> None:
        """验证完成处理"""
        task = ExtractTask(
            task_id="task_001",
            source_type="image",
            source_content="https://example.com/image.jpg",
        )
        task.start_processing()
        extracted = {"company": "字节跳动", "position": "Agent 开发", "questions": []}
        task.complete(extracted)
        assert task.status == ExtractTaskStatus.COMPLETED
        assert task.extracted_interview == extracted

    def test_confirm(self) -> None:
        """验证确认入库"""
        task = ExtractTask(
            task_id="task_001",
            source_type="image",
            source_content="https://example.com/image.jpg",
        )
        task.start_processing()
        task.complete({"company": "字节跳动", "position": "Agent 开发", "questions": []})
        task.confirm()
        assert task.status == ExtractTaskStatus.CONFIRMED

    def test_cancel_from_pending(self) -> None:
        """验证从 pending 取消"""
        task = ExtractTask(
            task_id="task_001",
            source_type="image",
            source_content="https://example.com/image.jpg",
        )
        task.cancel()
        assert task.status == ExtractTaskStatus.CANCELLED

    def test_cancel_from_processing(self) -> None:
        """验证从 processing 取消"""
        task = ExtractTask(
            task_id="task_001",
            source_type="image",
            source_content="https://example.com/image.jpg",
        )
        task.start_processing()
        task.cancel()
        assert task.status == ExtractTaskStatus.CANCELLED

    def test_cannot_start_from_completed(self) -> None:
        """验证不能从 completed 状态开始处理"""
        task = ExtractTask(
            task_id="task_001",
            source_type="image",
            source_content="https://example.com/image.jpg",
        )
        task.start_processing()
        task.complete({})
        with pytest.raises(ValueError):
            task.start_processing()

    def test_cannot_complete_from_pending(self) -> None:
        """验证不能从 pending 状态完成"""
        task = ExtractTask(
            task_id="task_001",
            source_type="image",
            source_content="https://example.com/image.jpg",
        )
        with pytest.raises(ValueError):
            task.complete({})

    def test_is_ready_for_ingestion(self) -> None:
        """验证是否可以入库"""
        task = ExtractTask(
            task_id="task_001",
            source_type="image",
            source_content="https://example.com/image.jpg",
        )
        assert task.is_ready_for_ingestion() is False

        task.start_processing()
        task.complete({"company": "字节跳动", "position": "Agent 开发", "questions": []})
        assert task.is_ready_for_ingestion() is True

        task.confirm()
        assert task.is_ready_for_ingestion() is False

    def test_to_payload_and_from_payload(self) -> None:
        """验证 payload 转换和恢复"""
        task = ExtractTask(
            task_id="task_001",
            source_type="image",
            source_content="https://example.com/image.jpg",
        )
        task.start_processing()
        extracted = {"company": "字节跳动", "position": "Agent 开发"}
        task.complete(extracted)

        payload = task.to_payload()
        restored = ExtractTask.from_payload(payload)

        assert restored.task_id == task.task_id
        assert restored.source_type == task.source_type
        assert restored.source_content == task.source_content
        assert restored.status == task.status
        assert restored.extracted_interview == task.extracted_interview