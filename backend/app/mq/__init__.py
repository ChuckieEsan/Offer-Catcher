"""消息队列层

底层服务由 infrastructure/messaging 提供。
"""

from app.infrastructure.messaging.producer import (
    RabbitMQProducer,
    get_producer,
    AsyncRabbitMQProducer,
)
from app.infrastructure.messaging.consumer import (
    RabbitMQConsumer,
    get_consumer,
    AsyncRabbitMQConsumer,
)
from app.infrastructure.messaging.thread_pool_consumer import (
    ThreadPoolRabbitMQConsumer,
    get_thread_pool_consumer,
)

# 向后兼容的别名
AsyncRabbitMQProducer = RabbitMQProducer
AsyncRabbitMQConsumer = RabbitMQConsumer

__all__ = [
    "AsyncRabbitMQProducer",
    "get_producer",
    "AsyncRabbitMQConsumer",
    "get_consumer",
    "ThreadPoolRabbitMQConsumer",
    "get_thread_pool_consumer",
]