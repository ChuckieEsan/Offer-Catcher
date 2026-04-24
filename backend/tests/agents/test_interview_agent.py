"""Interview Agent 测试 - 验证掌握度驱动自适应面试引擎"""

import pytest
import asyncio
import json
from datetime import datetime
from uuid import uuid4

from app.application.agents.interview.agent import InterviewAgent, parse_evaluation
from app.application.agents.scorer.agent import ScorerAgent
from app.domain.interview.aggregates import (
    InterviewSessionCreate,
    InterviewSession,
    InterviewQuestion,
)
from app.domain.shared.enums import MasteryLevel, SessionStatus, QuestionStatus, DifficultyLevel
from app.infrastructure.adapters.llm_adapter import get_llm
from app.infrastructure.persistence.qdrant.question_repository import get_question_repository
from app.infrastructure.adapters.embedding_adapter import get_embedding_adapter


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


class TestMasteryDrivenQuestionSelection:
    """测试掌握度驱动的出题策略"""

    @pytest.fixture
    def agent_with_real_deps(self):
        """创建真实依赖的 InterviewAgent"""
        llm = get_llm("deepseek", "chat")
        question_repo = get_question_repository()
        embedding_adapter = get_embedding_adapter()

        agent = InterviewAgent(
            llm=llm,
            question_repo=question_repo,
            embedding_adapter=embedding_adapter,
            scorer_agent=None,  # 出题测试不需要 scorer
        )
        return agent

    def test_count_by_mastery(self, agent_with_real_deps):
        """测试统计各掌握度的题目数量"""
        # 使用真实题库测试
        counts = {
            MasteryLevel.LEVEL_0: agent_with_real_deps._count_by_mastery(
                "字节跳动", "后端开发", MasteryLevel.LEVEL_0
            ),
            MasteryLevel.LEVEL_1: agent_with_real_deps._count_by_mastery(
                "字节跳动", "后端开发", MasteryLevel.LEVEL_1
            ),
            MasteryLevel.LEVEL_2: agent_with_real_deps._count_by_mastery(
                "字节跳动", "后端开发", MasteryLevel.LEVEL_2
            ),
        }

        # 验证返回值是整数
        for level, count in counts.items():
            assert isinstance(count, int)
            assert count >= 0

        # 记录结果
        total = sum(counts.values())
        print(f"字节跳动/后端开发 题库分布: LEVEL_0={counts[MasteryLevel.LEVEL_0]}, "
              f"LEVEL_1={counts[MasteryLevel.LEVEL_1]}, LEVEL_2={counts[MasteryLevel.LEVEL_2]}, "
              f"总计={total}")

    @pytest.mark.skipif(
        True,  # 默认跳过，需要题库有数据时手动启用
        reason="需要题库中有字节跳动/后端开发的题目"
    )
    def test_preload_questions_weight_distribution(self, agent_with_real_deps):
        """测试出题权重分配策略（真实题库）"""
        request = InterviewSessionCreate(
            company="字节跳动",
            position="后端开发",
            difficulty="medium",
            total_questions=10,
        )

        session = agent_with_real_deps.create_session("test_weight_user", request)

        # 统计各掌握度题目数量
        level_counts = {
            MasteryLevel.LEVEL_0: 0,
            MasteryLevel.LEVEL_1: 0,
            MasteryLevel.LEVEL_2: 0,
        }

        for q in session.questions:
            if q.mastery_before == 0:
                level_counts[MasteryLevel.LEVEL_0] += 1
            elif q.mastery_before == 1:
                level_counts[MasteryLevel.LEVEL_1] += 1
            elif q.mastery_before == 2:
                level_counts[MasteryLevel.LEVEL_2] += 1

        # 验证权重分配倾向（LEVEL_0 应最多）
        print(f"出题分布: LEVEL_0={level_counts[MasteryLevel.LEVEL_0]}, "
              f"LEVEL_1={level_counts[MasteryLevel.LEVEL_1]}, "
              f"LEVEL_2={level_counts[MasteryLevel.LEVEL_2]}")

        # 由于题库分布可能不均匀，只验证有题目
        assert len(session.questions) == 10

    def test_empty_repository_raises_error(self, agent_with_real_deps):
        """测试题库为空时抛出异常"""
        # 使用不存在的数据查询
        request = InterviewSessionCreate(
            company="不存在公司XYZ",
            position="不存在岗位ABC",
            difficulty="medium",
            total_questions=5,
        )

        # 题库中没有对应公司/岗位的题目，应抛出异常
        with pytest.raises(ValueError, match="题库中没有足够的题目"):
            agent_with_real_deps.create_session("test_empty_user", request)


