"""Graph Client 测试 - 使用真实 Neo4j 服务"""

import pytest

from app.db.graph_client import Neo4jGraphClient, get_graph_client


class TestNeo4jGraphClient:
    """Neo4j Graph Client 测试类（真实服务）"""

    @pytest.fixture(scope="class")
    def client(self):
        """创建真实的 Graph Client"""
        client = Neo4jGraphClient()
        # 尝试连接
        connected = client.connect()
        if not connected:
            pytest.skip("Neo4j 未连接，跳过测试")

        yield client

        # 清理测试数据
        client.close()

    def test_is_connected(self, client):
        """测试连接状态"""
        assert client.is_connected is True

    def test_create_company_node(self, client):
        """测试创建公司节点"""
        result = client.create_company_node("测试公司")
        assert result is True

    def test_create_entity_node(self, client):
        """测试创建考点实体节点"""
        result = client.create_entity_node("测试考点")
        assert result is True

    def test_create_exam_frequency_relationship(self, client):
        """测试创建考频关系"""
        result = client.create_exam_frequency_relationship("测试公司", "测试考点", 1)
        assert result is True

    def test_get_top_entities_with_company(self, client):
        """测试获取公司热门考点"""
        # 先创建数据
        client.create_company_node("考频测试公司")
        client.create_exam_frequency_relationship("考频测试公司", "RAG", 5)
        client.create_exam_frequency_relationship("考频测试公司", "Agent", 3)

        result = client.get_top_entities(company="考频测试公司", limit=5)

        assert len(result) >= 2
        entities = [r["entity"] for r in result]
        assert "RAG" in entities

    def test_get_top_entities_global(self, client):
        """测试获取全局热门考点"""
        result = client.get_top_entities(limit=10)
        assert isinstance(result, list)

    def test_get_company_stats(self, client):
        """测试获取公司统计"""
        result = client.get_company_stats("考频测试公司")
        assert "entity_count" in result
        assert "total_questions" in result

    def test_record_question_entities(self, client):
        """测试记录题目考点"""
        entities = ["Python", "RAG", "LLM"]
        result = client.record_question_entities("测试公司2", entities)
        assert result is True

        # 验证数据已记录
        top = client.get_top_entities(company="测试公司2", limit=5)
        assert len(top) >= 3

    def test_close(self, client):
        """测试关闭连接"""
        # 重新连接
        client.connect()
        assert client.is_connected is True

        client.close()
        assert client.is_connected is False


class TestGraphClientSingleton:
    """单例测试"""

    def test_get_graph_client_singleton(self):
        """测试单例获取"""
        from app.db import graph_client as graph_client_module
        graph_client_module._graph_client = None

        client1 = get_graph_client()
        client2 = get_graph_client()

        assert client1 is client2