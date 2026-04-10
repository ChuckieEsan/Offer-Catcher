"""AI 模拟面试官 Agent

提供模拟面试能力，支持多轮对话、追问、评估。
"""

import json
import random
import re
from datetime import datetime
from typing import Optional, List, AsyncIterator, Tuple
import uuid

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.llm import get_llm
from app.db.qdrant_client import get_qdrant_manager
from app.memory.long_term import get_long_term_memory
from app.models.interview_session import (
    InterviewSession,
    InterviewQuestion,
    InterviewSessionCreate,
    InterviewReport,
)
from app.tools.search_question_tool import search_questions
from app.tools.embedding_tool import get_embedding_tool
from app.utils.logger import logger
from app.agents.prompts import build_prompt
from app.utils.cache import singleton


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


class InterviewManager:
    """面试会话管理器

    管理面试会话的创建、进行、结束等生命周期。
    """

    def __init__(self):
        self._sessions: dict[str, InterviewSession] = {}
        self._qdrant = get_qdrant_manager()
        self._memory = get_long_term_memory()
        self._llm = get_llm("deepseek", "chat")

    def _get_system_prompt(self, session: InterviewSession) -> str:
        """获取面试官系统提示词"""
        style = COMPANY_STYLES.get(session.company, "专业、友好、有深度")
        return build_prompt(
            "interviewer_system.md",
            company=session.company,
            position=session.position,
            style=style,
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
        """
        session_id = str(uuid.uuid4())

        session = InterviewSession(
            session_id=session_id,
            user_id=user_id,
            company=request.company,
            position=request.position,
            difficulty=request.difficulty,
            total_questions=request.total_questions,
            status="active",
        )

        # 预加载题目
        self._preload_questions(session)

        # 如果没有预加载到题目，生成默认题目
        if not session.questions:
            self._generate_default_questions(session)

        self._sessions[session_id] = session
        logger.info(f"Created interview session: {session_id}, questions: {len(session.questions)}")

        return session

    def _preload_questions(self, session: InterviewSession) -> None:
        """预加载面试题目

        从题库中随机选取题目，确保每次面试有不同的题目组合。

        Args:
            session: 面试会话
        """
        embedding_tool = get_embedding_tool()

        # 构建查询上下文
        context = f"公司：{session.company} | 岗位：{session.position} | 面试题"
        query_vector = embedding_tool.embed_text(context)

        # 搜索更多候选题目，从中随机选取
        # 取 3 倍数量的候选，保证随机性
        candidate_limit = session.total_questions * 3
        candidates = self._qdrant.search(query_vector, limit=candidate_limit)

        if not candidates:
            logger.warning("No candidates found from Qdrant")
            return

        # 随机打乱候选题目
        random.shuffle(candidates)

        # 选取指定数量的题目
        selected = candidates[:session.total_questions]

        # 转换为 InterviewQuestion
        for c in selected:
            question = InterviewQuestion(
                question_id=c.question_id,
                question_text=c.question_text,
                question_type=c.question_type,
                difficulty=session.difficulty,
                knowledge_points=c.core_entities or [],
                status="pending",
            )
            session.questions.append(question)

        logger.info(f"Preloaded {len(session.questions)} questions for session {session.session_id}")

    def _generate_default_questions(self, session: InterviewSession) -> None:
        """当题库为空时生成默认题目

        Args:
            session: 面试会话
        """
        default_questions = [
            ("请介绍一下你最近做的一个项目，以及你在其中的角色和贡献。", "project"),
            ("你如何处理工作中遇到的技术难题？请举一个具体的例子。", "behavioral"),
            ("请描述一下你对微服务架构的理解，以及它的优缺点。", "knowledge"),
            ("如果系统出现性能问题，你会如何排查和优化？", "scenario"),
            ("请解释一下数据库索引的原理，以及如何优化查询性能。", "knowledge"),
        ]

        # 随机打乱默认题目
        random.shuffle(default_questions)

        for i, (text, q_type) in enumerate(default_questions[:session.total_questions]):
            question = InterviewQuestion(
                question_id=f"default_{i}",
                question_text=text,
                question_type=q_type,
                difficulty=session.difficulty,
                knowledge_points=[],
                status="pending",
            )
            session.questions.append(question)

        logger.warning(f"Generated {len(session.questions)} default questions for session {session.session_id}")

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
        """流式处理用户回答

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

        # 更新用户回答
        current_question.user_answer = answer
        current_question.status = "answered"
        current_question.answered_at = datetime.now()

        # 构建评估 Prompt
        system_prompt = self._get_system_prompt(session)
        user_prompt = build_prompt(
            "interview_evaluate.md",
            question_text=current_question.question_text,
            question_type=current_question.question_type,
            knowledge_points=", ".join(current_question.knowledge_points) or "无",
            answer=answer,
        )

        # 流式生成回复
        response_chunks = []
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            async for chunk in self._llm.astream(messages):
                content = chunk.content
                if content:
                    response_chunks.append(content)
                    yield json.dumps({"type": "text", "content": content})

            # 收集完整回复
            full_response = "".join(response_chunks)

            # 解析评估结果
            score, evaluation, should_continue = parse_evaluation(full_response)

            # 更新题目评分
            current_question.score = score
            current_question.feedback = evaluation

            if should_continue or score >= 70:
                # 进入下一题
                current_question.status = "scored"
                session.current_question_idx += 1

                if session.is_completed():
                    # 面试结束
                    await self._end_session(session)
                    yield json.dumps({
                        "type": "completed",
                        "message": "面试已结束。感谢你的参与！",
                        "session_id": session.session_id,
                    })
                else:
                    # 有下一题，发送信号让前端显示按钮
                    next_question = session.get_current_question()
                    yield json.dumps({
                        "type": "next_question_ready",
                        "question_idx": session.current_question_idx,
                        "next_question": next_question.question_text if next_question else None,
                        "score": score,
                    })
            else:
                # 继续追问，记录追问次数
                current_question.follow_ups.append(full_response)
                yield json.dumps({
                    "type": "follow_up",
                    "question_idx": session.current_question_idx,
                    "score": score,
                })

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield json.dumps({"type": "error", "message": str(e)})

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
            current_question.status = "skipped"
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
        session.status = "completed"
        session.ended_at = datetime.now()

        # 计算统计
        answered = [q for q in session.questions if q.status in ["answered", "scored"]]
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
        if not session or session.status != "completed":
            return None

        answered = [q for q in session.questions if q.status in ["answered", "scored"]]
        skipped = [q for q in session.questions if q.status == "skipped"]

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


@singleton
def get_interview_manager() -> InterviewManager:
    """获取面试管理器单例"""
    return InterviewManager()


__all__ = [
    "InterviewManager",
    "get_interview_manager",
]