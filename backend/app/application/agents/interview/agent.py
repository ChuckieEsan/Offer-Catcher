"""Interview Agent - AI 模拟面试官

提供模拟面试能力，支持多轮对话、追问、评估。
使用依赖注入：LLM、QdrantManager、EmbeddingAdapter。
"""

from __future__ import annotations

import json
import random
import re
from datetime import datetime
from typing import Any, AsyncIterator, Optional, List, Tuple
import uuid

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.domain.question.repositories import QuestionRepository
from app.domain.question.aggregates import Question
from app.domain.shared.enums import MasteryLevel, SessionStatus, QuestionStatus, DifficultyLevel
from app.infrastructure.adapters.embedding_adapter import EmbeddingAdapter
from app.infrastructure.common.logger import logger
from app.infrastructure.common.prompt import build_prompt
from app.domain.shared.enums import SessionStatus, QuestionStatus, DifficultyLevel
from app.domain.interview.aggregates import InterviewSession, InterviewQuestion, InterviewSessionCreate, InterviewReport
from app.application.agents.shared.base_agent import LLMType
from app.application.agents.interview.prompts import PROMPTS_DIR
from app.infrastructure.config.settings import get_settings


# 公司类型与面试风格映射
COMPANY_STYLES = {
    "字节跳动": "务实、注重细节和深度",
    "阿里巴巴": "注重价值观匹配和系统性思维",
    "腾讯": "温和但有深度，注重实际应用",
    "百度": "注重技术细节和底层原理",
    "美团": "务实、注重业务理解",
    "京东": "注重系统设计和稳定性",
    "快手": "注重创新和快速响应",
    "拼多多": "注重效率和成本意识",
    "小红书": "注重用户体验和创新",
}


def parse_evaluation(response: str) -> Tuple[int, str, bool]:
    """解析 LLM 评估响应，提取评分、评价和决定

    Args:
        response: LLM 返回的评估文本

    Returns:
        (score, evaluation, should_continue)
        - score: 评分 0-100
        - evaluation: 评价文本
        - should_continue: 是否进入下一题
    """
    score = 0
    evaluation = ""
    should_continue = False

    # 解析评分
    score_match = re.search(r"【评分】\s*(\d+)\s*分", response)
    if score_match:
        score = int(score_match.group(1))

    # 解析评价
    eval_match = re.search(r"【评价】\s*(.+?)(?=【决定】|$)", response, re.DOTALL)
    if eval_match:
        evaluation = eval_match.group(1).strip()

    # 解析决定
    if "【决定】进入下一题" in response:
        should_continue = True
    elif "【决定】继续追问" in response:
        should_continue = False

    return score, evaluation, should_continue


