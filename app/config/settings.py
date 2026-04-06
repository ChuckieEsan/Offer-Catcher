"""全局配置管理模块

使用 Pydantic Settings 读取环境变量。
支持从 .env 文件加载配置。
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from langchain_openai import ChatOpenAI
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Provider 基础配置
PROVIDERS_CONFIG = {
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "models": {
            "chat": "deepseek-chat",
            "vision": "Qwen/Qwen3-VL-8B-Instruct",
        }
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "models": {
            "chat": "gpt-4o",
            "vision": "gpt-4o",
        }
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "models": {
            "chat": "deepseek-chat",
        }
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": {
            "chat": "qwen3.6-plus",
            "vision": "qwen3.6-plus",
        }
    },
}


class Settings(BaseSettings):
    """全局配置类

    所有配置项均可通过环境变量覆盖。
    支持 .env 文件自动加载。

    Environment Variables:
        SILICONFLOW_API_KEY: SiliconFlow API Key
        OPENAI_API_KEY: OpenAI API Key
        DEEPSEEK_API_KEY: DeepSeek API Key
        DASHSCOPE_API_KEY: 阿里云百炼 DashScope API Key
        TAVILY_API_KEY: Tavily Web Search API Key
        QDRANT_HOST: Qdrant 服务地址（可选，默认 localhost）
        QDRANT_PORT: Qdrant 端口（可选，默认 6333）
        QDRANT_COLLECTION: Qdrant 集合名称（可选，默认 questions）
        RABBITMQ_HOST: RabbitMQ 服务地址（可选，默认 localhost）
        RABBITMQ_PORT: RabbitMQ 端口（可选，默认 5672）
        RABBITMQ_USER: RabbitMQ 用户名（可选，默认 guest）
        RABBITMQ_PASSWORD: RabbitMQ 密码（可选，默认 guest）
        RABBITMQ_QUEUE: 队列名称（可选，默认 answer_tasks）
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

    def get_provider_config(self, provider: str) -> dict:
        """获取指定 provider 的完整配置

        Args:
            provider: provider 名称

        Returns:
            包含 api_key, base_url, models 的字典
        """
        if provider not in PROVIDERS_CONFIG:
            raise ValueError(f"Unknown provider: {provider}")

        config = PROVIDERS_CONFIG[provider].copy()
        config["api_key"] = getattr(self, f"{provider}_api_key")
        return config


def create_llm(provider: str, model_type: str = "chat", **kwargs) -> ChatOpenAI:
    """工厂函数：创建 LLM 实例

    Args:
        provider: provider 名称 (siliconflow/openai/deepseek)
        model_type: 模型类型 ("chat" 或 "vision")
        **kwargs: 其他传递给 ChatOpenAI 的参数

    Returns:
        ChatOpenAI 实例
    """
    settings = get_settings()
    config = settings.get_provider_config(provider)

    model = config["models"].get(model_type)
    if not model:
        raise ValueError(f"Provider {provider} does not support model type: {model_type}")

    return ChatOpenAI(
        model=model,
        api_key=config["api_key"],
        base_url=config["base_url"],
        **kwargs,
    )


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例

    使用 LRU 缓存确保配置对象在整个应用生命周期内只加载一次。
    """
    return Settings()