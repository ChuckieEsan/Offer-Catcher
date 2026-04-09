"""测试 Interview Agent 的流式输出和报告生成"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import asyncio
import json
from datetime import datetime
from uuid import uuid4

from app.agents.interview_agent import get_interview_manager, InterviewManager, parse_evaluation
from app.models.interview_session import (
    InterviewSessionCreate,
    InterviewSession,
    InterviewQuestion,
    InterviewReport,
)


class TestParseEvaluation:
    """测试评估解析函数"""

    def test_parse_high_score(self):
        """测试解析高分评估"""
        response = """【评分】85分
【评价】回答准确，对核心概念理解到位。
【决定】进入下一题"""
        score, evaluation, should_continue = parse_evaluation(response)
        assert score == 85
        assert "准确" in evaluation
        assert should_continue is True

    def test_parse_low_score(self):
        """测试解析低分评估"""
        response = """【评分】45分
【评价】回答方向正确，但对核心原理的解释不够准确。
【决定】继续追问
你能具体说说在这个场景下，数据是如何流转的吗？"""
        score, evaluation, should_continue = parse_evaluation(response)
        assert score == 45
        assert should_continue is False

    def test_parse_missing_score(self):
        """测试缺失评分的情况"""
        response = "这是一个不错的回答，让我们继续下一题。"
        score, evaluation, should_continue = parse_evaluation(response)
        assert score == 0
        assert should_continue is False


class TestInterviewAgentStreaming:
    """测试面试 Agent 流式输出"""

    @pytest.fixture
    def manager(self):
        """获取 InterviewManager 实例"""
        return get_interview_manager()

    def test_create_session(self, manager):
        """测试创建面试会话"""
        request = InterviewSessionCreate(
            company="字节跳动",
            position="后端开发",
            difficulty="medium",
            total_questions=2,
        )

        session = manager.create_session("test_user", request)

        assert session.session_id is not None
        assert session.company == "字节跳动"
        assert session.position == "后端开发"
        assert session.status == "active"
        assert len(session.questions) > 0  # 应该有题目（预加载或默认生成）
        assert session.started_at is not None
        assert isinstance(session.started_at, datetime)

    @pytest.mark.asyncio
    async def test_process_answer_stream(self, manager):
        """测试流式处理回答"""
        # 创建会话
        request = InterviewSessionCreate(
            company="字节跳动",
            position="后端开发",
            difficulty="medium",
            total_questions=2,
        )
        session = manager.create_session("test_user_stream", request)

        # 测试流式输出
        chunks = []
        async for chunk in manager.process_answer_stream(session.session_id, "我了解一些基础知识"):
            data = json.loads(chunk)
            chunks.append(data)

            # 验证数据格式
            assert "type" in data
            if data["type"] == "text":
                assert "content" in data

        # 验证有流式输出
        assert len(chunks) > 0
        text_chunks = [c for c in chunks if c["type"] == "text"]
        assert len(text_chunks) > 0

        # 验证题目已被评分
        question = session.get_current_question()
        if question:
            assert question.score is not None, "题目应该被评分"

    @pytest.mark.asyncio
    async def test_get_hint_stream(self, manager):
        """测试流式获取提示"""
        # 创建会话
        request = InterviewSessionCreate(
            company="字节跳动",
            position="后端开发",
            difficulty="medium",
            total_questions=2,
        )
        session = manager.create_session("test_user_hint", request)

        # 测试流式提示
        chunks = []
        async for chunk in manager.get_hint_stream(session.session_id):
            data = json.loads(chunk)
            chunks.append(data)

        # 验证有流式输出
        assert len(chunks) > 0
        text_chunks = [c for c in chunks if c["type"] == "text"]
        assert len(text_chunks) > 0


class TestInterviewReport:
    """测试面试报告生成"""

    @pytest.fixture
    def manager(self):
        """获取 InterviewManager 实例"""
        return get_interview_manager()

    def test_end_session_sets_datetime(self, manager):
        """测试结束会话正确设置 ended_at 为 datetime 类型"""
        # 创建会话
        request = InterviewSessionCreate(
            company="字节跳动",
            position="后端开发",
            difficulty="medium",
            total_questions=2,
        )
        session = manager.create_session("test_user_end", request)

        # 调用 _end_session
        asyncio.run(manager._end_session(session))

        # 验证 ended_at 是正确的 datetime 类型
        assert session.ended_at is not None
        assert isinstance(session.ended_at, datetime), f"ended_at 应该是 datetime 类型，实际是 {type(session.ended_at)}"
        assert session.status == "completed"

    def test_get_report_with_scores(self, manager):
        """测试报告生成包含评分"""
        # 直接创建 session，不依赖预加载
        session_id = str(uuid4())
        session = InterviewSession(
            session_id=session_id,
            user_id="test_user_scored",
            company="阿里巴巴",
            position="前端开发",
            difficulty="easy",
            total_questions=3,
            questions=[
                InterviewQuestion(
                    question_id=f"q_{i}",
                    question_text=f"测试题目 {i}",
                    question_type="knowledge",
                    status="scored",
                    score=60 + i * 10,  # 60, 70, 80
                    user_answer=f"回答 {i}",
                    knowledge_points=[f"知识点{i}"],
                    answered_at=datetime.now(),
                )
                for i in range(3)
            ],
            current_question_idx=3,
            status="completed",
            ended_at=datetime.now(),
        )

        # 手动添加到 manager
        manager._sessions[session_id] = session

        # 获取报告
        report = manager.get_report(session_id)

        assert report is not None
        assert report.total_questions == 3
        assert report.answered_questions == 3
        assert report.average_score == 70.0  # (60 + 70 + 80) / 3
        # 至少有一个优势点（score >= 80）
        assert len(report.strengths) >= 1
        # 题目详情包含评分
        for detail in report.question_details:
            assert "score" in detail
            assert detail["score"] is not None

    def test_report_datetime_calculation(self, manager):
        """测试报告生成中的时间计算"""
        # 创建会话
        request = InterviewSessionCreate(
            company="字节跳动",
            position="后端开发",
            difficulty="medium",
            total_questions=2,
        )
        session = manager.create_session("test_user_report", request)

        # 模拟回答第一题
        question = session.get_current_question()
        if question:
            question.status = "scored"
            question.score = 80
            question.user_answer = "这是一个测试回答"
            question.answered_at = datetime.now()

        # 手动正确结束会话
        session.status = "completed"
        session.ended_at = datetime.now()

        # 获取报告
        report = manager.get_report(session.session_id)

        assert report is not None
        assert report.session_id == session.session_id
        assert isinstance(report.duration_minutes, float)
        assert report.duration_minutes >= 0

    def test_report_with_skipped_questions(self, manager):
        """测试包含跳过题目的报告"""
        session_id = str(uuid4())
        session = InterviewSession(
            session_id=session_id,
            user_id="test_user_skip",
            company="腾讯",
            position="算法工程师",
            difficulty="medium",
            total_questions=3,
            questions=[
                InterviewQuestion(
                    question_id="q_0",
                    question_text="题目1",
                    question_type="knowledge",
                    status="scored",
                    score=85,
                    knowledge_points=["算法"],
                    answered_at=datetime.now(),
                ),
                InterviewQuestion(
                    question_id="q_1",
                    question_text="题目2",
                    question_type="knowledge",
                    status="skipped",
                    score=0,  # 跳过的题目分数为0
                ),
                InterviewQuestion(
                    question_id="q_2",
                    question_text="题目3",
                    question_type="knowledge",
                    status="scored",
                    score=70,
                    knowledge_points=["数据结构"],
                    answered_at=datetime.now(),
                ),
            ],
            current_question_idx=3,
            status="completed",
            ended_at=datetime.now(),
        )

        manager._sessions[session_id] = session
        report = manager.get_report(session_id)

        assert report is not None
        assert report.answered_questions == 2  # 只有2题被回答
        # 平均分 = (85 + 0 + 70) / 3 = 51.67（跳过的题目也计入平均分）
        assert report.average_score == pytest.approx(51.67, rel=0.1)


class TestInterviewSessionState:
    """测试面试会话状态管理"""

    @pytest.fixture
    def manager(self):
        return get_interview_manager()

    def test_session_started_at_is_datetime(self, manager):
        """测试 started_at 初始化为 datetime"""
        request = InterviewSessionCreate(
            company="百度",
            position="测试开发",
            difficulty="hard",
            total_questions=1,
        )
        session = manager.create_session("test_datetime", request)

        assert isinstance(session.started_at, datetime)
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.updated_at, datetime)

    def test_skip_question(self, manager):
        """测试跳过题目"""
        request = InterviewSessionCreate(
            company="美团",
            position="运维工程师",
            difficulty="medium",
            total_questions=2,
        )
        session = manager.create_session("test_skip", request)

        # 跳过第一题
        result = asyncio.run(manager.skip_question(session.session_id))

        assert result["type"] in ["next_question", "completed"]
        assert session.current_question_idx == 1
        assert session.questions[0].status == "skipped"
        assert session.questions[0].score == 0  # 跳过的题目分数为0

    def test_default_questions_generated_when_empty(self, manager):
        """测试题库为空时生成默认题目"""
        # 创建一个会话，如果预加载题目数量不足，会生成默认题目
        request = InterviewSessionCreate(
            company="测试公司",
            position="测试岗位",
            difficulty="medium",
            total_questions=5,
        )
        session = manager.create_session("test_default", request)

        # 应该有题目（无论是预加载还是默认生成）
        assert len(session.questions) > 0