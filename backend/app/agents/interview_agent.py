"""AI 模拟面试官 Agent

提供模拟面试能力，支持多轮对话、追问、评估。
"""

import json
from typing import Optional, List, AsyncIterator
from datetime import datetime
import uuid

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate

from app.llm import get_llm
from app.db.qdrant_client import get_qdrant_manager
from app.memory.long_term import get_long_term_memory
from app.models.interview_session import (
    InterviewSession,
    InterviewQuestion,
    InterviewSessionCreate,
    InterviewReport,
)
from app.tools.interview_tools import (
    get_next_question,
    evaluate_answer,
    get_interview_style,
    generate_follow_up,
)
from app.tools.search_question_tool import search_questions
from app.tools.memory_tools import update_learning_progress
from app.tools.embedding_tool import get_embedding_tool
from app.utils.logger import logger
from app.utils.cache import singleton


class InterviewManager:
    """面试会话管理器

    管理面试会话的创建、进行、结束等生命周期。
    """

    def __init__(self):
        self._sessions: dict[str, InterviewSession] = {}
        self._qdrant = get_qdrant_manager()
        self._memory = get_long_term_memory()
        self._llm = get_llm("deepseek", "chat")

    def _get_interview_prompt(self, session: InterviewSession) -> str:
        """获取面试官 Prompt"""
        style = self._get_company_style(session.company)
        return f"""你是{session.company}的面试官，正在面试{session.position}岗位的候选人。
你的风格应该{style}。

面试流程：
1. 出题阶段：根据用户画像和薄弱知识点出题
2. 追问阶段：如果用户回答不完整，追问细节
3. 提示阶段：如果用户卡住，给出提示而非答案
4. 评估阶段：用户完成回答后，评估并给出反馈

请用自然、友好的语气与候选人交流。"""

    def _get_company_style(self, company: str) -> str:
        """获取公司面试风格"""
        styles = {
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
        return styles.get(company, "专业、友好、有深度")

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

        self._sessions[session_id] = session
        logger.info(f"Created interview session: {session_id}")

        return session

    def _preload_questions(self, session: InterviewSession) -> None:
        """预加载面试题目

        Args:
            session: 面试会话
        """
        embedding_tool = get_embedding_tool()

        # 构建查询上下文
        context = f"公司：{session.company} | 岗位：{session.position} | 面试题"
        query_vector = embedding_tool.embed_text(context)

        # 搜索题目
        candidates = self._qdrant.search(query_vector, limit=session.total_questions * 2)

        # 根据难度过滤
        if session.difficulty == "easy":
            candidates = [c for c in candidates if "基础" in c.question_text or "概念" in c.question_text][:session.total_questions]
        elif session.difficulty == "hard":
            candidates = [c for c in candidates if "高级" in c.question_text or "优化" in c.question_text][:session.total_questions]
        else:
            candidates = candidates[:session.total_questions]

        # 转换为 InterviewQuestion
        for i, c in enumerate(candidates):
            question = InterviewQuestion(
                question_id=c.question_id,
                question_text=c.question_text,
                question_type=c.question_type,
                difficulty=session.difficulty,
                knowledge_points=c.core_entities,
                status="pending",
            )
            session.questions.append(question)

        logger.info(f"Preloaded {len(session.questions)} questions for session {session.session_id}")

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
        system_prompt = self._get_interview_prompt(session)
        user_prompt = f"""候选人回答了题目："{current_question.question_text}"

候选人的回答：
{answer}

请评估这个回答并给出反馈。

规则：
1. 如果回答正确或基本正确：先给出简短的正面评价，最后必须说"让我们继续下一题"
2. 如果回答有不足：指出问题所在，并追问一个具体的问题

注意：
- 用自然、友好的语气
- 追问要具体，只问一个问题
- 回答满意时，必须包含"让我们继续下一题"这句话"""

        # 流式生成回复
        response_chunks = []
        messages = [
            ("system", system_prompt),
            ("human", user_prompt),
        ]

        try:
            # 使用同步 LLM 的 stream 方法（它在内部是同步迭代器）
            for chunk in self._llm.stream(messages):
                content = chunk.content
                if content:
                    response_chunks.append(content)
                    yield json.dumps({"type": "text", "content": content})

            # 收集完整回复，决定下一步
            full_response = "".join(response_chunks)

            # 根据回复内容判断是否进入下一题
            should_next = self._should_move_to_next(full_response, current_question)

            if should_next:
                # 进入下一题
                session.current_question_idx += 1
                current_question.status = "scored"

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
                        "message": full_response,
                    })
            else:
                # 继续追问
                yield json.dumps({
                    "type": "follow_up",
                    "question_idx": session.current_question_idx,
                    "message": full_response,
                })

        except Exception as e:
            logger.error(f"Stream error: {e}")
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

        system_prompt = self._get_interview_prompt(session)
        user_prompt = f"""候选人对题目 "{current_question.question_text}" 请求提示。

请给出一个引导性的提示，帮助候选人思考，但不要直接给出答案。
提示要简洁、有启发性。"""

        messages = [
            ("system", system_prompt),
            ("human", user_prompt),
        ]

        hint_chunks = []
        for chunk in self._llm.stream(messages):
            content = chunk.content
            if content:
                hint_chunks.append(content)
                yield json.dumps({"type": "text", "content": content})

        # 保存提示
        current_question.hints_given.append("".join(hint_chunks))

    def _should_move_to_next(self, response: str, question: InterviewQuestion) -> bool:
        """判断是否应该进入下一题

        Args:
            response: AI 回复
            question: 当前题目

        Returns:
            是否进入下一题
        """
        # 简单判断：检测回复中是否包含"让我们继续下一题"或类似信号
        next_signal_keywords = [
            "让我们继续下一题",
            "让我们进入下一题",
            "下一题",
            "继续下一题",
        ]

        for kw in next_signal_keywords:
            if kw in response:
                return True

        # 如果已经追问超过 2 次，强制进入下一题
        if len(question.follow_ups) >= 2:
            return True

        # 默认继续追问，记录追问内容
        question.follow_ups.append(response)
        return False

    async def get_hint(self, session_id: str) -> str:
        """获取提示

        Args:
            session_id: 会话 ID

        Returns:
            提示内容
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        current_question = session.get_current_question()
        if not current_question:
            raise ValueError("No current question")

        # 构建提示 Prompt
        system_prompt = self._get_interview_prompt(session)
        user_prompt = f"""候选人对题目 "{current_question.question_text}" 请求提示。

