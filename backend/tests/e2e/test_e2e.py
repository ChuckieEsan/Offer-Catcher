"""端到端集成测试

验证完整的业务流程：
1. Ingestion Pipeline：题目入库
2. Retrieval Pipeline：题目检索
"""

import pytest

from app.models import QuestionItem, ExtractedInterview, QuestionType, MasteryLevel
from app.utils.hasher import generate_question_id
from app.pipelines.ingestion import get_ingestion_pipeline
from app.pipelines.retrieval import get_retrieval_pipeline


class TestEndToEnd:
    """端到端测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前置设置"""
        self.ingestion = get_ingestion_pipeline()
        self.retrieval = get_retrieval_pipeline()

    @pytest.mark.asyncio
    async def test_complete_flow(self):
        """测试完整流程：入库 -> 检索"""
        # ========== 1. 入库 ==========
        # 创建面试数据
        interview = ExtractedInterview(
            company='字节跳动',
            position='Agent应用开发',
            questions=[
                QuestionItem(
                    question_id=generate_question_id('字节跳动', '什么是 RAG？'),
                    question_text='什么是 RAG？',
                    question_type=QuestionType.KNOWLEDGE,
                    company='字节跳动',
                    position='Agent应用开发',
                ),
                QuestionItem(
                    question_id=generate_question_id('字节跳动', '讲讲你的 Agent 项目？'),
                    question_text='讲讲你的 Agent 项目？',
                    question_type=QuestionType.PROJECT,
                    company='字节跳动',
                    position='Agent应用开发',
                ),
                QuestionItem(
                    question_id=generate_question_id('腾讯', 'Python 装饰器是什么？'),
                    question_text='Python 装饰器是什么？',
                    question_type=QuestionType.KNOWLEDGE,
                    company='腾讯',
                    position='后端开发',
                ),
            ]
        )

        # 执行入库
        result = await self.ingestion.process(interview)

        print(f"\n=== Ingestion Result ===")
        print(f"Processed: {result.processed}")
        print(f"Async tasks: {result.async_tasks}")
        print(f"Question IDs: {result.question_ids}")

        # 验证入库结果
        assert result.processed == 3
        assert result.async_tasks == 2  # knowledge 类型才发异步任务
        assert len(result.question_ids) == 3

        # ========== 2. 检索 ==========
        # 检索所有题目
        all_results = self.retrieval.search(query='什么是 RAG', k=10)
        print(f"\n=== Search All Results ===")
        print(f"Found: {len(all_results)}")
        for r in all_results:
            print(f"  - {r.question_text} ({r.company})")

        assert len(all_results) > 0

        # 按公司过滤检索
        bytedance_results = self.retrieval.search(
            query='什么是 RAG',
            company='字节跳动',
            k=10
        )
        print(f"\n=== Search (字节跳动) ===")
        print(f"Found: {len(bytedance_results)}")
        for r in bytedance_results:
            print(f"  - {r.question_text} ({r.company})")
            assert r.company == '字节跳动'

        # 按熟练度过滤检索
        level0_results = self.retrieval.search(
            query='Python',
            mastery_level=0,
            k=10
        )
        print(f"\n=== Search (mastery_level=0) ===")
        print(f"Found: {len(level0_results)}")
        for r in level0_results:
            print(f"  - {r.question_text} (level={r.mastery_level})")
            assert r.mastery_level == 0

        print("\n=== End-to-end test PASSED ===")


class TestRetrievalPipeline:
    """检索流水线测试"""

    def test_search_by_company(self):
        """测试按公司检索"""
        retrieval = get_retrieval_pipeline()

        results = retrieval.search(
            query='什么是',
            company='腾讯',
            k=10
        )

        print(f"\n=== Search by Company (腾讯) ===")
        print(f"Found: {len(results)}")
        for r in results:
            print(f"  - {r.question_text} ({r.company})")
            assert r.company == '腾讯'

    def test_search_by_type(self):
        """测试按题目类型检索"""
        retrieval = get_retrieval_pipeline()

        results = retrieval.search(
            query='项目',
            question_type='project',
            k=10
        )

        print(f"\n=== Search by Type (project) ===")
        print(f"Found: {len(results)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])