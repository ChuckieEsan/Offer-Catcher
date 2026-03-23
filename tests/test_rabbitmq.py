"""RabbitMQ 客户端功能测试

验证 RabbitMQ 生产者和消费者功能是否正常工作。
"""

import threading
import time
from typing import List, Optional

import pytest

from app.config.settings import get_settings
from app.models.schemas import MQTaskMessage
from app.mq.producer import RabbitMQProducer, get_producer
from app.mq.consumer import RabbitMQConsumer


class TestRabbitMQConnection:
    """RabbitMQ 连接测试"""

    def test_producer_connection(self):
        """测试生产者连接"""
        producer = RabbitMQProducer()
        connected = producer.connect()
        assert connected is True

        # 验证连接状态
        assert producer._connection is not None
        assert not producer._connection.is_closed

        producer.close()
        print("Producer connection test passed")

    def test_consumer_connection(self):
        """测试消费者连接"""
        consumer = RabbitMQConsumer()
        connected = consumer.connect()
        assert connected is True

        # 验证连接状态
        assert consumer._connection is not None
        assert not consumer._connection.is_closed

        consumer.close()
        print("Consumer connection test passed")


class TestRabbitMQProducer:
    """生产者功能测试"""

    def setup_method(self):
        """测试前置设置"""
        self.producer = RabbitMQProducer()
        self.producer.connect()
        self.settings = get_settings()

    def teardown_method(self):
        """测试后清理"""
        self.producer.close()

    def test_publish_single_task(self):
        """测试发布单条任务"""
        task = MQTaskMessage(
            question_id="test_001",
            question_text="什么是 RAG？",
            company="字节跳动",
            position="Agent应用开发",
            core_entities=["RAG", "检索增强"],
        )

        result = self.producer.publish_task(task)
        assert result is True
        print("Published single task successfully")

    def test_publish_batch_tasks(self):
        """测试批量发布任务"""
        tasks = [
            MQTaskMessage(
                question_id=f"test_{i:03d}",
                question_text=f"测试问题 {i}",
                company="字节跳动",
                position="Agent应用开发",
            )
            for i in range(5)
        ]

        success_count = self.producer.publish_tasks(tasks)
        assert success_count == 5
        print(f"Published {success_count} tasks successfully")


class TestRabbitMQConsumer:
    """消费者功能测试"""

    def setup_method(self):
        """测试前置设置"""
        self.consumer = RabbitMQConsumer()
        self.consumer.connect()
        self.settings = get_settings()
        self.received_messages: List[MQTaskMessage] = []

    def teardown_method(self):
        """测试后清理"""
        self.consumer.close()

    def test_consume_message(self):
        """测试消费消息"""
        # 先发布一条消息
        producer = RabbitMQProducer()
        producer.connect()

        test_task = MQTaskMessage(
            question_id="consume_test_001",
            question_text="消费测试问题",
            company="腾讯",
            position="后端开发",
        )
        producer.publish_task(test_task)
        producer.close()

        # 等待消息被消费
        time.sleep(1)

        # 验证队列状态
        queue = self.consumer._channel.queue_declare(
            queue=self.settings.rabbitmq_queue, passive=True
        )
        print(f"Queue message count: {queue.method.message_count}")


class TestRabbitMQIntegration:
    """生产者和消费者集成测试"""

    def test_producer_consumer_integration(self):
        """测试生产者和消费者集成"""
        # 1. 发布测试消息
        producer = RabbitMQProducer()
        producer.connect()

        test_task = MQTaskMessage(
            question_id="integration_test_001",
            question_text="集成测试问题",
            company="阿里",
            position="大模型开发",
            core_entities=["LLM"],
        )

        publish_result = producer.publish_task(test_task)
        assert publish_result is True
        print(f"Published task: {test_task.question_id}")
        producer.close()

        # 2. 验证消息已在队列中
        consumer = RabbitMQConsumer()
        consumer.connect()
        queue = consumer._channel.queue_declare(
            queue=get_settings().rabbitmq_queue, passive=True
        )
        print(f"Queue contains {queue.method.message_count} messages")
        assert queue.method.message_count > 0
        consumer.close()

        print("Integration test passed - message published successfully")


class TestRabbitMQContextManager:
    """上下文管理器测试"""

    def test_producer_context_manager(self):
        """测试生产者上下文管理器"""
        with RabbitMQProducer() as producer:
            assert producer._connection is not None
            assert not producer._connection.is_closed

            task = MQTaskMessage(
                question_id="ctx_test_001",
                question_text="上下文管理器测试",
                company="美团",
                position="算法工程师",
            )
            result = producer.publish_task(task)
            assert result is True

        # 退出后应该自动关闭
        print("Producer context manager test passed")

    def test_consumer_context_manager(self):
        """测试消费者上下文管理器"""
        with RabbitMQConsumer() as consumer:
            assert consumer._connection is not None
            assert not consumer._connection.is_closed

        print("Consumer context manager test passed")


class TestRabbitMQFullWorkflow:
    """完整流程测试"""

    def test_full_workflow(self):
        """测试完整的消息队列流程"""
        print("\n=== Starting RabbitMQ full workflow test ===")

        # 1. 测试连接
        print("1. Testing producer connection...")
        producer = RabbitMQProducer()
        producer.connect()
        assert producer._connection is not None
        print("   Producer connected")

        print("2. Testing consumer connection...")
        consumer = RabbitMQConsumer()
        consumer.connect()
        assert consumer._connection is not None
        print("   Consumer connected")

        # 2. 发布多条消息
        print("3. Publishing test messages...")
        test_tasks = [
            MQTaskMessage(
                question_id=f"workflow_{i}",
                question_text=f"工作流测试问题 {i}",
                company="字节跳动" if i % 2 == 0 else "腾讯",
                position="Agent开发" if i % 2 == 0 else "后端开发",
            )
            for i in range(3)
        ]

        for task in test_tasks:
            producer.publish_task(task)
            print(f"   Published: {task.question_id}")

        # 3. 验证队列状态
        queue = producer._channel.queue_declare(
            queue=get_settings().rabbitmq_queue, passive=True
        )
        print(f"4. Queue contains {queue.method.message_count} messages")

        # 4. 清理
        producer.close()
        consumer.close()

        print("=== Full workflow test passed ===\n")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])