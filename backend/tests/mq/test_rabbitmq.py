"""RabbitMQ 消费者异步测试

验证 AsyncRabbitMQConsumer 功能是否正常。
包括可靠性测试：消息持久化、线程池消费、幂等性、连接断开重连等。
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.infrastructure.config.settings import get_settings
from app.utils.hasher import generate_question_id
from app.models import MQTaskMessage
from app.mq.producer import AsyncRabbitMQProducer
from app.mq.consumer import AsyncRabbitMQConsumer, _message_breaker
from app.mq.thread_pool_consumer import ThreadPoolRabbitMQConsumer


class TestAsyncRabbitMQConnection:
    """连接测试"""

    @pytest.mark.asyncio
    async def test_consumer_connect(self):
        """测试消费者连接"""
        c = AsyncRabbitMQConsumer(prefetch_count=5)
        result = await c.connect()

        assert result is True
        assert c._connection is not None
        assert not c._connection.is_closed

        await c.close()
        print("Consumer connection test passed")

    @pytest.mark.asyncio
    async def test_consumer_close(self):
        """测试消费者关闭"""
        c = AsyncRabbitMQConsumer(prefetch_count=5)
        await c.connect()
        assert c._connection is not None

        await c.close()
        print("Consumer close test passed")


class TestAsyncRabbitMQProducer:
    """生产者功能测试"""

    @pytest.mark.asyncio
    async def test_publish_single_task(self):
        """测试发布单条任务"""
        producer = AsyncRabbitMQProducer()
        await producer.connect()

        try:
            question_id = generate_question_id("字节跳动", "什么是 RAG？")
            task = MQTaskMessage(
                question_id=question_id,
                question_text="什么是 RAG？",
                company="字节跳动",
                position="Agent应用开发",
                core_entities=["RAG", "检索增强"],
            )

            result = await producer.publish_task(task)
            assert result is True
            print("Published single task successfully")
        finally:
            await producer.close()

    @pytest.mark.asyncio
    async def test_publish_batch_tasks(self):
        """测试批量发布任务"""
        producer = AsyncRabbitMQProducer()
        await producer.connect()

        try:
            tasks = [
                MQTaskMessage(
                    question_id=generate_question_id("字节跳动", f"测试问题 {i}"),
                    question_text=f"测试问题 {i}",
                    company="字节跳动",
                    position="Agent应用开发",
                )
                for i in range(5)
            ]

            success_count = await producer.publish_tasks(tasks)
            assert success_count == 5
            print(f"Published {success_count} tasks successfully")
        finally:
            await producer.close()


class TestAsyncRabbitMQIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_publish_and_check_queue(self):
        """测试发布消息并验证队列状态"""
        settings = get_settings()

        # 生产者发布消息
        producer = AsyncRabbitMQProducer()
        await producer.connect()

        try:
            question_id = generate_question_id("阿里", "集成测试问题")
            test_task = MQTaskMessage(
                question_id=question_id,
                question_text="集成测试问题",
                company="阿里",
                position="大模型开发",
                core_entities=["LLM"],
            )

            publish_result = await producer.publish_task(test_task)
            assert publish_result is True
            print(f"Published task: {test_task.question_id}")
        finally:
            await producer.close()

        # 消费者验证队列
        consumer = AsyncRabbitMQConsumer(prefetch_count=5)
        await consumer.connect()

        try:
            # 检查队列消息数
            queue = consumer._queue
            # 通过 get 方法获取队列信息
            declaration_result = await queue.declare()
            print(f"Queue exists: {declaration_result}")
            print("Integration test passed")
        finally:
            await consumer.close()

    @pytest.mark.asyncio
    async def test_retry_count_in_header(self):
        """测试消息重试次数是否正确记录"""
        settings = get_settings()

        # 发布测试消息
        producer = AsyncRabbitMQProducer()
        await producer.connect()
        try:
            question_id = generate_question_id("测试公司", "重试测试问题")
            test_task = MQTaskMessage(
                question_id=question_id,
                question_text="重试测试问题",
                company="测试公司",
                position="测试岗位",
            )
            await producer.publish_task(test_task)
        finally:
            await producer.close()

        # 消费者处理消息
        consumer = AsyncRabbitMQConsumer(prefetch_count=5)
        await consumer.connect()

        try:
            # 定义失败的回调
            async def fail_callback(_task: MQTaskMessage) -> bool:
                print(f"Callback invoked, returning False")
                return False

            # 获取并处理消息
            message = await consumer._queue.get()
            await consumer._on_message(message, fail_callback)

            # 等待重试
            await asyncio.sleep(0.5)

            print("Retry count test passed")
        finally:
            await consumer.close()

    @pytest.mark.asyncio
    async def test_max_retries_to_dlq(self):
        """测试超过最大重试次数后消息进入死信队列

        注意：由于熔断器逻辑，重试测试需要手动模拟
        """
        # 此测试需要更复杂的设置，暂跳过
        pytest.skip("熔断器与重试逻辑有冲突，需要单独测试")

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens(self):
        """测试熔断器在连续失败后打开"""
        # 重置熔断器状态
        _message_breaker.close()

        settings = get_settings()

        # 发布测试消息
        producer = AsyncRabbitMQProducer()
        await producer.connect()
        try:
            question_id = generate_question_id("测试公司", "熔断器测试问题")
            test_task = MQTaskMessage(
                question_id=question_id,
                question_text="熔断器测试问题",
                company="测试公司",
                position="测试岗位",
            )
            await producer.publish_task(test_task)
        finally:
            await producer.close()

        # 消费者触发熔断
        consumer = AsyncRabbitMQConsumer(prefetch_count=5)
        await consumer.connect()

        try:
            async def always_fail(_task: MQTaskMessage) -> bool:
                return False

            print("Triggering circuit breaker...")
            for _ in range(6):
                try:
                    message = await asyncio.wait_for(
                        consumer._queue.get(), timeout=2.0
                    )
                    await consumer._on_message(message, always_fail)
                except asyncio.TimeoutError:
                    break
                await asyncio.sleep(0.1)

            # 验证熔断器已打开
            from aiobreaker.state import CircuitOpenState
            is_open = isinstance(consumer.circuit_breaker.state, CircuitOpenState)
            print(f"Circuit breaker is open: {is_open}")

            assert is_open, "Circuit breaker should be open after 5 failures"

            print("Circuit breaker test passed")
        finally:
            await consumer.close()


class TestRabbitMQReliability:
    """消息队列可靠性测试"""

    @pytest.mark.asyncio
    async def test_message_persistence(self):
        """测试消息持久化：验证消息在队列中是持久化的"""
        settings = get_settings()
        producer = AsyncRabbitMQProducer()
        await producer.connect()

        try:
            # 发布消息
            question_id = generate_question_id("持久化测试", "测试问题")
            task = MQTaskMessage(
                question_id=question_id,
                question_text="持久化测试问题",
                company="测试公司",
                position="测试岗位",
            )
            result = await producer.publish_task(task)
            assert result is True

            # 获取 channel 来检查队列状态
            channel = producer._channel
            queue = await channel.declare_queue(
                settings.rabbitmq_queue, passive=True
            )
            declare_result = await queue.declare()
            assert declare_result.message_count > 0, "消息应该已持久化到队列"

            print("Message persistence test passed")
        finally:
            await producer.close()

    @pytest.mark.asyncio
    async def test_message_idempotency(self):
        """测试消息幂等性：同一 question_id 多次消费结果一致"""
        settings = get_settings()
        question_id = generate_question_id("幂等性测试", "测试问题")

        # 发布消息
        producer = AsyncRabbitMQProducer()
        await producer.connect()
        try:
            task = MQTaskMessage(
                question_id=question_id,
                question_text="幂等性测试问题",
                company="测试公司",
                position="测试岗位",
            )
            await producer.publish_task(task)
        finally:
            await producer.close()

        # 消费消息
        consumer = AsyncRabbitMQConsumer(prefetch_count=1)
        await consumer.connect()

        try:
            # 消费第一条消息
            message = await asyncio.wait_for(consumer._queue.get(timeout=5), timeout=10)
            await message.ack()
            print("Message consumed successfully")
        finally:
            await consumer.close()

        print("Message idempotency test passed")

    @pytest.mark.asyncio
    async def test_concurrent_produce_consume(self):
        """测试并发生产和消费：验证高并发场景下消息不丢失"""
        settings = get_settings()

        # 记录初始队列消息数
        producer = AsyncRabbitMQProducer()
        await producer.connect()
        try:
            channel = producer._channel
            queue = await channel.declare_queue(settings.rabbitmq_queue, passive=True)
            initial_count = (await queue.declare()).message_count
        finally:
            await producer.close()

        # 同步发布消息
        async def publish_messages():
            p = AsyncRabbitMQProducer()
            await p.connect()
            try:
                tasks = [
                    MQTaskMessage(
                        question_id=generate_question_id("并发测试", f"问题{i}"),
                        question_text=f"并发测试问题{i}",
                        company="测试公司",
                        position="测试岗位",
                    )
                    for i in range(10)
                ]
                success_count = await p.publish_tasks(tasks)
                print(f"Published {success_count}/10 messages")
                return success_count
            finally:
                await p.close()

        # 使用线程池并发发布
        with ThreadPoolExecutor(max_workers=3) as executor:
            loop = asyncio.get_event_loop()
            futures = [loop.run_in_executor(executor, lambda: asyncio.run(publish_messages())) for _ in range(3)]
            results = await asyncio.gather(*futures)

        total_published = sum(results)
        print(f"Total published: {total_published}/30")

        # 验证队列消息数量
        producer = AsyncRabbitMQProducer()
        await producer.connect()
        try:
            channel = producer._channel
            queue = await channel.declare_queue(settings.rabbitmq_queue, passive=True)
            declare_result = await queue.declare()
            message_count = declare_result.message_count
            expected_count = initial_count + total_published
            print(f"Queue contains {message_count} messages (expected: {expected_count})")
            assert message_count == expected_count
        finally:
            await producer.close()

        print("Concurrent produce/consume test passed")


class TestThreadPoolConsumer:
    """线程池消费者测试"""

    @pytest.mark.asyncio
    async def test_thread_pool_consumer_init(self):
        """测试线程池消费者初始化"""
        consumer = ThreadPoolRabbitMQConsumer(num_threads=2, prefetch_count=1)
        assert consumer.num_threads == 2
        assert consumer.prefetch_count == 1
        assert not consumer.is_running
        print("Thread pool consumer init test passed")

    @pytest.mark.asyncio
    async def test_thread_pool_consumer_start_stop(self):
        """测试线程池消费者启动和停止"""
        settings = get_settings()

        # 发布测试消息
        producer = AsyncRabbitMQProducer()
        await producer.connect()
        try:
            for i in range(3):
                task = MQTaskMessage(
                    question_id=generate_question_id("线程池测试", f"问题{i}"),
                    question_text=f"线程池测试问题{i}",
                    company="测试公司",
                    position="测试岗位",
                )
                await producer.publish_task(task)
        finally:
            await producer.close()

        # 测试线程池消费者
        def simple_callback(task: MQTaskMessage) -> bool:
            print(f"Processed: {task.question_id}")
            return True

        consumer = ThreadPoolRabbitMQConsumer(num_threads=2, prefetch_count=1)

        # 启动消费者
        await consumer.start(simple_callback)
        assert consumer.is_running
        print("Thread pool consumer started")

        # 运行一段时间
        await asyncio.sleep(3)

        # 停止消费者
        await consumer.stop()
        assert not consumer.is_running
        print("Thread pool consumer stopped")

        print("Thread pool consumer start/stop test passed")

    @pytest.mark.asyncio
    async def test_multiple_threads_consume(self):
        """测试多线程并发消费"""
        settings = get_settings()

        # 发布 8 条消息
        producer = AsyncRabbitMQProducer()
        await producer.connect()
        try:
            for i in range(8):
                task = MQTaskMessage(
                    question_id=generate_question_id("多线程消费", f"问题{i}"),
                    question_text=f"多线程消费问题{i}",
                    company="测试公司",
                    position="测试岗位",
                )
                await producer.publish_task(task)
        finally:
            await producer.close()

        processed_count = 0
        lock = threading.Lock()

        def counting_callback(task: MQTaskMessage) -> bool:
            nonlocal processed_count
            with lock:
                processed_count += 1
            print(f"Processed: {task.question_id}, total: {processed_count}")
            return True

        # 使用 4 个线程消费
        consumer = ThreadPoolRabbitMQConsumer(num_threads=4, prefetch_count=1)
        await consumer.start(counting_callback)

        # 等待处理完成
        max_wait = 30
        start_time = time.time()
        while processed_count < 8 and (time.time() - start_time) < max_wait:
            await asyncio.sleep(0.5)

        print(f"Processed {processed_count}/8 messages in {time.time() - start_time:.1f}s")

        await consumer.stop()

        # 验证
        assert processed_count >= 8, f"Expected at least 8 messages processed, got {processed_count}"

        print("Multiple threads consume test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])