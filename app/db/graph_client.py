"""Neo4j 图数据库客户端模块

提供 Neo4j 图数据库的连接、实体创建、关系管理和考频统计功能。
"""

from typing import Optional

from neo4j import GraphDatabase

from app.config.settings import get_settings
from app.utils.logger import logger


class Neo4jGraphClient:
    """Neo4j 图数据库客户端

    提供以下核心功能：
    - 连接与断开管理
    - 公司节点创建
    - 考点实体节点创建
    - 考频关系创建与更新
    - 热门考点查询
    """

    def __init__(self) -> None:
        """初始化 Neo4j 客户端"""
        self.settings = get_settings()
        self._driver = None

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._driver is not None and not self._driver._closed

    def connect(self) -> bool:
        """建立与 Neo4j 的连接

        Returns:
            是否连接成功
        """
        if self.is_connected:
            logger.info("Neo4j client already connected")
            return True

        try:
            self._driver = GraphDatabase.driver(
                self.settings.neo4j_uri,
                auth=(self.settings.neo4j_user, self.settings.neo4j_password),
            )
            # 验证连接
            self._driver.verify_connectivity()
            logger.info(f"Neo4j connected: {self.settings.neo4j_uri}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            self._driver = None
            return False

    def close(self) -> None:
        """关闭连接"""
        if self._driver and not self._driver._closed:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    def create_company_node(self, company: str) -> bool:
        """创建公司节点

        Args:
            company: 公司名称

        Returns:
            是否成功
        """
        if not self.is_connected:
            logger.warning("Neo4j not connected")
            return False

        query = """
        MERGE (c:Company {name: $company})
        RETURN c
        """

        try:
            with self._driver.session(database=self.settings.neo4j_database) as session:
                session.run(query, company=company)
            logger.debug(f"Created/merged company node: {company}")
            return True
        except Exception as e:
            logger.error(f"Failed to create company node: {e}")
            return False

    def create_entity_node(self, entity: str) -> bool:
        """创建考点实体节点

        Args:
            entity: 考点实体名称

        Returns:
            是否成功
        """
        if not self.is_connected:
            logger.warning("Neo4j not connected")
            return False

        query = """
        MERGE (e:Entity {name: $entity})
        RETURN e
        """

        try:
            with self._driver.session(database=self.settings.neo4j_database) as session:
                session.run(query, entity=entity)
            logger.debug(f"Created/merged entity node: {entity}")
            return True
        except Exception as e:
            logger.error(f"Failed to create entity node: {e}")
            return False

    def create_exam_frequency_relationship(
        self,
        company: str,
        entity: str,
        question_count: int = 1,
    ) -> bool:
        """创建或更新考频关系

        Args:
            company: 公司名称
            entity: 考点实体
            question_count: 题目数量增量

        Returns:
            是否成功
        """
        if not self.is_connected:
            logger.warning("Neo4j not connected")
            return False

        # 先确保节点存在
        self.create_company_node(company)
        self.create_entity_node(entity)

        query = """
        MATCH (c:Company {name: $company})
        MATCH (e:Entity {name: $entity})
        MERGE (c)-[r:考频 {entity: $entity}]->(e)
        SET r.count = coalesce(r.count, 0) + $count
        RETURN r
        """

        try:
            with self._driver.session(database=self.settings.neo4j_database) as session:
                session.run(
                    query,
                    company=company,
                    entity=entity,
                    count=question_count,
                )
            logger.debug(f"Updated 考频 relationship: {company} -> {entity}")
            return True
        except Exception as e:
            logger.error(f"Failed to create 考频 relationship: {e}")
            return False

    def get_top_entities(
        self,
        company: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        """获取热门考点

        Args:
            company: 公司名称（可选，不指定则查询全局）
            limit: 返回数量限制

        Returns:
            考点列表，每个元素包含 entity, count
        """
        if not self.is_connected:
            logger.warning("Neo4j not connected")
            return []

        if company:
            query = """
            MATCH (c:Company {name: $company})-[r:考频]->(e:Entity)
            RETURN e.name as entity, r.count as count
            ORDER BY r.count DESC
            LIMIT $limit
            """
            params = {"company": company, "limit": limit}
        else:
            query = """
            MATCH ()-[r:考频]->(e:Entity)
            RETURN e.name as entity, sum(r.count) as count
            ORDER BY count DESC
            LIMIT $limit
            """
            params = {"limit": limit}

        try:
            with self._driver.session(database=self.settings.neo4j_database) as session:
                result = session.run(query, **params)
                return [{"entity": record["entity"], "count": record["count"]} for record in result]
        except Exception as e:
            logger.error(f"Failed to get top entities: {e}")
            return []

    def get_company_stats(self, company: str) -> dict:
        """获取公司统计信息

        Args:
            company: 公司名称

        Returns:
            统计信息字典
        """
        if not self.is_connected:
            logger.warning("Neo4j not connected")
            return {}

        query = """
        MATCH (c:Company {name: $company})
        OPTIONAL MATCH (c)-[r:考频]->(e:Entity)
        RETURN count(DISTINCT e) as entity_count, sum(r.count) as total_questions
        """

        try:
            with self._driver.session(database=self.settings.neo4j_database) as session:
                result = session.run(query, company=company)
                record = result.single()
                if record:
                    return {
                        "entity_count": record["entity_count"] or 0,
                        "total_questions": record["total_questions"] or 0,
                    }
        except Exception as e:
            logger.error(f"Failed to get company stats: {e}")

        return {}

    def record_question_entities(
        self,
        company: str,
        entities: list[str],
    ) -> bool:
        """记录题目的考点信息

        Args:
            company: 公司名称
            entities: 考点实体列表

        Returns:
            是否成功
        """
        if not entities:
            return True

        success = True
        for entity in entities:
            if not self.create_exam_frequency_relationship(company, entity, 1):
                success = False

        return success


# 全局单例
_graph_client: Optional[Neo4jGraphClient] = None


def get_graph_client() -> Neo4jGraphClient:
    """获取图数据库客户端单例

    Returns:
        Neo4jGraphClient 实例
    """
    global _graph_client
    if _graph_client is None:
        _graph_client = Neo4jGraphClient()
    return _graph_client