class TestScorerIntegration:
    """测试 Scorer Agent 集成的评分闭环"""

    @pytest.fixture
    def agent_with_scorer(self):
        """创建带 Scorer Agent 的 InterviewAgent"""
        llm = get_llm("deepseek", "chat")
        question_repo = get_question_repository()
        embedding_adapter = get_embedding_adapter()

        # 创建 Scorer Agent
        scorer_agent = ScorerAgent(
            llm=llm,
            question_repo=question_repo,
        )

        agent = InterviewAgent(
            llm=llm,
            question_repo=question_repo,
            embedding_adapter=embedding_adapter,
            scorer_agent=scorer_agent,
        )
        return agent

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        True,  # 默认跳过，需要题库有数据时手动启用
        reason="需要题库中有带答案的题目"
    )
    async def test_scorer_agent_called_in_process_answer(self, agent_with_scorer):
        """测试评分时调用 Scorer Agent（真实服务）"""
        # 创建会话（需要题库有数据）
        request = InterviewSessionCreate(
            company="字节跳动",
            position="后端开发",
            difficulty="medium",
            total_questions=1,
        )

        try:
            session = agent_with_scorer.create_session("test_scorer_user", request)
        except ValueError:
            pytest.skip("题库中没有足够的题目")

        current_question = session.get_current_question()
        if not current_question:
            pytest.skip("未能加载题目")

        # 查询原始 mastery_level
        original_question = agent_with_scorer._question_repo.find_by_id(
            current_question.question_id
        )
        mastery_before = original_question.mastery_level if original_question else None

        # 提交回答并收集流式输出
        chunks = []
        async for chunk in agent_with_scorer.process_answer_stream(
            session.session_id,
            "这是一个测试回答，用于验证评分功能。"
        ):
            data = json.loads(chunk)
            chunks.append(data)

        # 验证有 score_result 类型的输出
        score_results = [c for c in chunks if c.get("type") == "score_result"]
        if score_results:
            result = score_results[0]
            assert "score" in result
            assert "mastery_before" in result
            assert "mastery_after" in result
            assert "feedback" in result
            assert 0 <= result["score"] <= 100

            # 验证题目状态已更新
            assert current_question.score == result["score"]
            assert current_question.mastery_after is not None

            print(f"评分结果: score={result['score']}, "
                  f"mastery={result.get('mastery_before')} -> {result['mastery_after']}")

    @pytest.mark.asyncio
    async def test_fallback_evaluation_without_scorer(self):
        """测试无 Scorer Agent 时的降级评估"""
        llm = get_llm("deepseek", "chat")
        question_repo = get_question_repository()
        embedding_adapter = get_embedding_adapter()

        # 创建不带 Scorer Agent 的 InterviewAgent
        agent = InterviewAgent(
            llm=llm,
            question_repo=question_repo,
            embedding_adapter=embedding_adapter,
            scorer_agent=None,
        )

        # 手动创建会话（绕过题库查询）
        session_id = str(uuid4())
        session = InterviewSession(
            session_id=session_id,
            user_id="test_fallback_user",
            company="测试公司",
            position="测试岗位",
            difficulty=DifficultyLevel.MEDIUM,
            total_questions=1,
            status=SessionStatus.ACTIVE,
            questions=[
                InterviewQuestion(
                    question_id="test_q_1",
                    question_text="请解释一下微服务架构的优缺点",
                    question_type="knowledge",
                    difficulty=DifficultyLevel.MEDIUM,
                    knowledge_points=["微服务"],
                    status=QuestionStatus.PENDING,
                )
            ],
        )
        agent._sessions[session_id] = session

        # 提交回答
        chunks = []
        async for chunk in agent.process_answer_stream(
            session_id,
            "微服务架构的优点包括独立部署、技术栈灵活、容错性好。缺点是运维复杂、分布式事务处理困难。"
        ):
            data = json.loads(chunk)
            chunks.append(data)

        # 验证有输出（可能是 text 或其他类型，取决于 LLM 响应）
        assert len(chunks) > 0

        # 验证题目已评分
        current_question = session.get_current_question()
        assert current_question.score is not None
        assert current_question.feedback is not None


