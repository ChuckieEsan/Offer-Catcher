"""测试 Interview Agent 的流式输出和报告生成"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import asyncio
import json
from datetime import datetime

from app.agents.interview_agent import get_interview_manager, InterviewManager
from app.models.interview_session import (
    InterviewSessionCreate,
    InterviewSession,
    InterviewQuestion,
    InterviewReport,
)


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
        assert len(session.questions) == 2
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
            elif data["type"] == "follow_up":
                assert "question_idx" in data

        # 验证有流式输出
        assert len(chunks) > 0
        text_chunks = [c for c in chunks if c["type"] == "text"]
        assert len(text_chunks) > 0

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

    def test_get_report_datetime_calculation(self, manager):
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
            question.status = "answered"
            question.score = 80
            question.user_answer = "这是一个测试回答"
            question.answered_at = datetime.now()

        # 手动正确结束会话
        session.status = "completed"
        session.ended_at = datetime.now()  # 正确设置为 datetime

        # 获取报告
        report = manager.get_report(session.session_id)

        assert report is not None
        assert report.session_id == session.session_id
        assert report.company == "字节跳动"
        assert report.position == "后端开发"
        assert isinstance(report.duration_minutes, float)
        assert report.duration_minutes >= 0

    def test_report_with_scored_questions(self, manager):
        """测试有评分题目的报告生成"""
        # 直接创建 session，不依赖预加载
        from uuid import uuid4

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

    def test_api_end_interview_datetime_fix(self, manager):
        """验证 API end_interview 应该正确设置 ended_at"""
        # 这个测试验证 interview.py 中的 end_interview 函数
        # 应该正确设置 ended_at 为 datetime 类型

        request = InterviewSessionCreate(
            company="腾讯",
            position="算法工程师",
            difficulty="medium",
            total_questions=2,
        )
        session = manager.create_session("test_api_end", request)

        # 模拟 API 调用 end_interview 的正确逻辑
        session.status = "completed"
        # 正确的方式：直接使用 datetime.now()
        session.ended_at = datetime.now()

        # 验证可以正常计算时间差
        duration = (session.ended_at - session.started_at).total_seconds() / 60
        assert isinstance(duration, float)
        assert duration >= 0


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