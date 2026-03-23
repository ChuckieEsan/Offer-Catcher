"""消息队列层

提供 RabbitMQ 生产者和消费者功能，用于实现主从 Agent 解耦。
"""

from app.mq.producer import RabbitMQProducer, get_producer
from app.mq.consumer import RabbitMQConsumer, get_consumer

__all__ = [
    "RabbitMQProducer",
    "get_producer",
    "RabbitMQConsumer",
    "get_consumer",
]