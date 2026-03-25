"""Router Agent 模块

负责用户意图分类与路由，将用户输入分类为不同的意图并提取关键参数。
"""

import json
from pathlib import Path
from typing import Optional

from langchain_openai import ChatOpenAI

from app.config.settings import create_llm
from app.models.schemas import RoutingResult
from app.utils.logger import logger


# Prompt 模板路径
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "router.md"

# 公司名称标准化映射
COMPANY_ALIASES = {
    "鹅厂": "腾讯",
    "大厂": "阿里",
    "阿里": "阿里巴巴",
    "字节": "字节跳动",
    "百度": "百度",
    "腾讯": "腾讯",
    "美团": "美团",
    "京东": "京东",
    "拼多多": "拼多多",
    "滴滴": "滴滴",
    "快手": "快手",
    "小红书": "小红书",
    "b站": "哔哩哔哩",
    "bilibili": "哔哩哔哩",
}


def load_prompt() -> str:
    """加载 Prompt 模板"""
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    return ""


def normalize_company(company: str) -> str:
    """标准化公司名称

    Args:
        company: 公司名称（可能是别名）

    Returns:
        标准化后的公司名称
    """
    if not company:
        return company

    # 去除首尾空白
    company = company.strip()

    # 查表转换
    for alias, standard in COMPANY_ALIASES.items():
        if alias in company:
            return standard

    return company


class RouterAgent:
    """Router Agent - 意图分类与路由

    分析用户输入，确定意图类型并提取关键参数。
    """

    def __init__(self, provider: str = "dashscope") -> None:
        """初始化 Router Agent

        Args:
            provider: LLM Provider 名称，默认 dashscope
        """
        self.provider = provider
        self._llm = None
        self.prompt_template = load_prompt()
        logger.info(f"RouterAgent initialized with provider: {provider}")

    @property
    def llm(self) -> ChatOpenAI:
        """获取 LLM"""
        if self._llm is None:
            self._llm = create_llm(self.provider, "chat")
        return self._llm

    def _build_prompt(self, user_input: str) -> str:
        """构建 Prompt"""
        return self.prompt_template.format(user_input=user_input)

    def _parse_response(self, response: str) -> dict:
        """解析 LLM 响应"""
        try:
            # 尝试提取 JSON
            json_start = response.find("{")
            json_end = response.rfind("}") + 1

            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")

            json_str = response[json_start:json_end]
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.error(f"Response: {response}")
            raise

    def route(self, user_input: str) -> RoutingResult:
        """执行路由

        Args:
            user_input: 用户输入

        Returns:
            RoutingResult 包含意图和参数
        """
        logger.info(f"Routing input: {user_input[:50]}...")

        try:
            # 构建 Prompt
            prompt = self._build_prompt(user_input)

            # 调用 LLM
            response = self.llm.invoke(prompt)
            result = self._parse_response(response.content)

            # 标准化公司名称
            params = result.get("params", {})
            if "company" in params and params["company"]:
                params["company"] = normalize_company(params["company"])

            # 构建结果
            routing_result = RoutingResult(
                intent=result.get("intent", "query"),
                params=params,
                confidence=result.get("confidence", 1.0),
                original_text=user_input,
            )

            logger.info(f"Routing result: intent={routing_result.intent}, params={routing_result.params}")
            return routing_result

        except Exception as e:
            logger.error(f"Routing failed: {e}")
            # 返回默认结果
            return RoutingResult(
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