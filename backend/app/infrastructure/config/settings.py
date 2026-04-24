"""基础设施层配置

全局配置管理，使用 Pydantic Settings 读取环境变量。
"""

from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# 项目根目录和模型目录
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
MODEL_DIR = PROJECT_ROOT / "models"

load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    """全局配置类

    所有配置项均可通过环境变量覆盖。
    支持 .env 文件自动加载。
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM Provider API Keys
    siliconflow_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    deepseek_api_key: str = Field(default="")
    dashscope_api_key: str = Field(default="")
    tavily_api_key: str = Field(default="")

    # 讯飞语音识别配置
    xfyun_app_id: str = Field(default="")
    xfyun_api_key: str = Field(default="")
    xfyun_api_secret: str = Field(default="")

    # Embedding 模型配置
    embedding_model_path: str = Field(default=str(MODEL_DIR / "bge-m3"))
    reranker_model_path: str = Field(default=str(MODEL_DIR / "bge-reranker-base"))

    # Qdrant 配置
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=6333)
    qdrant_collection: str = Field(default="questions")
    qdrant_test_collection: str = Field(default="questions_test")
    qdrant_vector_size: int = Field(default=1024)

    # RabbitMQ 配置
    rabbitmq_host: str = Field(default="localhost")
    rabbitmq_port: int = Field(default=5672)
    rabbitmq_user: str = Field(default="guest")
    rabbitmq_password: str = Field(default="guest")
    rabbitmq_queue: str = Field(default="answer_tasks")
    rabbitmq_dlq: str = Field(default="answer_tasks_dlq")
    rabbitmq_max_retries: int = Field(default=3)

    # Neo4j 图数据库配置
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="neo4j")
    neo4j_database: str = Field(default="neo4j")

    # Redis 配置
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_password: str = Field(default="")
    redis_db: int = Field(default=0)
    redis_ttl: int = Field(default=86400)

    # 记忆模块配置
    memory_retrieval_min_length: int = Field(default=10)
    memory_retrieval_top_k: int = Field(default=5)
    memory_retrieval_lock_timeout: int = Field(default=60)
    memory_context_max_size: int = Field(default=20 * 1024)
    memory_lock_timeout: int = Field(default=30)

    # 面试模块配置
    interview_max_follow_ups: int = Field(default=3, description="追问次数上限")

    # PostgreSQL 配置
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default="root")
    postgres_password: str = Field(default="root")
    postgres_db: str = Field(default="offer_catcher")
    postgres_test_db: str = Field(default="offer_catcher_test")

    # 应用配置
    app_name: str = Field(default="Offer-Catcher")
    log_level: str = Field(default="INFO")

    # OpenTelemetry 配置
    otlp_endpoint: str = Field(default="http://localhost:4317")
    telemetry_enabled: bool = Field(default=False)
    prometheus_port: int = Field(default=9464)

    @property
    def qdrant_url(self) -> str:
        """Qdrant URL"""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    @property
    def rabbitmq_url(self) -> str:
        """RabbitMQ URL"""
        return f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}@{self.rabbitmq_host}:{self.rabbitmq_port}/"

    @property
    def postgres_url(self) -> str:
        """PostgreSQL URL"""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


__all__ = ["Settings", "get_settings"]