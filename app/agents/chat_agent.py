"""Chat Agent - AI 面试助手

使用 LangChain create_agent 实现，支持工具调用：
- 向量检索 (Qdrant)
- Web 搜索 (Tavily)
- 图数据库 (Neo4j)
"""

from typing import Optional

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from app.config.settings import create_llm
from app.utils.logger import logger
from app.tools.search_question_tool import search_questions
from app.tools.web_search_tool import search_web
from app.tools.query_graph_tool import query_graph
from app.tools.vision_extractor_tool import extract_interview_questions
from app.skills import get_skills_prompt


# ==================== Chat Agent ====================

class ChatAgent:
    """AI 面试助手 Agent

    基于 LangChain create_agent，支持工具调用：
    - search_questions: 向量检索题目
    - search_web: Web 搜索
    - query_graph: 图数据库查询
    """

    def __init__(self, provider: str = "dashscope"):
        self.provider = provider
        self._agent = None
        self._tools: list = [
            extract_interview_questions,
            search_questions,
            search_web,
            query_graph,
        ]

    @property
    def agent(self):
        if self._agent is None:
            self._agent = self._create_agent()
        return self._agent

    def _create_agent(self):
        """创建 Agent"""
        llm = create_llm(self.provider, "chat")

        skills_prompt = get_skills_prompt()

        system_prompt = f"""你是一个 AI 面试助手，具有强大的意图识别能力。

你的能力：
1. 提取面经题目：当用户上传图片或分享面经文本时，调用 extract_interview_questions
2. 搜索题目：当用户提问技术问题时，调用 search_questions 或 search_web
3. 查询知识图谱：当用户询问知识点之间的关系时，调用 query_graph
4. 日常对话：回答面试相关问题，提供建议

意图识别规则：
- 用户上传图片/截图 → 必须调用 extract_interview_questions（source_type="image"）
- 用户粘贴面经文本 → 调用 extract_interview_questions（source_type="text"）
- 用户提问具体技术问题 → 调用 search_questions 或 search_web
- 用户问"X 和 Y 是什么关系" → 调用 query_graph

注意：
- 回答要专业、准确
- 如果不确定信息，说明不确定的原因
- 保持友好的对话风格
- 当调用工具时，告诉用户"正在分析..."

{skills_prompt}"""

        return create_agent(
            llm,
            self._tools,
            system_prompt=system_prompt,
        )

    def chat(self, message: str, history: Optional[list[BaseMessage]] = None) -> str:
        """处理用户消息

        Args:
            message: 用户消息
            history: 对话历史 (LangChain BaseMessage 列表)

        Returns:
            Agent 回复
        """
        logger.info(f"ChatAgent processing: {message[:50]}...")

        # 构建消息列表
        messages = history[-10:] if history else []
        messages.append(HumanMessage(content=message))

        try:
            result = self.agent.invoke({"messages": messages})
            response = result["messages"][-1].content
            logger.info(f"ChatAgent response: {response[:50]}...")
            return response
        except Exception as e:
            logger.error(f"ChatAgent error: {e}")
            return f"抱歉，我遇到了问题: {e}"

    def chat_streaming(self, message: str, history: Optional[list[BaseMessage]] = None):
        """流式处理用户消息

        Args:
            message: 用户消息
            history: 对话历史 (LangChain BaseMessage 列表)

        Yields:
            Agent 回复的片段
        """
        logger.info(f"ChatAgent streaming: {message[:50]}...")

        # 构建消息列表
        messages = history[-10:] if history else []
        messages.append(HumanMessage(content=message))

        try:
            for event in self.agent.stream(
                {"messages": messages},
                stream_mode="messages"
            ):
                if isinstance(event, tuple):
                    msg = event[0]
                else:
                    msg = event

                if isinstance(msg, AIMessage) and msg.content:
                    yield msg.content
        except Exception as e:
            logger.error(f"ChatAgent streaming error: {e}")
            yield f"抱歉，我遇到了问题: {e}"


# 全局单例
_chat_agent: Optional[ChatAgent] = None


def get_chat_agent(provider: str = "dashscope") -> ChatAgent:
    """获取 Chat Agent 单例"""
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = ChatAgent(provider=provider)
    return _chat_agent


__all__ = ["ChatAgent", "get_chat_agent"]