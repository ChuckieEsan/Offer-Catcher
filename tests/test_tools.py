"""智能体工具功能测试

验证 Embedding、向量检索、Web 搜索工具是否正常工作。
"""
import random
import pytest

from app.db.qdrant_client import QdrantManager
from app.tools.embedding import EmbeddingTool, get_embedding_tool
from app.tools.vector_search import VectorSearchTool, get_vector_search_tool
from app.tools.web_search import WebSearchTool, get_web_search_tool


class TestEmbeddingTool:
    """Embedding 工具测试"""

    def test_embedding_tool_initialization(self):
        """测试 Embedding 工具初始化"""
        tool = EmbeddingTool()
        assert tool is not None
        assert tool.embedding_dimension == 1024
        print(f"Embedding dimension: {tool.embedding_dimension}")

    def test_embed_single_text(self):
        """测试单条文本向量化"""
        tool = EmbeddingTool()
        text = "什么是 RAG？"
        vector = tool.embed_text(text)

        assert vector is not None
        assert len(vector) == 1024  # BGE-M3 向量维度
        print(f"Single text embedding: {len(vector)} dims")

    def test_embed_batch_texts(self):
        """测试批量文本向量化"""
        tool = EmbeddingTool()
        texts = ["什么是 RAG？", "什么是 LangChain？", "什么是 Vector DB？"]
        vectors = tool.embed_texts(texts)

        assert len(vectors) == 3
        for v in vectors:
            assert len(v) == 1024  # BGE-M3 向量维度
        print(f"Batch embeddings: {len(vectors)} texts")

    def test_embed_with_context(self):
        """测试上下文拼接后向量化（Context Enrichment）"""
        tool = EmbeddingTool()
        vector = tool.embed_with_context(
            question_text="qlora怎么优化显存？",
            company="字节跳动",
            position="Agent应用开发",
        )

        assert vector is not None
        assert len(vector) == 1024  # BGE-M3 向量维度
        print(f"Context enriched embedding: {len(vector)} dims")

    def test_get_embedding_tool_singleton(self):
        """测试单例获取"""
        tool1 = get_embedding_tool()
        tool2 = get_embedding_tool()
        assert tool1 is tool2
        print("Singleton pattern verified")


class TestVectorSearchTool:
    """向量检索工具测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前置设置"""

        # 准备测试数据
        self.vector_tool = get_embedding_tool()
        self.qdrant_manager = QdrantManager()
        self.settings = self.qdrant_manager.settings

        # 删除旧集合并重新创建（向量维度已改为 1024）
        try:
            self.qdrant_manager.delete_collection()
        except Exception:
            pass
        self.qdrant_manager.create_collection_if_not_exists()

        test_questions = [
            ("字节跳动", "Agent应用开发", "什么是 RAG？", "knowledge"),
            ("字节跳动", "Agent应用开发", "讲讲你的 Agent 项目？", "project"),
            ("腾讯", "后端开发", "Python 装饰器是什么？", "knowledge"),
            ("阿里", "大模型开发", "如何优化 LLM 推理？", "knowledge"),
        ]

        for company, position, question, qtype in test_questions:
            vector = self.vector_tool.embed_with_context(question, company, position)
            self.qdrant_manager.upsert_question_with_context(
                question_text=question,
                company=company,
                position=position,
                vector=vector,
                question_type=qtype,
                mastery_level=0,
            )

        print(f"Inserted {len(test_questions)} test questions")
        yield

    def test_search_similar(self):
        """测试相似度检索"""
        search_tool = VectorSearchTool()

        # 搜索与 "RAG" 相关的内容
        results = search_tool.search_similar(
            query="什么是 RAG",
            top_k=10,
        )

        assert results is not None
        print(f"Search returned {len(results)} results")
        if results:
            print(f"Top result: {results[0].question_text}, score: {results[0].score:.4f}")

    def test_search_with_company_filter(self):
        """测试按公司过滤检索"""
        search_tool = VectorSearchTool()

        results = search_tool.search_similar(
            query="什么是 RAG",
            company="字节跳动",
            top_k=10,
        )

        # 验证所有结果都是字节跳动
        for r in results:
            assert r.company == "字节跳动"
        print(f"Filtered search (字节跳动) returned {len(results)} results")

    def test_search_with_mastery_level_filter(self):
        """测试按熟练度过滤检索"""
        search_tool = VectorSearchTool()

        results = search_tool.search_similar(
            query="什么是 RAG",
            mastery_level=0,
            top_k=10,
        )

        # 验证所有结果的 mastery_level 都是 0
        for r in results:
            assert r.mastery_level == 0
        print(f"Filtered search (mastery_level=0) returned {len(results)} results")

    def test_get_vector_search_tool_singleton(self):
        """测试单例获取"""
        tool1 = get_vector_search_tool()
        tool2 = get_vector_search_tool()
        assert tool1 is tool2
        print("Singleton pattern verified")


class TestWebSearchTool:
    """Web 搜索工具测试"""

    def test_web_search_tool_initialization(self):
        """测试 Web 搜索工具初始化"""
        tool = WebSearchTool(max_results=3)
        assert tool is not None
        assert tool.max_results == 3
        print(f"Web search tool initialized, max_results={tool.max_results}")

    def test_web_search(self):
        """测试 Web 搜索功能"""
        tool = WebSearchTool(max_results=3)

        try:
            results = tool.search("Python RAG vector database")
            print(f"Search returned {len(results)} results")

            for r in results:
                print(f"  - {r.title}")
                print(f"    URL: {r.url}")
                if r.content:
                    print(f"    Content: {r.content[:100]}...")
        except Exception as e:
            # 网络搜索可能有网络问题，仅记录
            print(f"Web search test skipped due to: {e}")

    def test_search_for_answer(self):
        """测试为答案搜索资料"""
        tool = WebSearchTool(max_results=2)

        try:
            result = tool.search_for_answer(
                question="什么是 RAG",
                company="字节跳动",
                position="Agent开发",
            )
            print(f"Search for answer result:\n{result[:500]}...")
        except Exception as e:
            print(f"Search for answer test skipped due to: {e}")

    def test_get_web_search_tool_singleton(self):
        """测试单例获取"""
        tool1 = get_web_search_tool(max_results=5)
        tool2 = get_web_search_tool(max_results=3)  # 应该返回已有实例，忽略参数
        assert tool1 is tool2
        print("Singleton pattern verified")


class TestToolsIntegration:
    """工具集成测试"""

    def test_embedding_to_search_pipeline(self):
        """测试 Embedding -> Search 完整流程"""
        # 1. Embedding
        embedding_tool = get_embedding_tool()
        query = "什么是 RAG"
        vector = embedding_tool.embed_text(query)
        print(f"1. Embedded query: {len(vector)} dims")

        # 2. Search
        search_tool = get_vector_search_tool()
        results = search_tool.search_similar(query=query, top_k=5)
        print(f"2. Search returned {len(results)} results")

        assert results is not None
        print("Integration test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])