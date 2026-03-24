"""Answer Worker 入口脚本

启动 Worker 进程，消费 RabbitMQ 消息并生成答案。
"""

from app.agents.answer_specialist import get_answer_specialist
from app.db.qdrant_client import get_qdrant_manager
from app.mq.consumer import RabbitMQConsumer
from app.models.schemas import MQTaskMessage
from app.models.schemas import QuestionItem, QuestionType, MasteryLevel
from app.utils.logger import logger


def process_answer_task(task: MQTaskMessage) -> bool:
    """处理答案生成任务

    Args:
        task: MQ 消息

    Returns:
        是否成功
    """
    try:
        # 0. 幂等性检查：先判断答案是否已存在
        qdrant = get_qdrant_manager()
        existing = qdrant.get_question(task.question_id)
        if existing and existing.question_answer:
            logger.info(f"Answer already exists for: {task.question_id}, skipping")
            return True

        # 1. 创建 QuestionItem 对象
        question = QuestionItem(
            question_id=task.question_id,
            question_text=task.question_text,
            question_type=QuestionType.KNOWLEDGE,
            requires_async_answer=True,
            core_entities=task.core_entities,
            mastery_level=MasteryLevel.LEVEL_0,
            company=task.company,
            position=task.position,
        )

        # 2. 生成答案
        agent = get_answer_specialist(provider="dashscope")
        answer = agent.generate_answer(question)

        # 3. 写入 Qdrant
        qdrant.update_answer(task.question_id, answer)

        logger.info(f"Answer generated and saved for: {task.question_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to process task {task.question_id}: {e}")
        return False


def main():
    """主函数"""
    logger.info("Starting Answer Worker...")

    with RabbitMQConsumer(prefetch_count=1) as consumer:
        logger.info("Worker started, waiting for messages...")
        consumer.consume(process_answer_task)


if __name__ == "__main__":
    main()