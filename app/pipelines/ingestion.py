"""入库流水线模块

处理数据入库流程：
1. 将 ExtractedInterview 转换为嵌入向量
2. 使用 QdrantManager 直接存入 Qdrant（扁平结构）
3. 分类熔断 - knowledge/scenario 类型发送到 RabbitMQ 异步生成答案

直接使用 app/db 模块。
"""

import asyncio
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
        # 确保集合存在
        self.qdrant_manager.create_collection_if_not_exists()
        logger.info("IngestionPipeline initialized")

    async def _get_producer(self):
        """获取或创建异步生产者"""
        if not hasattr(self, '_mq_producer') or self._mq_producer is None:
            self._mq_producer = await get_producer()
        elif self._mq_producer._connection is None or self._mq_producer._connection.is_closed:
            await self._mq_producer.connect()
        return self._mq_producer

    def _create_context(self, question: QuestionItem) -> str:
        """创建用于 embedding 的上下文（静态前缀策略）

        格式："考点标签：xxx,yyy | 题目：xxx"
        """
        entities = question.core_entities or []
        entities_str = ",".join(entities) if entities else "综合"
        return f"考点标签：{entities_str} | 题目：{question.question_text}"

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

    async def _send_async_task(self, interview: ExtractedInterview) -> int:
        """发送异步任务到 RabbitMQ

        遵循分类熔断机制：
        - knowledge / scenario 类型：需要异步生成答案
        - project / behavioral 类型：熔断，不生成答案

        注意：不主动关闭连接，让 connect_robust 自动处理断线重连。
        """
        task_count = 0

        # 获取生产者（全局单例，连接保持长连接）
        mq_producer = await self._get_producer()

        for question in interview.questions:
            # KNOWLEDGE、SCENARIO 和 ALGORITHM 需要触发异步答案生成
            if question.question_type in (QuestionType.KNOWLEDGE, QuestionType.SCENARIO, QuestionType.ALGORITHM):
                task = MQTaskMessage(
                    question_id=question.question_id,
                    question_text=question.question_text,
                    company=question.company,
                    position=question.position,
                    core_entities=question.core_entities,
                )

                await mq_producer.publish_task(task)
                task_count += 1
                logger.info(
                    f"Async task sent: question_id={question.question_id}, "
                    f"company={question.company}"
                )

        return task_count

    async def process(self, interview: ExtractedInterview) -> IngestionResult:
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
                # 1.0 唯一键检查：使用 question_id 检查是否已存在
                existing_question = self.qdrant_manager.get_question(question.question_id)

                if existing_question:
                    # 题目已存在
                    if existing_question.question_answer:
                        # 已有答案 → 复用答案，跳过 MQ 任务
                        logger.info(
                            f"题目 {question.question_id} 已存在且有答案，复用已有答案"
                        )
                        question.requires_async_answer = False
                        payload = self._create_payload(question)
                        payload.question_answer = existing_question.question_answer
                    else:
                        # 无答案 → 跳过入库（MQ 中有待处理的任务）
                        logger.info(
                            f"题目 {question.question_id} 已存在但无答案，跳过入库（避免重复）"
                        )
                        continue
                else:
                    # 1.1 创建上下文用于 embedding
                    context = self._create_context(question)

                    # 1.2 写时复制：查重并复用答案（针对相似题目，非 exact match）
                    query_vector = self.embedding_tool.embed_text(context)
                    similar_docs = self.qdrant_manager.search(
                        query_vector=query_vector,
                        limit=1,
                        score_threshold=0.95,  # 高阈值查重
                    )

                    # 如果命中且已有答案，复用答案并关闭 MQ 任务
                    if similar_docs:
                        existing = similar_docs[0]
                        if existing.question_answer:
                            logger.info(
                                f"触发白嫖机制！题目【{question.question_text}】复用了库中已有标准答案。"
                            )
                            # 复制答案并关闭异步任务
                            # 注意：QuestionItem 没有 question_answer 字段，需要通过 payload 传递
                            question.requires_async_answer = False
                            # 在 payload 中设置答案
                            payload = self._create_payload(question)
                            payload.question_answer = existing.question_answer
                            logger.info(f"Question {question.question_id} will reuse existing answer")
                        else:
                            payload = self._create_payload(question)
                    else:
                        payload = self._create_payload(question)

                    # 1.3 生成向量
                    vector = self.embedding_tool.embed_text(context)

                    payloads.append(payload)
                    vectors.append(vector)

            if not payloads:
                logger.info("没有新题目需要入库")
                return result

            logger.info(f"Created {len(payloads)} payloads from interview")

            # 2. 存入 Qdrant（使用 QdrantManager 的 upsert_questions）
            self.qdrant_manager.upsert_questions(payloads, vectors)
            result.processed = len(payloads)
            result.question_ids = [p.question_id for p in payloads]

            logger.info(f"Stored {result.processed} questions to Qdrant")

            # 3. 分类熔断 - 发送异步任务（只在 requires_async_answer 为 True 时发送）
            async_count = await self._send_async_task(interview)
            result.async_tasks = async_count
            logger.info(f"Sent {async_count} async tasks to MQ")

            return result

        except Exception as e:
            logger.error(f"Ingestion pipeline failed: {e}")
            result.failed = result.processed
            result.processed = 0
            raise

    async def ingest_single_question(
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
            # knowledge、scenario 和 algorithm 的题目可以做异步处理
            requires_async_answer=(question_type in (QuestionType.KNOWLEDGE, QuestionType.SCENARIO, QuestionType.ALGORITHM)),
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

        return await self.process(interview)


# 全局单例
_ingestion_pipeline: Optional[IngestionPipeline] = None


def get_ingestion_pipeline() -> IngestionPipeline:
    """获取入库流水线单例"""
    global _ingestion_pipeline
    if _ingestion_pipeline is None:
        _ingestion_pipeline = IngestionPipeline()
    return _ingestion_pipeline