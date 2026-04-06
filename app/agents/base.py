"""Base Agent 模块

提供 Agent 的基类，包含 LLM 初始化、Structured Output、单例模式、重试机制等通用能力。
"""

from pathlib import Path
from typing import Any, Generic, Optional, TypeVar

from langchain_openai import ChatOpenAI

from app.config.settings import create_llm
from app.models.schemas import RouterResult, ScoreResult
from app.utils.logger import logger
from app.utils.agent import load_prompt
from app.utils.retry import retry

# 泛型：Agent 返回的结果类型
T = TypeVar("T")


class BaseAgent(Generic[T]):
    """Agent 基类

    提供以下通用能力：
    - LLM 初始化（支持多 Provider）
    - Structured Output 支持
    - Prompt 模板加载
    - 单例模式
    - 重试机制（默认启用）
    """

    # 子类必须覆盖
    _prompt_filename: str = ""
    _structured_output_schema: Optional[type] = None  # Pydantic 模型类

    def __init__(self, provider: str = "dashscope") -> None:
        """初始化 Agent

        Args:
            provider: LLM Provider 名称，默认 dashscope
        """
        self.provider = provider
        self._llm: Optional[ChatOpenAI] = None
        self._structured_llm: Optional[ChatOpenAI] = None
        self.prompt_template = load_prompt(self._prompt_filename) if self._prompt_filename else ""
        logger.info(f"{self.__class__.__name__} initialized with provider: {provider}")

    @property
    def llm(self) -> ChatOpenAI:
        """获取 LLM 实例（延迟加载）"""
        if self._llm is None:
            self._llm = create_llm(self.provider, "chat")
        return self._llm

    @property
    def structured_llm(self) -> Optional[ChatOpenAI]:
        """获取支持 structured output 的 LLM（延迟加载）

        Returns:
            带有 structured output 的 LLM，或不支持时返回 None
        """
        if self._structured_llm is None:
            if self._structured_output_schema is None:
                return None

            try:
                self._structured_llm = self.llm.with_structured_output(
                    self._structured_output_schema,
                    method="function_calling"
                )
            except Exception as e:
                logger.warning(f"Model does not support structured output: {e}")
                self._structured_llm = None

        return self._structured_llm

    def _build_prompt(self, **kwargs: Any) -> str:
        """构建 Prompt

        Args:
            **kwargs: 格式化参数

        Returns:
            格式化后的 Prompt
        """
        if not self.prompt_template:
            return ""

        # 过滤掉 None 值
        filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None}
        return self.prompt_template.format(**filtered_kwargs)

    @retry(max_retries=3, delay=1.0, backoff=2.0)
    def invoke_llm(self, prompt: str) -> str:
        """调用 LLM 获取文本响应（带重试）

        Args:
            prompt: 格式化后的 Prompt

        Returns:
            LLM 响应内容
        """
        response = self.llm.invoke(prompt)
        return response.content

    @retry(max_retries=3, delay=1.0, backoff=2.0)
    def invoke_structured(self, prompt: str) -> Optional[T]:
        """调用 LLM 获取结构化响应（带重试）

        优先使用 structured output，失败时返回 None。

        Args:
            prompt: 格式化后的 Prompt

        Returns:
            结构化结果，或 None（不支持时）
        """
        if self.structured_llm is None:
            return None

        return self.structured_llm.invoke(prompt)


# 全局单例存储（必须在 create_singleton 函数之前定义）
_singleton_instances: dict[str, BaseAgent] = {}


# 单例模式的辅助函数
def create_singleton(cls: type[BaseAgent], provider: str = "dashscope") -> BaseAgent:
    """创建或获取 Agent 单例

    Args:
        cls: Agent 类
        provider: LLM Provider

    Returns:
        Agent 实例
    """
    global _singleton_instances

    class_name = cls.__name__
    if class_name not in _singleton_instances:
        _singleton_instances[class_name] = cls(provider=provider)

    return _singleton_instances[class_name]


__all__ = ["BaseAgent", "create_singleton"]