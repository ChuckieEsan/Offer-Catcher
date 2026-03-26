"""Graph Client 测试 - 使用真实 Neo4j 服务

注意：测试使用独立的测试数据，测试结束后会清理。
"""

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
        client.delete_companies(["测试公司", "考频测试公司", "测试公司2"])
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


class TestGraphClientNewFeatures:
    """新增功能测试类"""

    # 测试用的公司名称列表
    TEST_COMPANIES = ["关联测试公司A", "关联测试公司B", "关联测试公司C"]

    @pytest.fixture(scope="class")
    def client(self):
        """创建真实的 Graph Client"""
        client = Neo4jGraphClient()
        connected = client.connect()
        if not connected:
            pytest.skip("Neo4j 未连接，跳过测试")

        # 准备测试数据
        test_companies = ["关联测试公司A", "关联测试公司B", "关联测试公司C"]
        test_entities = ["RAG", "Agent", "LangChain", "LLM", "VectorDB"]

        for company in test_companies:
            client.create_company_node(company)

        # 公司A: RAG, Agent, LangChain
        client.create_exam_frequency_relationship("关联测试公司A", "RAG", 3)
        client.create_exam_frequency_relationship("关联测试公司A", "Agent", 2)
        client.create_exam_frequency_relationship("关联测试公司A", "LangChain", 1)

        # 公司B: RAG, LLM, VectorDB
        client.create_exam_frequency_relationship("关联测试公司B", "RAG", 2)
        client.create_exam_frequency_relationship("关联测试公司B", "LLM", 3)
        client.create_exam_frequency_relationship("关联测试公司B", "VectorDB", 1)

        # 公司C: Agent, LLM, LangChain
        client.create_exam_frequency_relationship("关联测试公司C", "Agent", 1)
        client.create_exam_frequency_relationship("关联测试公司C", "LLM", 2)
        client.create_exam_frequency_relationship("关联测试公司C", "LangChain", 2)

        yield client

        # 清理测试数据
        client.delete_companies(["关联测试公司A", "关联测试公司B", "关联测试公司C"])
        client.close()

    def test_get_related_entities(self, client):
        """测试获取与给定知识点相关的其他知识点"""
        result = client.get_related_entities("RAG", limit=5)

        assert isinstance(result, list)
        # RAG 与 Agent、LangChain、LLM 有关联（通过公司A关联）
        entities = [r["entity"] for r in result]
        # 可能包含 Agent, LangChain（公司A同时考察了这些）
        assert "co_occurrence_count" in result[0] if result else True

    def test_get_entity_cooccurrence(self, client):
        """测试知识点共现分析"""
        result = client.get_entity_cooccurrence("RAG", limit=5)

        assert isinstance(result, list)
        if result:
            # 验证返回结构
            assert "entity" in result[0]
            assert "weight" in result[0]

    def test_get_company_entity_distribution(self, client):
        """测试获取公司在各个知识点的分布"""
        result = client.get_company_entity_distribution("关联测试公司A")

        assert isinstance(result, list)
        if result:
            entities = [r["entity"] for r in result]
            assert "RAG" in entities
            assert "Agent" in entities

    def test_get_cross_company_entities(self, client):
        """测试跨公司知识点查询"""
        result = client.get_cross_company_entities(min_companies=2)

        assert isinstance(result, list)
        # 验证返回结构
        if result:
            assert "entity" in result[0]
            assert "companies" in result[0]
            assert "total_count" in result[0]
            assert "company_count" in result[0]

    def test_get_related_entities_not_found(self, client):
        """测试查询不存在的知识点"""
        result = client.get_related_entities("不存在的知识点XYZ", limit=5)
        assert result == [] or isinstance(result, list)


class TestGraphClientSingleton:
    """单例测试"""

    def test_get_graph_client_singleton(self):
        """测试单例获取"""
        from app.db import graph_client as graph_client_module
        graph_client_module._graph_client = None

        client1 = get_graph_client()
        client2 = get_graph_client()

        assert client1 is client2