class TestInterviewSessionState:
    """测试面试会话状态管理"""

    @pytest.fixture
    def agent(self):
        """创建 InterviewAgent"""
        llm = get_llm("deepseek", "chat")
        question_repo = get_question_repository()
        embedding_adapter = get_embedding_adapter()

        return InterviewAgent(
            llm=llm,
            question_repo=question_repo,
            embedding_adapter=embedding_adapter,
            scorer_agent=None,
        )

    def test_session_datetime_fields(self, agent):
        """测试会话时间字段"""
        session_id = str(uuid4())
        session = InterviewSession(
            session_id=session_id,
            user_id="test_datetime_user",
            company="百度",
            position="测试开发",
            difficulty=DifficultyLevel.HARD,
            total_questions=1,
            status=SessionStatus.ACTIVE,
        )

        assert isinstance(session.started_at, datetime)
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.updated_at, datetime)

    def test_skip_question(self, agent):
        """测试跳过题目"""
        session_id = str(uuid4())
        session = InterviewSession(
            session_id=session_id,
            user_id="test_skip_user",
            company="美团",
            position="运维工程师",
            difficulty=DifficultyLevel.MEDIUM,
            total_questions=2,
            status=SessionStatus.ACTIVE,
            questions=[
                InterviewQuestion(
                    question_id="q_1",
                    question_text="题目1",
                    question_type="knowledge",
                    difficulty=DifficultyLevel.MEDIUM,
                    status=QuestionStatus.PENDING,
                ),
                InterviewQuestion(
                    question_id="q_2",
                    question_text="题目2",
                    question_type="knowledge",
                    difficulty=DifficultyLevel.MEDIUM,
                    status=QuestionStatus.PENDING,
                ),
            ],
        )
        agent._sessions[session_id] = session

        # 跳过第一题
        result = asyncio.run(agent.skip_question(session_id))

        assert result["type"] == "next_question"
        assert session.current_question_idx == 1
        assert session.questions[0].status == QuestionStatus.SKIPPED
        assert session.questions[0].score == 0

    def test_end_session_statistics(self, agent):
        """测试结束会话的统计计算"""
        session_id = str(uuid4())
        session = InterviewSession(
            session_id=session_id,
            user_id="test_stats_user",
            company="阿里",
            position="前端开发",
            difficulty=DifficultyLevel.EASY,
            total_questions=3,
            status=SessionStatus.ACTIVE,
            questions=[
                InterviewQuestion(
                    question_id="q_1",
                    question_text="题目1",
                    question_type="knowledge",
                    difficulty=DifficultyLevel.EASY,
                    status=QuestionStatus.SCORED,
                    score=80,
                    user_answer="回答1",
                    knowledge_points=["JavaScript"],
                    answered_at=datetime.now(),
                ),
                InterviewQuestion(
                    question_id="q_2",
                    question_text="题目2",
                    question_type="knowledge",
                    difficulty=DifficultyLevel.EASY,
                    status=QuestionStatus.SKIPPED,
                    score=0,
                ),
                InterviewQuestion(
                    question_id="q_3",
                    question_text="题目3",
                    question_type="knowledge",
                    difficulty=DifficultyLevel.EASY,
                    status=QuestionStatus.SCORED,
                    score=70,
                    user_answer="回答3",
                    knowledge_points=["CSS"],
                    answered_at=datetime.now(),
                ),
            ],
            current_question_idx=3,
        )
        agent._sessions[session_id] = session

        # 结束会话
        asyncio.run(agent._end_session(session))

        assert session.status == SessionStatus.COMPLETED
        assert session.ended_at is not None
        assert session.correct_count == 2  # 80 >= 70, 0 < 70, 70 >= 70
        assert session.calculate_average_score() == pytest.approx(50.0, rel=0.1)  # (80 + 0 + 70) / 3


