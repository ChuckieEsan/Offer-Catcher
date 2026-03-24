"""RabbitMQ 客户端功能测试

验证 RabbitMQ 生产者和消费者功能是否正常工作。
"""

import time
from typing import List

import pytest

from app.config.settings import get_settings
from app.utils.hasher import generate_question_id
from app.models.schemas import MQTaskMessage
from app.mq.producer import RabbitMQProducer
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
        question_id = generate_question_id("字节跳动", "什么是 RAG？")
        task = MQTaskMessage(
            question_id=question_id,
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
                question_id=generate_question_id("字节跳动", f"测试问题 {i}"),
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

        question_id = generate_question_id("腾讯", "消费测试问题")
        test_task = MQTaskMessage(
            question_id=question_id,
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

        question_id = generate_question_id("阿里", "集成测试问题")
        test_task = MQTaskMessage(
            question_id=question_id,
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

            question_id = generate_question_id("美团", "上下文管理器测试")
            task = MQTaskMessage(
                question_id=question_id,
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
                question_id=generate_question_id(
                    "字节跳动" if i % 2 == 0 else "腾讯",
                    f"工作流测试问题 {i}"
                ),
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


class TestCircuitBreakerAndDLQ:
    """熔断器和死信队列测试"""

    def setup_method(self):
        """测试前置设置"""
        self.producer = RabbitMQProducer()
        self.producer.connect()
        self.consumer = RabbitMQConsumer()
        self.consumer.connect()
        self.settings = get_settings()

    def teardown_method(self):
        """测试后清理"""
        self.producer.close()
        self.consumer.close()

    def test_retry_count_in_header(self):
        """测试消息重试次数是否正确记录在消息头中"""
        print("\n=== Testing retry count in message header ===")

        question_id = generate_question_id("测试公司", "重试测试问题")
        print(f"   Generated question_id: {question_id}")

        # 1. 发布测试消息
        test_task = MQTaskMessage(
            question_id=question_id,
            question_text="重试测试问题",
            company="测试公司",
            position="测试岗位",
        )
        self.producer.publish_task(test_task)

        # 2. 定义一个始终返回失败的回调
        def fail_callback(_task: MQTaskMessage) -> bool:
            print(f"   Callback invoked, returning False")
            return False  # 始终返回失败

        # 3. 消费消息（会失败并重试）
        method, properties, body = self.consumer._channel.basic_get(
            queue=self.settings.rabbitmq_queue
        )

        if method:
            # 模拟处理失败
            self.consumer._on_message(
                self.consumer._channel,
                method,
                properties,
                body,
                fail_callback
            )

            # 4. 验证消息被重新发布（检查队尾是否有消息）
            time.sleep(0.5)
            queue = self.consumer._channel.queue_declare(
                queue=self.settings.rabbitmq_queue, passive=True
            )
            print(f"   Queue contains {queue.method.message_count} messages after first failure")

            # 获取队尾的消息，检查 retry-count
            method2, properties2, _body2 = self.consumer._channel.basic_get(
                queue=self.settings.rabbitmq_queue
            )

            if properties2 and properties2.headers:
                retry_count = properties2.headers.get("x-retry-count", 0)
                print(f"   Retry count in header: {retry_count}")
                # 第一次失败后重试，retry-count 应该是 1
                assert retry_count == 1, f"Expected retry_count=1, got {retry_count}"

            # 清理
            if method2:
                self.consumer._channel.basic_ack(method2.delivery_tag)

            print("   Retry count test passed")

    def test_max_retries_to_dlq(self):
        """测试超过最大重试次数后消息进入死信队列"""
        print("\n=== Testing max retries to DLQ ===")

        # 使用符合 UUID 格式的 question_id
        from app.utils.hasher import generate_question_id

        question_id = generate_question_id("测试公司", "死信队列测试问题")
        print(f"   Generated question_id: {question_id}")

        # 确保重试次数配置正确
        max_retries = self.settings.rabbitmq_max_retries
        print(f"   Max retries: {max_retries}")

        # 1. 清空队列和死信队列
        self.consumer._channel.queue_purge(queue=self.settings.rabbitmq_queue)
        self.consumer._channel.queue_purge(queue=self.settings.rabbitmq_dlq)

        # 2. 发布测试消息
        test_task = MQTaskMessage(
            question_id=question_id,
            question_text="死信队列测试问题",
            company="测试公司",
            position="测试岗位",
        )
        self.producer.publish_task(test_task)

        # 3. 定义始终失败的回调
        def always_fail(_task: MQTaskMessage) -> bool:
            return False

        # 4. 消费消息直到进入死信队列
        print("   Consuming messages until max retries reached...")
        for i in range(max_retries + 1):
            method, properties, body = self.consumer._channel.basic_get(
                queue=self.settings.rabbitmq_queue
            )
            if method:
                self.consumer._on_message(
                    self.consumer._channel,
                    method,
                    properties,
                    body,
                    always_fail
                )
                time.sleep(0.2)
                print(f"   Attempt {i+1}/{max_retries+1} done")

        time.sleep(1)

        # 5. 验证主队列已清空
        main_queue = self.consumer._channel.queue_declare(
            queue=self.settings.rabbitmq_queue, passive=True
        )
        print(f"   Main queue messages: {main_queue.method.message_count}")

        # 6. 验证死信队列有消息
        dlq = self.consumer._channel.queue_declare(
            queue=self.settings.rabbitmq_dlq, passive=True
        )
        print(f"   DLQ messages: {dlq.method.message_count}")

        assert main_queue.method.message_count == 0, "Main queue should be empty"
        assert dlq.method.message_count == 1, "DLQ should have 1 message"

        print("   Max retries to DLQ test passed")

    def test_circuit_breaker_opens(self):
        """测试熔断器在连续失败后打开"""
        print("\n=== Testing circuit breaker ===")

        # 使用符合 UUID 格式的 question_id
        from app.utils.hasher import generate_question_id

        question_id = generate_question_id("测试公司", "熔断器测试问题")
        print(f"   Generated question_id: {question_id}")

        # 确保队列中有消息供消费
        test_task = MQTaskMessage(
            question_id=question_id,
            question_text="熔断器测试问题",
            company="测试公司",
            position="测试岗位",
        )
        self.producer.publish_task(test_task)

        # 连续触发失败直到熔断器打开
        def always_fail(_task: MQTaskMessage) -> bool:
            return False

        print("   Triggering circuit breaker...")
        for _i in range(6):  # 熔断阈值是 5
            method, properties, body = self.consumer._channel.basic_get(
                queue=self.settings.rabbitmq_queue
            )
            if method:
                self.consumer._on_message(
                    self.consumer._channel,
                    method,
                    properties,
                    body,
                    always_fail
                )
                time.sleep(0.1)

        # 验证熔断器已打开
        from aiobreaker.state import CircuitOpenState
        is_open = isinstance(self.consumer.circuit_breaker.state, CircuitOpenState)
        print(f"   Circuit breaker is open: {is_open}")

        assert is_open, "Circuit breaker should be open after 5 failures"

        # 清理
        self.consumer._channel.queue_purge(queue=self.settings.rabbitmq_queue)

        print("   Circuit breaker test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])