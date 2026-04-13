"""面试相关工具

为 AI 面试官 Agent 提供的工具函数。
"""

from typing import Optional, List
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.db.qdrant_client import get_qdrant_manager
from app.tools.embedding_tool import get_embedding_tool
from app.tools.reranker_tool import get_reranker_tool
from app.utils.logger import logger


# ==================== 输入模型 ====================

class EvaluateAnswerInput(BaseModel):
    """evaluate_answer 工具的输入参数"""
    question_id: str = Field(description="题目 ID")
    user_answer: str = Field(description="用户回答")
    session_id: Optional[str] = Field(default=None, description="会话 ID")


class GetNextQuestionInput(BaseModel):
    """get_next_question 工具的输入参数"""
    session_id: Optional[str] = Field(default=None, description="会话 ID")
    difficulty: Optional[str] = Field(default=None, description="难度偏好")
    knowledge_point: Optional[str] = Field(default=None, description="知识点过滤")
    company: Optional[str] = Field(default=None, description="公司过滤")
    position: Optional[str] = Field(default=None, description="岗位过滤")


# ==================== 工具实现 ====================

@tool
def get_next_question(
    company: Optional[str] = None,
    position: Optional[str] = None,
    difficulty: Optional[str] = None,
    knowledge_point: Optional[str] = None,
    user_id: Optional[str] = None,
) -> str:
    """获取下一道面试题。

    基于上下文智能推荐下一道面试题。
    优先选择用户未掌握的知识点（通过 mastery_level 判断）。

    Args:
        company: 公司名称（可选）
        position: 岗位名称（可选）
        difficulty: 难度偏好（easy/medium/hard，可选）
        knowledge_point: 知识点过滤（可选）
        user_id: 用户 ID（可选，用于获取学习进度）

    Returns:
        题目信息，包含 question_id, question_text, question_type, difficulty
    """
    qdrant = get_qdrant_manager()
    embedding_tool = get_embedding_tool()
    reranker_tool = get_reranker_tool()

    # 构建查询上下文
    query_parts = []
    if company:
        query_parts.append(f"公司：{company}")
    if position:
        query_parts.append(f"岗位：{position}")
    if knowledge_point:
        query_parts.append(f"知识点：{knowledge_point}")

    query_context = " | ".join(query_parts) if query_parts else "面试题"

    # 向量搜索
    query_vector = embedding_tool.embed_text(query_context)
    candidates = qdrant.search(query_vector, limit=15)

    if not candidates:
        return "未找到合适的面试题"

    # Rerank
    candidate_texts = [c.question_text for c in candidates]
    ranked_indices = reranker_tool.rerank(query_context, candidate_texts, top_k=5)

    # 优先推荐未掌握的题目（通过 mastery_level 判断）
    # mastery_level 存储在 Qdrant payload 中，而非记忆模块
    def score_question(idx_score):
        idx, _ = idx_score
        candidate = candidates[idx]
        # LEVEL_0 表示未掌握，提高优先级
        mastery = getattr(candidate, 'mastery_level', None)
        mastery_priority = 0 if mastery == 'LEVEL_0' else 1 if mastery == 'LEVEL_1' else 2
        return (mastery_priority, idx_score[1])

    ranked_indices = sorted(ranked_indices, key=score_question, reverse=True)

    # 返回最佳题目
    best_idx, score = ranked_indices[0]
    best_question = candidates[best_idx]

    result = f"""题目ID: {best_question.question_id}
题目: {best_question.question_text}
类型: {best_question.question_type}
难度: {difficulty or 'medium'}
知识点: {', '.join(best_question.core_entities) if best_question.core_entities else '综合'}
"""
    return result