请给出一个引导性的提示，帮助候选人思考，但不要直接给出答案。
提示要简洁、有启发性。"""

        messages = [
            ("system", system_prompt),
            ("human", user_prompt),
        ]

        result = self._llm.invoke(messages)
        hint = result.content

        current_question.hints_given.append(hint)

        return hint

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

        # 更新用户学习进度
        if session.user_id:
            completed_ids = [q.question_id for q in answered if q.score and q.score >= 70]
            if completed_ids:
                self._memory.save_progress(
                    session.user_id,
                    self._memory.get_progress(session.user_id) or type('obj', (object,), {
                        'mastered_entities': [],
                        'pending_review_question_ids': [],
                        'total_questions_answered': 0,
                    })()
                )

        logger.info(f"Interview session ended: {session.session_id}, score: {session.calculate_average_score()}")

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
        duration_minutes = 0
        if session.ended_at and session.started_at:
            duration_minutes = (session.ended_at - session.started_at).total_seconds() / 60

        # 分析知识点
        all_knowledge_points = []
        for q in answered:
            all_knowledge_points.extend(q.knowledge_points)

        strong_points = []
        weak_points = []

        for q in answered:
            if q.score and q.score >= 80:
                strong_points.extend(q.knowledge_points)
            elif q.score and q.score < 60:
                weak_points.extend(q.knowledge_points)

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
            strengths=list(set(strong_points))[:5],
            weaknesses=list(set(weak_points))[:5],
            knowledge_gaps=list(set(weak_points))[:5],
            recommendations=[
                f"建议加强对 {kp} 的学习" for kp in set(weak_points)[:3]
            ],
            question_details=[
                {
                    "question": q.question_text,
                    "score": q.score,
                    "status": q.status,
                }
                for q in session.questions
            ],
        )

        return report


# 全局单例
_interview_manager: Optional[InterviewManager] = None


def get_interview_manager() -> InterviewManager:
    """获取面试管理器单例"""
    global _interview_manager
    if _interview_manager is None:
        _interview_manager = InterviewManager()
    return _interview_manager


__all__ = [
    "InterviewManager",
    "get_interview_manager",
]