class TestInterviewReport:
    """测试面试报告生成"""

    @pytest.fixture
    def agent(self):
        """创建 InterviewAgent"""
        llm = get_llm("deepseek", "chat")
        question_repo = get_question_repository()
        embedding_adapter = get_embedding_adapter()

        return InterviewAgent(
            llm=llm,
            question_repo=question_repo,
            embedding_adapter=embedding_adapter,
            scorer_agent=None,
        )

    def test_report_generation(self, agent):
        """测试报告生成"""
        session_id = str(uuid4())
        session = InterviewSession(
            session_id=session_id,
            user_id="test_report_user",
            company="腾讯",
            position="算法工程师",
            difficulty=DifficultyLevel.MEDIUM,
            total_questions=3,
            status=SessionStatus.COMPLETED,
            ended_at=datetime.now(),
            correct_count=1,  # 需要预先设置，因为 _end_session 未调用
            questions=[
                InterviewQuestion(
                    question_id="q_1",
                    question_text="题目1",
                    question_type="knowledge",
                    difficulty=DifficultyLevel.MEDIUM,
                    status=QuestionStatus.SCORED,
                    score=85,
                    user_answer="回答1",
                    knowledge_points=["算法"],
                    feedback="回答优秀",
                    mastery_before=0,
                    mastery_after=2,
                    answered_at=datetime.now(),
                ),
                InterviewQuestion(
                    question_id="q_2",
                    question_text="题目2",
                    question_type="knowledge",
                    difficulty=DifficultyLevel.MEDIUM,
                    status=QuestionStatus.SCORED,
                    score=55,
                    user_answer="回答2",
                    knowledge_points=["数据结构"],
                    feedback="需要改进",
                    mastery_before=1,
                    mastery_after=1,
                    answered_at=datetime.now(),
                ),
                InterviewQuestion(
                    question_id="q_3",
                    question_text="题目3",
                    question_type="knowledge",
                    difficulty=DifficultyLevel.MEDIUM,
                    status=QuestionStatus.SKIPPED,
                    score=0,
                ),
            ],
            current_question_idx=3,
        )
        agent._sessions[session_id] = session

        report = agent.get_report(session_id)

        assert report is not None
        assert report.session_id == session_id
        assert report.total_questions == 3
        # answered_questions 包含 SCORED 和 SKIPPED
        assert report.answered_questions == 3
        # correct_count: score >= 70 的题目数（从 session.correct_count 获取）
        assert report.correct_count == 1  # 85 >= 70
        assert report.average_score == pytest.approx(46.67, rel=0.1)  # (85 + 55 + 0) / 3
        assert "算法" in report.strengths  # score >= 80
        assert "数据结构" in report.weaknesses  # score < 60

        # 验证题目详情
        assert len(report.question_details) == 3


class TestMasteryTracking:
    """测试掌握度变化追踪"""

    def test_mastery_fields_in_interview_question(self):
        """测试 InterviewQuestion 的掌握度追踪字段"""
        question = InterviewQuestion(
            question_id="test_q",
            question_text="测试题目",
            question_type="knowledge",
            difficulty=DifficultyLevel.MEDIUM,
            knowledge_points=["测试"],
            status=QuestionStatus.PENDING,
            mastery_before=0,
            mastery_after=1,
        )

        assert question.mastery_before == 0
        assert question.mastery_after == 1

        # 测试序列化
        payload = question.to_payload()
        assert payload["mastery_before"] == 0
        assert payload["mastery_after"] == 1

        # 测试反序列化
        restored = InterviewQuestion.from_payload(payload)
        assert restored.mastery_before == 0
        assert restored.mastery_after == 1

    def test_mastery_before_set_on_preload(self):
        """测试预加载题目时设置 mastery_before"""
        # 模拟 Question 聚合根
        from app.domain.question.aggregates import Question, QuestionType

        mock_question = Question(
            question_id="test_q_id",
            question_text="测试题目文本",
            question_type=QuestionType.KNOWLEDGE,
            mastery_level=MasteryLevel.LEVEL_1,
            company="测试公司",
            position="测试岗位",
        )

        # 转换为 InterviewQuestion
        interview_q = InterviewQuestion(
            question_id=mock_question.question_id,
            question_text=mock_question.question_text,
            question_type=mock_question.question_type.value,
            difficulty=DifficultyLevel.MEDIUM,
            knowledge_points=mock_question.core_entities or [],
            status=QuestionStatus.PENDING,
            mastery_before=mock_question.mastery_level.value,
        )

        assert interview_q.mastery_before == 1


