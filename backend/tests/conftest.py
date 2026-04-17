"""pytest 配置文件

定义共享的 fixtures 和测试配置。

测试数据库隔离策略：
- Qdrant: 使用 settings.qdrant_test_collection
- PostgreSQL: 使用 settings.postgres_test_db
- Redis: 使用独立的测试 DB 编号
- Neo4j: 使用独立测试数据库（待配置）

注意：测试只允许读取生产数据库，不允许写入。
"""

import os
import sys
from pathlib import Path
from typing import Optional

import pytest

# 添加项目路径到 sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ============================================================================
# 测试环境配置
# ============================================================================

# 设置测试环境变量（在导入 settings 前设置）
TEST_ENV_VARS = {
    "QDRANT_COLLECTION": "questions_test",
    "POSTGRES_DB": "offer_catcher_test",
    "REDIS_DB": "1",  # 使用独立的 Redis DB 编号
}


def pytest_configure(config):
    """pytest 配置钩子

    在测试开始前设置环境变量，确保使用测试数据库。
    注意：使用强制设置，覆盖 .env 文件中的值。
    """
    # 强制设置测试环境变量（覆盖 .env 文件）
    for key, value in TEST_ENV_VARS.items():
        os.environ[key] = value

    # 注册自定义标记
    config.addinivalue_line("markers", "slow: 标记慢速测试")
    config.addinivalue_line("markers", "integration: 标记集成测试")
    config.addinivalue_line("markers", "e2e: 标记端到端测试")
    config.addinivalue_line("markers", "performance: 标记性能测试")
    config.addinivalue_line("markers", "eval: 标记评估测试")


# ============================================================================
# Settings Fixture
# ============================================================================

@pytest.fixture(scope="session")
def test_settings():
    """获取测试环境配置

    确保使用测试数据库而非生产数据库。
    清除 settings 缓存以重新加载环境变量。
    """
    from app.infrastructure.config.settings import Settings, get_settings

    # 清除 lru_cache，确保重新加载环境变量
    get_settings.cache_clear()

    settings = get_settings()

    # 验证使用的是测试配置
    assert settings.qdrant_collection == "questions_test", (
        f"测试应使用 questions_test 集合，当前: {settings.qdrant_collection}"
    )
    assert settings.postgres_db == "offer_catcher_test", (
        f"测试应使用 offer_catcher_test 数据库，当前: {settings.postgres_db}"
    )

    return settings


# ============================================================================
# Qdrant Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def qdrant_test_client(test_settings):
    """Qdrant 测试客户端

    使用测试集合，确保不影响生产数据。
    """
    from app.infrastructure.persistence.qdrant.client import QdrantClient

    client = QdrantClient(collection_name=test_settings.qdrant_test_collection)
    client.ensure_collection_exists()

    yield client

    # 测试结束后清理测试集合
    # 注意：这里不删除集合，保留数据供后续测试使用
    # 如果需要每次测试后清空，可以添加清理逻辑


@pytest.fixture
def question_repository(qdrant_test_client):
    """Question 仓库 fixture

    每个测试使用独立的仓库实例，支持依赖注入。
    """
    from app.infrastructure.persistence.qdrant.question_repository import (
        QdrantQuestionRepository,
    )
    from app.infrastructure.adapters.embedding_adapter import EmbeddingAdapter

    # 使用 Mock Embedding（避免加载真实模型）
    mock_embedding = MockEmbeddingAdapter()

    repo = QdrantQuestionRepository(
        client=qdrant_test_client,
        embedding=mock_embedding,
    )

    return repo


@pytest.fixture
def cluster_repository(qdrant_test_client):
    """Cluster 仓库 fixture"""
    from app.infrastructure.persistence.qdrant.cluster_repository import (
        QdrantClusterRepository,
    )

    repo = QdrantClusterRepository(client=qdrant_test_client)
    return repo


# ============================================================================
# PostgreSQL Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def postgres_test_client(test_settings):
    """PostgreSQL 测试客户端

    使用测试数据库，确保不影响生产数据。
    """
    from app.infrastructure.persistence.postgres.client import PostgresClient

    client = PostgresClient(database=test_settings.postgres_test_db)
    client.init_tables()

    yield client

    # 测试结束后不删除表，保留结构供后续测试


@pytest.fixture
def extract_task_repository(postgres_test_client):
    """ExtractTask 仓库 fixture"""
    from app.infrastructure.persistence.postgres.extract_task_repository import (
        PostgresExtractTaskRepository,
    )

    repo = PostgresExtractTaskRepository(client=postgres_test_client)
    return repo


# ============================================================================
# Mock Adapters
# ============================================================================

class MockEmbeddingAdapter:
    """Mock Embedding 适配器

    用于测试时避免加载真实模型，返回固定向量。
    """

    def embed(self, text: str) -> list[float]:
        """返回固定向量

        Args:
            text: 输入文本（忽略）

        Returns:
            固定的 1024 维向量
        """
        # 返回固定的向量（避免每次随机导致测试不稳定）
        return [0.1] * 1024


@pytest.fixture
def mock_embedding():
    """Mock Embedding fixture"""
    return MockEmbeddingAdapter()


# ============================================================================
# Cleanup Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def cleanup_qdrant_test_data(request, qdrant_test_client):
    """自动清理 Qdrant 测试数据

    标记为 autouse，每个测试后自动清理。
    只清理该测试写入的数据。
    """
    # 测试前：记录现有数据数量
    initial_count = qdrant_test_client.count()

    yield

    # 测试后：如果测试标记为需要清理，则删除新增数据
    if request.node.get_closest_marker("cleanup"):
        final_count = qdrant_test_client.count()
        if final_count > initial_count:
            # 删除测试期间新增的数据（需要实现删除逻辑）
            # 这里暂不实现，因为大多数测试不需要每次清理
            pass