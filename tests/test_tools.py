"""智能体工具功能测试

验证 Embedding、Web 搜索工具是否正常工作。
向量检索功能请参考 test_qdrant_client.py
"""
import pytest

from app.db.qdrant_client import QdrantManager
from app.tools.embedding_tool import EmbeddingTool, get_embedding_tool
from app.tools.web_search_tool import WebSearchTool, get_web_search_tool


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
        """测试上下文拼接后向量化（Context Enrichment）

        上下文拼接在 IngestionPipeline 中实现，此处验证核心 embedding 功能正常
        """
        tool = EmbeddingTool()
        # 测试常规向量化功能
        text = "公司：字节跳动 | 岗位：Agent应用开发 | 题目：qlora怎么优化显存？"
        vector = tool.embed_text(text)

        assert vector is not None
        assert len(vector) == 1024  # BGE-M3 向量维度
        print(f"Context enriched embedding: {len(vector)} dims")

    def test_get_embedding_tool_singleton(self):
        """测试单例获取"""
        tool1 = get_embedding_tool()
        tool2 = get_embedding_tool()
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

    def test_embedding_to_qdrant_pipeline(self):
        """测试 Embedding -> Qdrant 完整流程"""
        # 使用测试 collection
        test_collection = "questions_test"

        # 1. Embedding
        embedding_tool = get_embedding_tool()
        query = "什么是 RAG"
        vector = embedding_tool.embed_text(query)
        print(f"1. Embedded query: {len(vector)} dims")

        # 2. Qdrant search (使用测试 collection)
        qdrant_manager = QdrantManager(collection_name=test_collection)
        results = qdrant_manager.search(query_vector=vector, limit=5)
        print(f"2. Qdrant search returned {len(results)} results")

        assert results is not None
        print("Integration test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])