class TestFollowUpLimit:
    """测试追问次数上限逻辑"""

    @pytest.fixture
    def agent(self):
        """创建 InterviewAgent"""
        llm = get_llm("deepseek", "chat")
        question_repo = get_question_repository()
        embedding_adapter = get_embedding_adapter()

        return InterviewAgent(
            llm=llm,
            question_repo=question_repo,
            embedding_adapter=embedding_adapter,
            scorer_agent=None,
        )

    def test_max_follow_ups_constant(self, agent):
        """测试追问上限配置"""
        assert agent._max_follow_ups == 3

    def test_generate_follow_up_summary_low_score(self, agent):
        """测试低分情况下的总结性反馈"""
        question = InterviewQuestion(
            question_id="q_1",
            question_text="请解释微服务架构",
            question_type="knowledge",
            difficulty=DifficultyLevel.MEDIUM,
            knowledge_points=["微服务", "架构"],
            status=QuestionStatus.ANSWERING,
            follow_ups=["追问1", "追问2", "追问3"],
        )

        summary = agent._generate_follow_up_summary(question, 30)

        assert "掌握程度仍然较低" in summary
        assert "微服务" in summary or "架构" in summary
        assert "系统学习" in summary

    def test_generate_follow_up_summary_medium_score(self, agent):
        """测试中等分数情况下的总结性反馈"""
        question = InterviewQuestion(
            question_id="q_1",
            question_text="请解释数据库索引原理",
            question_type="knowledge",
            difficulty=DifficultyLevel.MEDIUM,
            knowledge_points=["数据库", "索引"],
            status=QuestionStatus.ANSWERING,
            follow_ups=["追问1", "追问2", "追问3"],
        )

        summary = agent._generate_follow_up_summary(question, 55)

        assert "理解还不够深入" in summary
        assert "数据库" in summary or "索引" in summary

    def test_generate_follow_up_summary_near_pass_score(self, agent):
        """测试接近达标分数情况下的总结性反馈"""
        question = InterviewQuestion(
            question_id="q_1",
            question_text="请解释 RESTful API 设计原则",
            question_type="knowledge",
            difficulty=DifficultyLevel.MEDIUM,
            knowledge_points=["RESTful", "API"],
            status=QuestionStatus.ANSWERING,
            follow_ups=["追问1", "追问2", "追问3"],
        )

        summary = agent._generate_follow_up_summary(question, 65)

        assert "接近要求" in summary
        assert "进一步巩固" in summary

    def test_follow_up_count_tracking(self):
        """测试追问次数追踪"""
        question = InterviewQuestion(
            question_id="q_1",
            question_text="测试题目",
            question_type="knowledge",
            difficulty=DifficultyLevel.MEDIUM,
            knowledge_points=["测试"],
            status=QuestionStatus.ANSWERING,
        )

        # 初始无追问
        assert len(question.follow_ups) == 0

        # 添加追问
        question.follow_ups.append("追问1")
        assert len(question.follow_ups) == 1

        question.follow_ups.append("追问2")
        question.follow_ups.append("追问3")
        assert len(question.follow_ups) == 3

        # 达到上限检查（使用默认配置值）
        assert len(question.follow_ups) >= 3

    @pytest.mark.asyncio
    async def test_follow_up_limit_enforced_in_session(self, agent):
        """测试面试会话中追问上限被强制执行"""
        # 创建模拟会话
        session_id = str(uuid4())
        session = InterviewSession(
            session_id=session_id,
            user_id="test_follow_up_limit",
            company="测试公司",
            position="测试岗位",
            difficulty=DifficultyLevel.MEDIUM,
            total_questions=2,
            status=SessionStatus.ACTIVE,
            questions=[
                InterviewQuestion(
                    question_id="q_1",
                    question_text="题目1",
                    question_type="knowledge",
                    difficulty=DifficultyLevel.MEDIUM,
                    knowledge_points=["测试"],
                    status=QuestionStatus.PENDING,
                ),
                InterviewQuestion(
                    question_id="q_2",
                    question_text="题目2",
                    question_type="knowledge",
                    difficulty=DifficultyLevel.MEDIUM,
                    knowledge_points=["测试"],
                    status=QuestionStatus.PENDING,
                ),
            ],
        )
        agent._sessions[session_id] = session

        # 模拟已有 3 次追问
        current_question = session.get_current_question()
        current_question.follow_ups = ["追问1", "追问2", "追问3"]
        current_question.status = QuestionStatus.ANSWERING

        # 提交回答
        chunks = []
        async for chunk in agent.process_answer_stream(
            session_id,
            "这是一个不太好的回答"
        ):
            data = json.loads(chunk)
            chunks.append(data)

        # 检查输出类型
        final_types = [c.get("type") for c in chunks]

        # 应该触发 force_next（因为已有 3 次追问，评分低于 70 时强制下一题）
        assert "force_next" in final_types

        # 验证 force_next 包含总结性反馈
        force_next_chunks = [c for c in chunks if c.get("type") == "force_next"]
        if force_next_chunks:
            force_next_data = force_next_chunks[0]
            assert "summary_feedback" in force_next_data
            assert force_next_data["follow_up_count"] == 4  # 3 次已有 + 本次追加

        # 验证会话状态已更新
        assert session.current_question_idx == 1
        assert current_question.status == QuestionStatus.SCORED