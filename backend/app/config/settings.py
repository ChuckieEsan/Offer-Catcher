"""全局配置管理模块

使用 Pydantic Settings 读取环境变量。
支持从 .env 文件加载配置。
"""

from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# 项目根目录和模型目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
MODEL_DIR = PROJECT_ROOT / "models"

load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    """全局配置类

    所有配置项均可通过环境变量覆盖。
    支持 .env 文件自动加载。
    """

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM Provider API Keys（从环境变量加载）
    siliconflow_api_key: str = Field(
        description="SiliconFlow API Key",
        default="",
    )
    openai_api_key: str = Field(
        description="OpenAI API Key",
        default="",
    )
    deepseek_api_key: str = Field(
        description="DeepSeek API Key",
        default="",
    )
    dashscope_api_key: str = Field(
        description="阿里云百炼 DashScope API Key",
        default="",
    )
    tavily_api_key: str = Field(
        description="Tavily Web Search API Key",
        default="",
    )

    # 讯飞语音识别配置
    xfyun_app_id: str = Field(
        description="讯飞 AppID",
        default="",
    )
    xfyun_api_key: str = Field(
        description="讯飞 API Key",
        default="",
    )
    xfyun_api_secret: str = Field(
        description="讯飞 API Secret",
        default="",
    )

    # Embedding 模型配置
    embedding_model_path: str = Field(
        description="Embedding 模型路径（BGE-M3）",
        default=str(MODEL_DIR / "bge-m3"),
    )
    reranker_model_path: str = Field(
        description="Reranker 模型路径（BGE-Reranker）",
        default=str(MODEL_DIR / "bge-reranker-base"),
    )

    # Qdrant 配置
    qdrant_host: str = Field(
        description="Qdrant 服务地址",
        default="localhost",
    )
    qdrant_port: int = Field(
        description="Qdrant 端口",
        default=6333,
    )
    qdrant_collection: str = Field(
        description="Qdrant 集合名称",
        default="questions",
    )
    qdrant_test_collection: str = Field(
        description="Qdrant 测试集合名称",
        default="questions_test",
    )
    qdrant_vector_size: int = Field(
        description="向量维度（BGE-M3 为 1024）",
        default=1024,
    )

    # RabbitMQ 配置
    rabbitmq_host: str = Field(
        description="RabbitMQ 服务地址",
        default="localhost",
    )
    rabbitmq_port: int = Field(
        description="RabbitMQ 端口",
        default=5672,
    )
    rabbitmq_user: str = Field(
        description="RabbitMQ 用户名",
        default="guest",
    )
    rabbitmq_password: str = Field(
        description="RabbitMQ 密码",
        default="guest",
    )
    rabbitmq_queue: str = Field(
        description="队列名称",
        default="answer_tasks",
    )
    rabbitmq_dlq: str = Field(
        description="死信队列名称",
        default="answer_tasks_dlq",
    )
    rabbitmq_max_retries: int = Field(
        description="消息最大重试次数",
        default=3,
    )

    # Neo4j 图数据库配置
    neo4j_uri: str = Field(
        description="Neo4j 连接 URI",
        default="bolt://localhost:7687",
    )
    neo4j_user: str = Field(
        description="Neo4j 用户名",
        default="neo4j",
    )
    neo4j_password: str = Field(
        description="Neo4j 密码",
        default="neo4j",
    )
    neo4j_database: str = Field(
        description="Neo4j 数据库名称",
        default="neo4j",
    )

    # Redis 配置（短期记忆）
    redis_host: str = Field(
        description="Redis 服务地址",
        default="localhost",
    )
    redis_port: int = Field(
        description="Redis 端口",
        default=6379,
    )
    redis_password: str = Field(
        description="Redis 密码",
        default="",
    )
    redis_db: int = Field(
        description="Redis 数据库编号",
        default=0,
    )
    redis_ttl: int = Field(
        description="短期记忆 TTL（秒）",
        default=86400,  # 24 小时
    )

    # 记忆模块配置
    memory_retrieval_min_length: int = Field(
        description="触发记忆检索的最小消息长度",
        default=10,
    )
    memory_retrieval_top_k: int = Field(
        description="每次记忆检索返回的最大条数",
        default=5,
    )
    memory_retrieval_lock_timeout: int = Field(
        description="记忆检索锁超时时间（秒）",
        default=60,
    )
    memory_context_max_size: int = Field(
        description="记忆上下文最大窗口大小（字节）",
        default=20 * 1024,  # 20kb
    )
    memory_lock_timeout: int = Field(
        description="记忆更新锁超时时间（秒）",
        default=30,
    )

    # PostgreSQL 配置（历史对话）
    postgres_host: str = Field(
        description="PostgreSQL 服务地址",
        default="localhost",
    )
    postgres_port: int = Field(
        description="PostgreSQL 端口",
        default=5432,
    )
    postgres_user: str = Field(
        description="PostgreSQL 用户名",
        default="root",
    )
    postgres_password: str = Field(
        description="PostgreSQL 密码",
        default="root",
    )
    postgres_db: str = Field(
        description="PostgreSQL 数据库名称",
        default="offer_catcher",
    )
    postgres_test_db: str = Field(
        description="PostgreSQL 测试数据库名称",
        default="offer_catcher_test",
    )

    # 应用配置
    app_name: str = Field(
        description="应用名称",
        default="Offer-Catcher",
    )
    log_level: str = Field(
        description="日志级别",
        default="INFO",
    )

    # OpenTelemetry 配置
    otlp_endpoint: str = Field(
        description="OpenTelemetry OTLP endpoint (Jaeger traces)",
        default="http://localhost:4317",
    )
    telemetry_enabled: bool = Field(
        description="是否启用 OpenTelemetry",
        default=False,
    )
    prometheus_port: int = Field(
        description="Prometheus metrics 暴露端口",
        default=9464,
    )

    @property
    def qdrant_url(self) -> str:
        """获取 Qdrant 完整连接 URL"""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    @property
    def rabbitmq_url(self) -> str:
        """获取 RabbitMQ 完整连接 URL"""
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/"
        )

    @property
    def postgres_url(self) -> str:
        """获取 PostgreSQL 连接 URL（用于 LangGraph checkpointer）"""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例

    使用 LRU 缓存确保配置对象在整个应用生命周期内只加载一次。
    """
    return Settings()


__all__ = ["Settings", "get_settings"]