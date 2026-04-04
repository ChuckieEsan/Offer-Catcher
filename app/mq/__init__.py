"""消息队列层

提供 RabbitMQ 生产者和消费者功能，用于实现主从 Agent 解耦。
支持两种消费模式：
1. AsyncRabbitMQConsumer: 基于协程的异步消费
2. ThreadPoolRabbitMQConsumer: 基于线程池的消费（每个线程独立 channel）
"""

from app.mq.producer import AsyncRabbitMQProducer, get_producer
from app.mq.consumer import AsyncRabbitMQConsumer, get_consumer
from app.mq.thread_pool_consumer import ThreadPoolRabbitMQConsumer, get_thread_pool_consumer


__all__ = [
    "AsyncRabbitMQProducer",
    "get_producer",
    "AsyncRabbitMQConsumer",
    "get_consumer",
    "ThreadPoolRabbitMQConsumer",
    "get_thread_pool_consumer",
]