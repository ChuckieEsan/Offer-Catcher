"""智能体工具功能测试

验证 Embedding、Web 搜索 Adapter 是否正常工作。
向量检索功能请参考 test_qdrant_client.py
"""
import pytest

from app.infrastructure.persistence.qdrant import QdrantManager
from app.infrastructure.adapters.embedding_adapter import EmbeddingAdapter, get_embedding_adapter
from app.infrastructure.adapters.web_search_adapter import WebSearchAdapter, get_web_search_adapter


class TestEmbeddingAdapter:
    """Embedding Adapter 测试"""

    def test_embedding_adapter_initialization(self):
        """测试 Embedding Adapter 初始化"""
        adapter = get_embedding_adapter()
        assert adapter is not None
        assert adapter.dimension == 1024
        print(f"Embedding dimension: {adapter.dimension}")

    def test_embed_single_text(self):
        """测试单条文本向量化"""
        adapter = get_embedding_adapter()
        text = "什么是 RAG？"
        vector = adapter.embed(text)

        assert vector is not None
        assert len(vector) == 1024  # BGE-M3 向量维度

    def test_embed_batch_texts(self):
        """测试批量文本向量化"""
        adapter = get_embedding_adapter()
        texts = [
            "什么是 RAG？",
            "如何实现向量检索？",
            "Qdrant 的使用方法",
        ]
        vectors = adapter.embed_batch(texts)

        assert vectors is not None
        assert len(vectors) == 3
        assert len(vectors[0]) == 1024

    def test_embedding_adapter_singleton(self):
        """测试 Embedding Adapter 单例"""
        adapter1 = get_embedding_adapter()
        adapter2 = get_embedding_adapter()
        assert adapter1 is adapter2


class TestWebSearchAdapter:
    """Web Search Adapter 测试"""

    def test_web_search_adapter_initialization(self):
        """测试 Web Search Adapter 初始化"""
        adapter = get_web_search_adapter()
        assert adapter is not None

    @pytest.mark.skip(reason="需要网络连接，跳过")
    def test_search(self):
        """测试搜索功能"""
        adapter = get_web_search_adapter()
        results = adapter.search("RAG 检索增强生成", max_results=3)

        assert results is not None
        assert len(results) > 0

        for result in results:
            print(f"Title: {result.title}")
            print(f"Content: {result.content[:100]}...")

    @pytest.mark.skip(reason="需要网络连接，跳过")
    def test_search_for_context(self):
        """测试搜索上下文"""
        adapter = get_web_search_adapter()
        context = adapter.search_for_context(
            question="如何实现 RAG？",
            company="字节跳动",
            position="算法工程师",
        )

        assert context is not None
        assert len(context) > 0
        print(f"Context length: {len(context)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])