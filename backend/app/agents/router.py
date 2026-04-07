"""Router Agent 模块

负责用户意图分类与路由，将用户输入分类为不同的意图并提取关键参数。
"""

from typing import Optional

from app.agents.base import BaseAgent
from app.models.schemas import RouterResult
from app.utils.logger import logger
from app.utils.agent import parse_json_response


class RouterAgent(BaseAgent[RouterResult]):
    """Router Agent - 意图分类与路由

    分析用户输入，确定意图类型并提取关键参数。
    """

    _prompt_filename = "router.md"
    _structured_output_schema = RouterResult

    def __init__(self, provider: str = "dashscope") -> None:
        super().__init__(provider)
        # 禁用 thinking 模式，避免与 structured output 冲突
        self._llm_kwargs = {"extra_body": {"enable_thinking": False}}

    def _parse_response_fallback(self, response: str) -> RouterResult:
        """手动解析 LLM 响应（降级方案）"""
        data = parse_json_response(
            response,
            required_fields=["intent"],
            default_values={
                "intent": "query",
                "params": {},
                "confidence": 1.0,
            },
        )

        # 手动构建 params
        params = {}
        if "company" in data:
            params["company"] = data["company"]
        if "position" in data:
            params["position"] = data["position"]
        if "question" in data:
            params["question"] = data["question"]

        return RouterResult(
            intent=data.get("intent", "query"),
            params=params,
            confidence=data.get("confidence", 1.0),
            original_text="",
        )

    def route(self, user_input: str) -> RouterResult:
        """执行路由

        Args:
            user_input: 用户输入

        Returns:
            RouterResult 包含意图和参数
        """
        logger.info(f"Routing input: {user_input[:50]}...")

        # 构建 Prompt
        prompt = self._build_prompt(user_input=user_input)

        # 优先尝试使用 structured output
        result = self.invoke_structured(prompt)
        if result is not None:
            logger.info(f"Routing result (structured): intent={result.intent}, params={result.params}")
            return result

        # 降级到手动解析
        try:
            response = self.invoke_llm(prompt)
            result = self._parse_response_fallback(response)
            result.original_text = user_input
            return result
        except Exception as e:
            logger.error(f"Routing failed: {e}")
            # 返回默认结果
            return RouterResult(
                intent="query",
                params={},
                confidence=0.0,
                original_text=user_input,
            )


# 全局单例
_router_agent: Optional[RouterAgent] = None


def get_router_agent(provider: str = "dashscope") -> RouterAgent:
    """获取 Router Agent 单例

    Args:
        provider: LLM Provider 名称

    Returns:
        RouterAgent 实例
    """
    global _router_agent
    if _router_agent is None:
        _router_agent = RouterAgent(provider=provider)
    return _router_agent