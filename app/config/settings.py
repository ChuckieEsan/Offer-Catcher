"""全局配置管理模块

使用 Pydantic Settings 读取环境变量。
支持从 .env 文件加载配置。
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置类

    所有配置项均可通过环境变量覆盖。
    支持 .env 文件自动加载。

    Environment Variables:
        OPENAI_API_KEY: OpenAI API Key（必填）
        OPENAI_BASE_URL: OpenAI API Base URL（可选，默认官方地址）
        OPENAI_MODEL: 使用的模型名称（可选，默认 gpt-4o）
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
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # OpenAI 配置
    openai_api_key: str = Field(
        description="OpenAI API Key",
        default="",
    )
    openai_base_url: str = Field(
        description="OpenAI API Base URL",
        default="https://api.deepseek.com",
    )
    openai_model: str = Field(
        description="使用的模型名称",
        default="deepseek-chat",
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
        description="向量维度（text-embedding-3-small 为 1536）",
        default=1536,
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

    def validate_required(self) -> bool:
        """验证必填配置项"""
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required")
        return True


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例

    使用 LRU 缓存确保配置对象在整个应用生命周期内只加载一次。
    """
    return Settings()