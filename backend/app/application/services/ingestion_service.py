"""入库应用服务

编排面经入库用例，协调领域层和基础设施层。
作为应用层，负责：
- 调用仓库持久化聚合
- 分类熔断（判断是否需要异步答案）
- 发送 MQ 任务
- 复用答案机制（查重）
"""

from typing import Optional

from pydantic import BaseModel, Field

from app.domain.question.aggregates import Question, ExtractTask
from app.domain.question.repositories import (
    QuestionRepository,
    ExtractTaskRepository,
)
from app.domain.shared.enums import QuestionType
from app.models import ExtractedInterview, QuestionItem, MQTaskMessage

from app.infrastructure.persistence.qdrant.question_repository import (
    get_question_repository,
)
from app.infrastructure.persistence.postgres.extract_task_repository import (
    get_extract_task_repository,
)
from app.infrastructure.adapters.embedding_adapter import (
    EmbeddingAdapter,
    get_embedding_adapter,
)
from app.infrastructure.messaging import get_producer
from app.infrastructure.common.logger import logger


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


class IngestionApplicationService:
    """入库应用服务

    编排面经入库用例。通过依赖注入接收仓库实例，便于测试时使用 Mock。

    核心功能：
    1. ingest_interview - 从 ExtractedInterview 入库题目
    2. ingest_from_task - 从 ExtractTask 入库题目（用户确认后）

    设计要点：
    - 分类熔断：knowledge/scenario 类型触发 MQ 异步答案生成
    - 复用答案：高相似度题目复用已有答案
    """

    def __init__(
        self,
        question_repo: Optional[QuestionRepository] = None,
        extract_task_repo: Optional[ExtractTaskRepository] = None,
        embedding: Optional[EmbeddingAdapter] = None,
    ) -> None:
        """初始化应用服务

        Args:
            question_repo: Question 仓库（支持依赖注入）
            extract_task_repo: ExtractTask 仓库（支持依赖注入）
            embedding: Embedding 适配器（支持依赖注入）
        """
        self._question_repo = question_repo or get_question_repository()
        self._extract_task_repo = extract_task_repo or get_extract_task_repository()
        self._embedding = embedding or get_embedding_adapter()
        self._mq_producer = None

    async def _get_producer(self):
        """获取或创建异步 MQ 生产者"""
        if self._mq_producer is None:
            self._mq_producer = await get_producer()
        elif self._mq_producer._connection is None or self._mq_producer._connection.is_closed:
            await self._mq_producer.connect()
        return self._mq_producer

    async def ingest_interview(
        self,
        interview: ExtractedInterview,
        reuse_answer_threshold: float = 0.95,
    ) -> IngestionResult:
        """入库面试经验数据

        处理流程：
        1. 遍历题目，检查是否已存在
        2. 已存在且有答案 → 复用答案，跳过入库
        3. 新题目 → 计算向量，检查相似度
        4. 高相似度且有答案 → 复用答案
        5. 存入 Qdrant
        6. 分类熔断：knowledge/scenario 类型发送 MQ

        Args:
            interview: 面试经验数据
            reuse_answer_threshold: 复用答案的相似度阈值

        Returns:
            入库结果
        """
        result = IngestionResult()

        try:
            questions_to_save = []
            reuse_answer_map = {}  # question_id -> answer
            skip_async_question_ids = set()  # 不需要异步答案的题目 ID

            for question_item in interview.questions:
                # 1. 检查是否已存在
                existing = self._question_repo.find_by_id(question_item.question_id)

                if existing:
                    if existing.answer:
                        # 已有答案 → 标记不需要异步任务
                        logger.info(
                            f"Question {question_item.question_id} exists with answer, skip"
                        )
                        question_item.requires_async_answer = False
                        skip_async_question_ids.add(question_item.question_id)
                        # 注意：旧版本会入库带答案的 payload，新版本跳过入库
                        # 这里保持跳过，避免重复写入
                        result.question_ids.append(question_item.question_id)
                        continue
                    else:
                        # 已存在但无答案 → 跳过（MQ 中可能有待处理任务）
                        logger.info(
                            f"Question {question_item.question_id} exists without answer, skip"
                        )
                        skip_async_question_ids.add(question_item.question_id)
                        continue

                # 2. 新题目 - 检查相似度
                context = self._build_context(question_item)
                query_vector = self._embedding.embed(context)

                # 搜索相似题目（高阈值查重）
                similar_questions = self._question_repo.search(
                    query_vector=query_vector,
                    limit=1,
                    score_threshold=reuse_answer_threshold,
                )

                # 高相似度且有答案 → 复用答案
                if similar_questions and similar_questions[0].answer:
                    similar = similar_questions[0]
                    logger.info(
                        f"Reusing answer for {question_item.question_id} "
                        f"from similar question {similar.question_id}"
                    )
                    reuse_answer_map[question_item.question_id] = similar.answer
                    # 复用答案，不触发异步任务
                    skip_async_question_ids.add(question_item.question_id)

                # 创建 Question 聚合
                question = Question.create(
                    question_text=question_item.question_text,
                    company=question_item.company,
                    position=question_item.position,
                    question_type=QuestionType(question_item.question_type.value),
                    core_entities=question_item.core_entities,
                    metadata=question_item.metadata,
                )

                # 如果有复用的答案，设置到聚合
                if question_item.question_id in reuse_answer_map:
                    question.update_answer(reuse_answer_map[question_item.question_id])

                questions_to_save.append(question)

            if not questions_to_save:
                logger.info("No new questions to ingest")
                return result

            # 3. 批量存入 Qdrant
            for question in questions_to_save:
                self._question_repo.save(question)
                result.processed += 1
                result.question_ids.append(question.question_id)

            logger.info(f"Saved {result.processed} questions to Qdrant")

            # 4. 分类熔断 - 发送 MQ 任务
            async_count = await self._send_async_tasks(
                interview, skip_async_question_ids
            )
            result.async_tasks = async_count
            logger.info(f"Sent {async_count} async tasks to MQ")

            return result

        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            result.failed = result.processed
            result.processed = 0
            raise

    async def ingest_from_task(self, task_id: str) -> IngestionResult:
        """从 ExtractTask 入库题目

        用户确认后调用，从任务中获取提取结果并入库。

        Args:
            task_id: 提取任务 ID

        Returns:
            入库结果
        """
        # 1. 获取任务
        task = self._extract_task_repo.find_by_id(task_id)
        if not task:
            raise ValueError(f"ExtractTask not found: {task_id}")

        # 2. 检查任务状态
        if not task.is_ready_for_ingestion():
            raise ValueError(
                f"ExtractTask {task_id} is not ready for ingestion, "
                f"status={task.status}"
            )

        # 3. 解析提取结果
        if not task.extracted_interview:
            raise ValueError(f"ExtractTask {task_id} has no extracted_interview")

        interview = ExtractedInterview(**task.extracted_interview)

        # 4. 入库
        result = await self.ingest_interview(interview)

        # 5. 更新任务状态为 confirmed
        task.confirm()
        self._extract_task_repo.save(task)

        logger.info(f"Ingested from task {task_id}, result: {result}")
        return result

    async def _send_async_tasks(
        self,
        interview: ExtractedInterview,
        skip_async_question_ids: set[str],
    ) -> int:
        """发送异步答案生成任务到 MQ

        分类熔断机制：
        - knowledge / scenario / algorithm 类型：需要异步生成答案
        - project / behavioral 类型：熔断，不生成答案
        - 跳过的题目（已有答案或已存在）：不发送任务

        Args:
            interview: 面试经验数据
            skip_async_question_ids: 不需要异步任务的题目 ID 集合

        Returns:
            发送的任务数量
        """
        task_count = 0

        mq_producer = await self._get_producer()

        for question in interview.questions:
            # 检查是否被跳过
            if question.question_id in skip_async_question_ids:
                continue

            # 检查是否需要异步答案
            if question.question_type in (
                QuestionType.KNOWLEDGE,
                QuestionType.SCENARIO,
                QuestionType.ALGORITHM,
            ):
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
                    f"Async task sent: question_id={question.question_id}"
                )

        return task_count

    def _build_context(self, question: QuestionItem) -> str:
        """构建用于 embedding 的上下文

        格式："公司：xxx | 岗位：xxx | 类型：xxx | 考点：xxx | 题目：xxx"
        """
        entities = question.core_entities or []
        entities_str = ",".join(entities) if entities else "综合"
        return (
            f"公司：{question.company} | "
            f"岗位：{question.position} | "
            f"类型：{question.question_type.value} | "
            f"考点：{entities_str} | "
            f"题目：{question.question_text}"
        )


# 单例获取函数
_ingestion_service: Optional[IngestionApplicationService] = None


def get_ingestion_service() -> IngestionApplicationService:
    """获取入库应用服务单例"""
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = IngestionApplicationService()
    return _ingestion_service


__all__ = [
    "IngestionApplicationService",
    "IngestionResult",
    "get_ingestion_service",
]