class InterviewAgent:
    """面试会话管理器

    管理面试会话的创建、进行、结束等生命周期。

    使用依赖注入：
    - llm: ChatOpenAI 实例
    - question_repo: QuestionRepository 实例
    - embedding_adapter: EmbeddingAdapter 实例
    - scorer_agent: ScorerAgent 实例（可选）
    - max_follow_ups: 追问次数上限（从配置读取）
    """

    def __init__(
        self,
        llm: LLMType,
        question_repo: QuestionRepository,
        embedding_adapter: EmbeddingAdapter,
        scorer_agent: Optional["ScorerAgent"] = None,
        prompts_dir: Any = PROMPTS_DIR,
        max_follow_ups: Optional[int] = None,
    ) -> None:
        """初始化 InterviewAgent

        Args:
            llm: LLM 实例（依赖注入）
            question_repo: 题目仓库实例（依赖注入）
            embedding_adapter: 嵌入适配器实例（依赖注入）
            scorer_agent: 评分 Agent 实例（依赖注入，可选）
            prompts_dir: Prompt 目录路径
            max_follow_ups: 追问次数上限（默认从配置读取）
        """
        self._llm = llm
        self._question_repo = question_repo
        self._embedding_adapter = embedding_adapter
        self._scorer_agent = scorer_agent
        self._prompts_dir = prompts_dir
        self._max_follow_ups = max_follow_ups or get_settings().interview_max_follow_ups
        self._sessions: dict[str, InterviewSession] = {}

    def _get_system_prompt(self, session: InterviewSession) -> str:
        """获取面试官系统提示词"""
        style = COMPANY_STYLES.get(session.company, "专业、友好、有深度")
        return build_prompt(
            "interviewer_system.md",
            self._prompts_dir,
            company=session.company,
            position=session.position,
            style=style,
        )

    def _count_by_mastery(
        self,
        company: str,
        position: str,
        mastery_level: MasteryLevel,
    ) -> int:
        """统计指定公司/岗位/掌握度的题目数量

        Args:
            company: 公司名称
            position: 岗位名称
            mastery_level: 掌握度等级

        Returns:
            题目数量
        """
        query_filter = self._question_repo._client.build_filter(
            company=company,
            position=position,
            mastery_level=mastery_level.value,
        )
        return self._question_repo._client.count(query_filter)

    def _fetch_by_mastery(
        self,
        company: str,
        position: str,
        mastery_level: MasteryLevel,
        query_vector: list[float],
        limit: int,
    ) -> list[Tuple[Question, float]]:
        """从指定掌握度池中检索题目

        Args:
            company: 公司名称
            position: 岗位名称
            mastery_level: 掌握度等级
            query_vector: 查询向量
            limit: 返回数量

        Returns:
            [(Question, score)] 列表
        """
        filter_conditions = {
            "company": company,
            "position": position,
            "mastery_level": mastery_level.value,
        }
        return self._question_repo.search(
            query_vector=query_vector,
            filter_conditions=filter_conditions,
            limit=limit,
        )

    def create_session(
        self,
        user_id: str,
        request: InterviewSessionCreate,
    ) -> InterviewSession:
        """创建面试会话

        Args:
            user_id: 用户 ID
            request: 创建请求

        Returns:
            新创建的面试会话

        Raises:
            ValueError: 题库中没有足够的题目
        """
        session_id = str(uuid.uuid4())

        session = InterviewSession(
            session_id=session_id,
            user_id=user_id,
            company=request.company,
            position=request.position,
            difficulty=DifficultyLevel(request.difficulty),
            total_questions=request.total_questions,
            status=SessionStatus.ACTIVE,
        )

        # 预加载题目
        self._preload_questions(session)

        if not session.questions:
            raise ValueError(f"题库中没有足够的题目：公司={request.company}, 岗位={request.position}")

        self._sessions[session_id] = session
        logger.info(f"Created interview session: {session_id}, questions: {len(session.questions)}")

        return session

    def _preload_questions(self, session: InterviewSession) -> None:
        """预加载面试题目（掌握度驱动自适应策略）

        算法：
        1. 统计公司/岗位下各掌握度的题目数量
        2. 按权重分配题目数量（LEVEL_0: 60%, LEVEL_1: 30%, LEVEL_2: 10%）
        3. 从各池中检索相关题目（向量相似度）
        4. 合并并随机打乱

        Args:
            session: 面试会话
        """
        context = f"公司：{session.company} | 岗位：{session.position} | 面试题"
        query_vector = self._embedding_adapter.embed(context)

        # 统计各掌握度池的题目数量
        counts = {
            MasteryLevel.LEVEL_0: self._count_by_mastery(session.company, session.position, MasteryLevel.LEVEL_0),
            MasteryLevel.LEVEL_1: self._count_by_mastery(session.company, session.position, MasteryLevel.LEVEL_1),
            MasteryLevel.LEVEL_2: self._count_by_mastery(session.company, session.position, MasteryLevel.LEVEL_2),
        }

        total_available = sum(counts.values())
        if total_available == 0:
            logger.warning("No questions found from QuestionRepository")
            return

        # 按权重分配题目数量
        weights = {
            MasteryLevel.LEVEL_0: 0.6,
            MasteryLevel.LEVEL_1: 0.3,
            MasteryLevel.LEVEL_2: 0.1,
        }

        allocations = {}
        remaining = session.total_questions

        for level in [MasteryLevel.LEVEL_0, MasteryLevel.LEVEL_1, MasteryLevel.LEVEL_2]:
            desired = int(session.total_questions * weights[level])
            actual = min(desired, counts[level], remaining)
            allocations[level] = actual
            remaining -= actual

        # 如果还有剩余（因某些池题目不足），从 LEVEL_0 补充
        if remaining > 0 and counts[MasteryLevel.LEVEL_0] > allocations[MasteryLevel.LEVEL_0]:
            extra = min(remaining, counts[MasteryLevel.LEVEL_0] - allocations[MasteryLevel.LEVEL_0])
            allocations[MasteryLevel.LEVEL_0] += extra

        # 从各池检索题目
        all_candidates: list[Tuple[Question, float]] = []

        for level, count in allocations.items():
            if count > 0:
                candidates = self._fetch_by_mastery(
                    session.company,
                    session.position,
                    level,
                    query_vector,
                    limit=count * 2,
                )
                all_candidates.extend(candidates)

        # 随机打乱并选取
        random.shuffle(all_candidates)
        selected = all_candidates[:session.total_questions]

        # 转换为 InterviewQuestion
        for q, _score in selected:
            interview_question = InterviewQuestion(
                question_id=q.question_id,
                question_text=q.question_text,
                question_type=q.question_type.value,
                difficulty=session.difficulty,
                knowledge_points=q.core_entities or [],
                status=QuestionStatus.PENDING,
                mastery_before=q.mastery_level.value,
            )
            session.questions.append(interview_question)

        logger.info(
            f"Preloaded {len(session.questions)} questions for session {session.session_id} "
            f"(LEVEL_0: {allocations[MasteryLevel.LEVEL_0]}, "
            f"LEVEL_1: {allocations[MasteryLevel.LEVEL_1]}, "
            f"LEVEL_2: {allocations[MasteryLevel.LEVEL_2]})"
        )

    def get_session(self, session_id: str) -> Optional[InterviewSession]:
        """获取面试会话

        Args:
            session_id: 会话 ID

        Returns:
            面试会话，如果不存在返回 None
        """
        return self._sessions.get(session_id)

    async def process_answer_stream(
        self,
        session_id: str,
        answer: str,
    ) -> AsyncIterator[str]:
        """流式处理用户回答（集成 Scorer Agent）

        Args:
            session_id: 会话 ID
            answer: 用户回答

        Yields:
            流式输出的文本片段（JSON 格式）
        """
        session = self.get_session(session_id)
        if not session:
            yield json.dumps({"type": "error", "message": "Session not found"})
            return

        current_question = session.get_current_question()
        if not current_question:
            yield json.dumps({"type": "error", "message": "No current question"})
            return

        current_question.user_answer = answer
        current_question.status = QuestionStatus.ANSWERING
        current_question.answered_at = datetime.now()

        score: int = 0
        evaluation: str = ""
        mastery_before: Optional[MasteryLevel] = None
        mastery_after: Optional[MasteryLevel] = None

        # 使用 Scorer Agent 进行专业评分
        if self._scorer_agent:
            try:
                # 先查询题目获取原始 mastery_level（用于报告追踪变化）
                original_question = self._question_repo.find_by_id(current_question.question_id)
                if original_question:
                    mastery_before = original_question.mastery_level

                # Scorer Agent 是 async 方法，需要 await
                score_result = await self._scorer_agent.score(
                    question_id=current_question.question_id,
                    user_answer=answer,
                )
                score = score_result.score
                evaluation = score_result.feedback
                mastery_after = score_result.mastery_level
                current_question.score = score
                current_question.feedback = evaluation
                current_question.mastery_after = mastery_after.value

                logger.info(
                    f"Scorer evaluated: question={current_question.question_id}, "
                    f"score={score}, mastery={mastery_before.name if mastery_before else 'N/A'} -> {mastery_after.name}"
                )

                yield json.dumps({
                    "type": "score_result",
                    "score": score,
                    "mastery_before": mastery_before.name if mastery_before else None,
                    "mastery_after": mastery_after.name,
                    "strengths": score_result.strengths,
                    "improvements": score_result.improvements,
                    "feedback": evaluation,
                })

            except Exception as e:
                logger.error(f"Scorer Agent failed: {e}, falling back to LLM evaluation")
                score, evaluation = await self._fallback_evaluation_stream(
                    session, current_question, answer
                )
        else:
            score, evaluation = await self._fallback_evaluation_stream(
                session, current_question, answer
            )

        should_continue = score >= 70

        if should_continue:
            # 回答达标，进入下一题
            current_question.status = QuestionStatus.SCORED
            session.current_question_idx += 1

            if session.is_completed():
                await self._end_session(session)
                yield json.dumps({
                    "type": "completed",
                    "message": "面试已结束。感谢你的参与！",
                    "session_id": session.session_id,
                })
            else:
                next_question = session.get_current_question()
                yield json.dumps({
                    "type": "next_question_ready",
                    "question_idx": session.current_question_idx,
                    "next_question": next_question.question_text if next_question else None,
                    "score": score,
                })
        else:
            # 回答未达标，检查追问次数
            follow_up_count = len(current_question.follow_ups)

            if follow_up_count >= self._max_follow_ups:
                # 已达到追问上限（已有 3 次追问），强制进入下一题
                # 说明用户在问题理解上存在根本性不足
                current_question.status = QuestionStatus.SCORED
                session.current_question_idx += 1

                # 先追加本次评估到追问列表
                current_question.follow_ups.append(evaluation)

                # 生成总结性反馈
                summary_feedback = self._generate_follow_up_summary(
                    current_question, score
                )
                current_question.feedback = summary_feedback

                logger.info(
                    f"Follow-up limit reached: question={current_question.question_id}, "
                    f"follow_ups={len(current_question.follow_ups)}, forcing next question"
                )

                if session.is_completed():
                    await self._end_session(session)
                    yield json.dumps({
                        "type": "completed",
                        "message": "面试已结束。感谢你的参与！",
                        "session_id": session.session_id,
                    })
                else:
                    next_question = session.get_current_question()
                    yield json.dumps({
                        "type": "force_next",
                        "message": f"该题目已追问 {self._max_follow_ups} 次，我们进入下一题。",
                        "question_idx": session.current_question_idx,
                        "next_question": next_question.question_text if next_question else None,
                        "score": score,
                        "summary_feedback": summary_feedback,
                        "follow_up_count": follow_up_count + 1,
                    })
            else:
                # 继续追问，先追加本次评估
                current_question.follow_ups.append(evaluation)
                new_count = len(current_question.follow_ups)

                # 引导用户深入思考
                yield json.dumps({
                    "type": "follow_up",
                    "question_idx": session.current_question_idx,
                    "score": score,
                    "follow_up_count": new_count,
                    "max_follow_ups": self._max_follow_ups,
                    "remaining_chances": self._max_follow_ups - new_count,
                })

    def _generate_follow_up_summary(
        self,
        question: InterviewQuestion,
        final_score: int,
    ) -> str:
        """生成追问总结性反馈

        当用户连续多次追问仍未达标时，给出明确的诊断性反馈，
       指出用户在问题理解上的根本性不足。

        Args:
            question: 面试题目
            final_score: 最终评分

        Returns:
            总结性反馈文本
        """
        knowledge_points = ", ".join(question.knowledge_points) if question.knowledge_points else "相关知识"

        if final_score < 40:
            # 回答质量很低
            return (
                f"经过 {self._max_follow_ups} 次追问，你对这道题的掌握程度仍然较低。"
                f"建议你系统学习 {knowledge_points} 相关内容，"
                f"理解核心概念后再尝试回答。"
            )
        elif final_score < 60:
            # 回答质量中等偏下
            return (
                f"经过 {self._max_follow_ups} 次追问，你对这道题的理解还不够深入。"
                f"建议加强对 {knowledge_points} 的学习，"
                f"重点关注核心原理和实际应用场景。"
            )
        else:
            # 回答接近达标但仍有差距
            return (
                f"经过 {self._max_follow_ups} 次追问，你的回答已经接近要求。"
                f"建议进一步巩固 {knowledge_points} 的细节，"
                f"确保能够清晰、完整地表达核心要点。"
            )

    async def _fallback_evaluation_stream(
        self,
        session: InterviewSession,
        current_question: InterviewQuestion,
        answer: str,
    ) -> Tuple[int, str]:
        """原有 LLM 流式评估（降级方案）

        Args:
            session: 面试会话
            current_question: 当前题目
            answer: 用户回答

        Returns:
            (score, evaluation)
        """
        system_prompt = self._get_system_prompt(session)
        user_prompt = build_prompt(
            "interview_evaluate.md",
            self._prompts_dir,
            question_text=current_question.question_text,
            question_type=current_question.question_type,
            knowledge_points=", ".join(current_question.knowledge_points) or "无",
            answer=answer,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        response_chunks = []
        async for chunk in self._llm.astream(messages):
            content = chunk.content
            if content:
                response_chunks.append(content)

        full_response = "".join(response_chunks)
        score, evaluation, _should_continue = parse_evaluation(full_response)

        current_question.score = score
        current_question.feedback = evaluation

        return score, evaluation

    async def get_hint_stream(self, session_id: str) -> AsyncIterator[str]:
        """流式获取提示

        Args:
            session_id: 会话 ID

        Yields:
            流式输出的提示内容（JSON 格式）
        """
        session = self.get_session(session_id)
        if not session:
            yield json.dumps({"type": "error", "message": "Session not found"})
            return

        current_question = session.get_current_question()
        if not current_question:
            yield json.dumps({"type": "error", "message": "No current question"})
            return

        system_prompt = self._get_system_prompt(session)
        user_prompt = build_prompt(
            "interview_hint.md",
            self._prompts_dir,
            question_text=current_question.question_text,
        )

        hint_chunks = []
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        async for chunk in self._llm.astream(messages):
            content = chunk.content
            if content:
                hint_chunks.append(content)
                yield json.dumps({"type": "text", "content": content})

        # 保存提示
        current_question.hints_given.append("".join(hint_chunks))

    async def skip_question(self, session_id: str) -> dict:
        """跳过当前题目

        Args:
            session_id: 会话 ID

        Returns:
            下一题信息
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        current_question = session.get_current_question()
        if current_question:
            current_question.status = QuestionStatus.SKIPPED
            # 跳过的题目评分设为 0
            current_question.score = 0

        session.current_question_idx += 1

        if session.is_completed():
            return await self._end_session(session)

        next_question = session.get_current_question()
        return {
            "type": "next_question",
            "question": next_question.question_text if next_question else None,
            "question_idx": session.current_question_idx,
            "message": "好的，我们来看下一题。",
        }

    async def _end_session(self, session: InterviewSession) -> dict:
        """结束面试会话

        Args:
            session: 面试会话

        Returns:
            结束信息
        """
        session.status = SessionStatus.COMPLETED
        session.ended_at = datetime.now()

        # 计算统计
        answered = [q for q in session.questions if q.status in (QuestionStatus.SCORED, QuestionStatus.SKIPPED)]
        session.correct_count = sum(1 for q in answered if q.score and q.score >= 70)

        logger.info(f"Interview session ended: {session.session_id}, "
                   f"score: {session.calculate_average_score():.1f}, "
                   f"correct: {session.correct_count}/{len(answered)}")

        return {
            "type": "completed",
            "message": "面试已结束。感谢你的参与！",
            "session_id": session.session_id,
        }

    def get_report(self, session_id: str) -> Optional[InterviewReport]:
        """生成面试报告

        Args:
            session_id: 会话 ID

        Returns:
            面试报告
        """
        session = self.get_session(session_id)
        if not session or session.status != SessionStatus.COMPLETED:
            return None

        answered = [q for q in session.questions if q.status in (QuestionStatus.SCORED, QuestionStatus.SKIPPED)]
        skipped = [q for q in session.questions if q.status == QuestionStatus.SKIPPED]

        # 计算时长
        duration_minutes = 0.0
        if session.ended_at and session.started_at:
            duration_minutes = (session.ended_at - session.started_at).total_seconds() / 60

        # 分析知识点 - 基于实际评分
        strong_points: List[str] = []
        weak_points: List[str] = []

        for q in answered:
            if q.score is not None:
                if q.score >= 80:
                    strong_points.extend(q.knowledge_points)
                elif q.score < 60:
                    weak_points.extend(q.knowledge_points)

        # 去重
        strong_points = list(set(strong_points))[:5]
        weak_points = list(set(weak_points))[:5]

        # 生成报告
        report = InterviewReport(
            session_id=session.session_id,
            company=session.company,
            position=session.position,
            total_questions=session.total_questions,
            answered_questions=len(answered),
            correct_count=session.correct_count,
            average_score=session.calculate_average_score(),
            duration_minutes=duration_minutes,
            strengths=strong_points,
            weaknesses=weak_points,
            knowledge_gaps=weak_points,
            recommendations=[
                f"建议加强对 {kp} 的学习" for kp in weak_points[:3]
            ],
            question_details=[
                {
                    "question": q.question_text,
                    "score": q.score,
                    "status": q.status,
                    "feedback": q.feedback,
                }
                for q in session.questions
            ],
        )

        return report


__all__ = ["InterviewAgent", "parse_evaluation"]