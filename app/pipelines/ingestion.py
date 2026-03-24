"""入库流水线模块

处理数据入库流程：
1. 将 ExtractedInterview 转换为嵌入向量
2. 使用 QdrantManager 直接存入 Qdrant（扁平结构）
3. 分类熔断 - knowledge/scenario 类型发送到 RabbitMQ 异步生成答案

直接使用 app/db 模块。
"""

from pydantic import BaseModel, Field
from typing import Optional

from app.models.schemas import ExtractedInterview, QuestionType, MQTaskMessage, QdrantQuestionPayload
from app.tools.embedding import get_embedding_tool
from app.db.qdrant_client import get_qdrant_manager
from app.mq.producer import get_producer
from app.utils.logger import logger
from app.utils.hasher import generate_question_id
from app.models.schemas import QuestionItem


class IngestionResult(BaseModel):
    """入库结果

    Attributes:
        processed: 处理成功的题目数量
        failed: 处理失败的数量
        async_tasks: 触发的异步任务数量
        question_ids: 入库成功的 question_id 列表
    """

    processed: int = Field(default=0, description="处理成功的题目数量")
    failed: int = Field(default=0, description="处理失败的数量")
    async_tasks: int = Field(default=0, description="触发的异步任务数量")
    question_ids: list[str] = Field(default_factory=list, description="入库成功的 question_id 列表")


class IngestionPipeline:
    """入库流水线

    负责将面试经验数据入库到向量数据库，并触发异步答案生成任务。

    处理流程：
    1. 遍历每道题目，转换为扁平 Payload 格式
    2. 使用 QdrantManager 直接存入 Qdrant（扁平结构）
    3. 分类熔断：knowledge/scenario 类型发送异步任务
    """

    def __init__(self) -> None:
        """初始化入库流水线"""
        self.embedding_tool = get_embedding_tool()
        self.qdrant_manager = get_qdrant_manager()
        self.mq_producer = get_producer()
        logger.info("IngestionPipeline initialized")

    def _create_context(self, question: QuestionItem) -> str:
        """创建用于 embedding 的上下文

        遵循 CLAUDE.md 中的 Context Enrichment 原则：
        存储时拼接上下文："公司：xxx | 岗位：xxx | 题目：xxx"
        """
        return (
            f"公司：{question.company} | "
            f"岗位：{question.position} | "
            f"题目：{question.question_text}"
        )

    def _create_payload(self, question: QuestionItem) -> QdrantQuestionPayload:
        """创建 Qdrant Payload"""
        return QdrantQuestionPayload(
            question_id=question.question_id,
            question_text=question.question_text,
            company=question.company,
            position=question.position,
            mastery_level=question.mastery_level.value,
            question_type=question.question_type.value,
            core_entities=question.core_entities,
            metadata=question.metadata,
        )

    def _send_async_task(self, interview: ExtractedInterview) -> int:
        """发送异步任务到 RabbitMQ

        遵循分类熔断机制：
        - knowledge / scenario 类型：需要异步生成答案
        - project / behavioral 类型：熔断，不生成答案
        """
        task_count = 0

        # 确保生产者已连接
        if self.mq_producer._connection is None or self.mq_producer._connection.is_closed:
            self.mq_producer.connect()

        for question in interview.questions:
            # KNOWLEDGE 和 SCENARIO 需要触发异步答案生成
            if question.question_type in (QuestionType.KNOWLEDGE, QuestionType.SCENARIO):
                task = MQTaskMessage(
                    question_id=question.question_id,
                    question_text=question.question_text,
                    company=question.company,
                    position=question.position,
                    core_entities=question.core_entities,
                )

                self.mq_producer.publish_task(task)
                task_count += 1
                logger.info(
                    f"Async task sent: question_id={question.question_id}, "
                    f"company={question.company}"
                )

        return task_count

    def process(self, interview: ExtractedInterview) -> IngestionResult:
        """处理入库流水线

        Args:
            interview: 面试经验数据

        Returns:
            入库结果
        """
        result = IngestionResult()

        try:
            # 1. 为每道题生成向量和 Payload
            payloads = []
            vectors = []

            for question in interview.questions:
                # 创建上下文用于 embedding
                context = self._create_context(question)
                # 生成向量
                vector = self.embedding_tool.embeddings.embed_query(context)
                # 创建 Payload
                payload = self._create_payload(question)

                payloads.append(payload)
                vectors.append(vector)

            logger.info(f"Created {len(payloads)} payloads from interview")

            # 2. 存入 Qdrant（使用 QdrantManager 的 upsert_questions）
            self.qdrant_manager.upsert_questions(payloads, vectors)
            result.processed = len(payloads)
            result.question_ids = [p.question_id for p in payloads]

            logger.info(f"Stored {result.processed} questions to Qdrant")

            # 3. 分类熔断 - 发送异步任务
            async_count = self._send_async_task(interview)
            result.async_tasks = async_count
            logger.info(f"Sent {async_count} async tasks to MQ")

            return result

        except Exception as e:
            logger.error(f"Ingestion pipeline failed: {e}")
            result.failed = result.processed
            result.processed = 0
            raise

    def ingest_single_question(
        self,
        question_text: str,
        company: str,
        position: str,
        question_type: QuestionType = QuestionType.KNOWLEDGE,
        mastery_level: int = 0,
        core_entities: Optional[list[str]] = None,
    ) -> IngestionResult:
        """简化接口：入库单条题目

        适用于直接调用场景。
        """
        question_id = generate_question_id(company, question_text)

        # 创建 QuestionItem
        question = QuestionItem(
            question_id=question_id,
            question_text=question_text,
            question_type=question_type,
            # knowledge 和 scenario 的题目可以做异步处理
            requires_async_answer=(question_type in (QuestionType.KNOWLEDGE, QuestionType.SCENARIO)),
            core_entities=core_entities or [],
            mastery_level=mastery_level,
            company=company,
            position=position,
        )

        # 创建 ExtractedInterview
        interview = ExtractedInterview(
            company=company,
            position=position,
            questions=[question],
        )

        return self.process(interview)


# 全局单例
_ingestion_pipeline: Optional[IngestionPipeline] = None


def get_ingestion_pipeline() -> IngestionPipeline:
    """获取入库流水线单例"""
    global _ingestion_pipeline
    if _ingestion_pipeline is None:
        _ingestion_pipeline = IngestionPipeline()
    return _ingestion_pipeline