@tool
def evaluate_answer(
    question_id: str,
    user_answer: str,
) -> str:
    """评估用户回答，返回分数和建议。

    对用户的回答进行评估，给出分数、优点、改进建议，以及是否需要追问。

    Args:
        question_id: 题目 ID
        user_answer: 用户的回答

    Returns:
        评估结果，包含 score, strengths, improvements, should_follow_up, follow_up_question
    """
    from app.agents.scorer import get_scorer_agent

    qdrant = get_qdrant_manager()

    # 获取题目信息
    question = qdrant.get_question(question_id)
    if not question:
        return f"未找到题目: {question_id}"

    # 调用 ScorerAgent 进行评估
    # 注意：这里是同步调用，实际使用时可能需要异步处理
    try:
        import asyncio
        scorer = get_scorer_agent()
        result = asyncio.run(scorer.score(question_id, user_answer))

        # 格式化输出
        output = f"""评分: {result.score}/100
掌握度: {result.mastery_level.name}

优点:
{chr(10).join(f'- {s}' for s in result.strengths) if result.strengths else '- 暂无'}

改进建议:
{chr(10).join(f'- {i}' for i in result.improvements) if result.improvements else '- 暂无'}

反馈: {result.feedback}

是否需要追问: {'是' if result.score < 70 else '否'}
"""
        return output

    except Exception as e:
        logger.error(f"Evaluate answer failed: {e}")
        return f"评估失败: {str(e)}"


@tool
def get_interview_style(company: str) -> str:
    """获取公司的面试风格。

    返回该公司的面试特点、常考知识点、面试风格等信息。

    Args:
        company: 公司名称

    Returns:
        面试风格描述
    """
    # 可以从知识图谱或缓存中获取
    # 这里提供一些常见公司的面试风格

    styles = {
        "字节跳动": """字节跳动面试风格：
- 注重算法和数据结构
- 追问深入，要求理解原理
- 考察系统设计能力
- 代码规范和工程实践
- 常考：分布式系统、高并发、缓存、消息队列""",

        "阿里巴巴": """阿里巴巴面试风格：
- 注重项目经验和业务理解
- 考察架构设计能力
- 重视技术深度和广度
- 常考：Java 并发、JVM、Spring、数据库优化""",

        "腾讯": """腾讯面试风格：
- 基础扎实，注重原理
- 考察网络协议、操作系统
- 游戏相关岗位考察图形学
- 常考：TCP/IP、HTTP、Linux、C++""",

        "美团": """美团面试风格：
- 注重业务场景和解决方案
- 考察系统设计和高可用
- 重视工程能力和实践经验
- 常考：分布式、数据库、缓存、消息队列""",

        "百度": """百度面试风格：
- 注重算法和数据结构
- 考察搜索、推荐相关技术
- 重视技术深度
- 常考：算法、机器学习、NLP""",
    }

    # 模糊匹配
    for key, style in styles.items():
        if key in company or company in key:
            return style

    # 默认风格
    return f"""{company}面试风格：
- 注重基础知识和原理
- 考察项目经验和解决问题的能力
- 可能涉及算法和系统设计"""


@tool
def generate_follow_up(
    question_text: str,
    user_answer: str,
    knowledge_point: Optional[str] = None,
) -> str:
    """生成追问问题。

    当用户回答不完整时，生成一个相关的追问问题。

    Args:
        question_text: 原题目
        user_answer: 用户的回答
        knowledge_point: 需要深入的知识点（可选）

    Returns:
        追问问题
    """
    # 使用 LLM 生成追问
    from app.llm import get_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = get_llm("deepseek", "chat")

    system_prompt = """你是一个专业的面试官。根据用户的回答，生成一个追问问题。
要求：
1. 追问应该针对用户回答中的不足或模糊之处
2. 问题应该引导用户深入思考
3. 不要直接给出答案
4. 问题要具体，不要过于宽泛"""

    user_prompt = f"""原题目：{question_text}

用户回答：{user_answer}

{f'请针对"{knowledge_point}"这个知识点进行追问。' if knowledge_point else '请生成一个追问问题。'}"""

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    return response.content


__all__ = [
    "get_next_question",
    "evaluate_answer",
    "get_interview_style",
    "generate_follow_up",
]