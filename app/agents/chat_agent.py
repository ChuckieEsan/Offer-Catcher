"""Chat Agent - AI 面试助手

使用 LangChain create_agent 实现，支持工具调用：
- 向量检索 (Qdrant)
- Web 搜索 (Tavily)
- 图数据库 (Neo4j)
"""

from typing import Optional, List

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from app.db.qdrant_client import get_qdrant_manager

from app.config.settings import create_llm
from app.utils.logger import logger
from app.tools.web_search import get_web_search_tool
from app.tools.vision_extractor_tool import extract_interview_questions
from app.skills import get_skills_prompt


# ==================== LangChain Tools ====================

@tool
def search_questions(query: str, company: str = None, position: str = None, k: int = 5) -> str:
    """搜索题目库中的相关面试题

    Args:
        query: 搜索关键词
        company: 公司名称（可选）
        position: 岗位名称（可选）
        k: 返回数量，默认 5

    Returns:
        搜索结果，以文本形式返回
    """

    from app.tools.embedding import get_embedding_tool

    # 将 query 转为向量
    embedding_tool = get_embedding_tool()
    query_vector = embedding_tool.embed_text(query)

    # 检索
    qdrant = get_qdrant_manager()
    results = qdrant.search(query_vector, limit=k)

    if company:
        results = [r for r in results if r.company == company]
    if position:
        results = [r for r in results if r.position == position]

    if not results:
        return "未找到相关题目"

    output = []
    for i, r in enumerate(results, 1):
        output.append(f"题目 {i}: {r.question_text[:100]}...")
        if r.question_answer:
            output.append(f"答案: {r.question_answer[:200]}...")
        output.append("---")

    return "\n".join(output)


@tool
def search_web(query: str, max_results: int = 3) -> str:
    """使用 Web 搜索获取最新信息

    Args:
        query: 搜索关键词
        max_results: 最大结果数，默认 3

    Returns:
        搜索结果，以文本形式返回
    """

    try:
        web_tool = get_web_search_tool(max_results=max_results)
        results = web_tool.search(query)

        if not results:
            return "未找到相关信息"

        output = []
        for r in results:
            output.append(f"标题: {r.title}")
            output.append(f"内容: {r.content[:300]}...")
            output.append("---")

        return "\n".join(output)
    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return f"搜索失败: {e}"


@tool
def query_graph(question: str) -> str:
    """查询图数据库，获取知识点之间的关系

    Args:
        question: 查询问题

    Returns:
        查询结果
    """
    from app.db.graph_client import get_graph_client

    try:
        graph_client = get_graph_client()

        # 提取关键词
        keywords = question.replace("关系", "").replace("?", "").replace("知识", "").split()

        # 如果有关键词，查询相关知识点
        if keywords and keywords[0]:
            keyword = keywords[0]
            # 使用 get_related_entities 获取相关知识点
            related = graph_client.get_related_entities(keyword, limit=5)

            if not related:
                # 如果没有相关知识点，尝试获取热门考点
                top_entities = graph_client.get_top_entities(limit=5)
                if not top_entities:
                    return "图数据库中暂无知识点数据"

                output = ["热门考点:"]
                for e in top_entities:
                    output.append(f"- {e.get('entity', e)}")
                return "\n".join(output)

            output = [f"与 '{keyword}' 相关的知识点:"]
            for e in related:
                output.append(f"- {e.get('related_entity', e.get('entity', e))}")
                count = e.get('co_occurrence_count', '')
                if count:
                    output.append(f"  共现次数: {count}")
            return "\n".join(output)
        else:
            # 没有关键词时，返回热门考点
            top_entities = graph_client.get_top_entities(limit=10)
            if not top_entities:
                return "图数据库中暂无知识点数据"

            output = ["热门考点 Top 10:"]
            for i, e in enumerate(top_entities, 1):
                entity = e.get('entity', e)
                count = e.get('count', '')
                output.append(f"{i}. {entity}" + (f" (考察次数: {count})" if count else ""))
            return "\n".join(output)

    except Exception as e:
        logger.error(f"Graph query failed: {e}")
        return f"图数据库查询失败: {e}"


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
        self._tools = [
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

    def chat(self, message: str, history: List[dict] = None, attachments: List[str] = None) -> str:
        """处理用户消息

        Args:
            message: 用户消息
            history: 对话历史
            attachments: 附件列表（Base64 编码的图片）

        Returns:
            Agent 回复
        """
        logger.info(f"ChatAgent processing: {message[:50]}...")

        messages = []
        if history:
            for msg in history[-10:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        # 如果有附件，构建多模态消息
        if attachments:
            content = [{"type": "text", "text": message}]
            for b64_img in attachments:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}
                })
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": message})

        try:
            result = self.agent.invoke({"messages": messages})
            response = result["messages"][-1].content
            logger.info(f"ChatAgent response: {response[:50]}...")
            return response
        except Exception as e:
            logger.error(f"ChatAgent error: {e}")
            return f"抱歉，我遇到了问题: {e}"

    def chat_streaming(self, message: str, history: List[dict] = None, attachments: List[str] = None):
        """流式处理用户消息

        Args:
            message: 用户消息
            history: 对话历史
            attachments: 附件列表（Base64 编码的图片）

        Yields:
            Agent 回复的片段
        """
        logger.info(f"ChatAgent streaming: {message[:50]}...")

        messages = []
        if history:
            for msg in history[-10:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        # 如果有附件，构建多模态消息
        if attachments:
            content = [{"type": "text", "text": message}]
            for b64_img in attachments:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}
                })
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": message})

        try:
            for event in self.agent.stream(
                {"messages": messages},
                stream_mode="messages"
            ):
                # event 是 (message, metadata) 元组
                if isinstance(event, tuple):
                    msg = event[0]
                else:
                    msg = event

                # 只处理 AI 的回复，不要处理用户消息
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