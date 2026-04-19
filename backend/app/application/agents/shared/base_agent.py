"""Agent 基类 - 使用依赖注入

提供 Agent 的通用功能：
- Prompt 加载
- LLM 调用
- Structured Output
- 错误处理与重试

遵循 DDD 原则：
- LLM 通过构造函数注入（不直接创建）
- 便于测试时使用 Mock
"""

from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.infrastructure.common.prompt import build_prompt
from app.infrastructure.common.logger import logger
from app.infrastructure.common.retry import retry

T = TypeVar("T")


class BaseAgent(Generic[T]):
    """Agent 基类

    子类需要定义：
    - _prompt_filename: Prompt 文件名
    - _prompts_dir: Prompt 目录路径
    - _structured_output_schema: 结构化输出 Schema（可选）

    使用依赖注入：
    - llm: ChatOpenAI 实例（由 factory 注入）
    """

    _prompt_filename: str = ""
    _prompts_dir: Any = None
    _structured_output_schema: Optional[type] = None

    def __init__(
        self,
        llm: ChatOpenAI,
        prompts_dir: Any,
    ) -> None:
        """初始化 Agent

        Args:
            llm: LLM 实例（依赖注入）
            prompts_dir: Prompt 目录路径
        """
        self._llm = llm
        self._prompts_dir = prompts_dir
        self._structured_llm: Optional[ChatOpenAI] = None

    @property
    def llm(self) -> ChatOpenAI:
        """获取 LLM 实例"""
        return self._llm

    @property
    def structured_llm(self) -> Optional[ChatOpenAI]:
        """获取结构化输出 LLM（懒加载）"""
        if self._structured_llm is None and self._structured_output_schema:
            self._structured_llm = self._llm.with_structured_output(
                self._structured_output_schema
            )
        return self._structured_llm

    def _build_prompt(self, **kwargs) -> str:
        """构建 Prompt

        Args:
            **kwargs: Prompt 模板参数

        Returns:
            构建后的 Prompt
        """
        return build_prompt(
            self._prompt_filename,
            self._prompts_dir,
            **kwargs,
        )

    @retry(max_retries=3, delay=1.0)
    def invoke_llm(self, prompt: str) -> str:
        """调用 LLM（带重试）

        Args:
            prompt: 输入 Prompt

        Returns:
            LLM 响应文本
        """
        messages = [
            SystemMessage(content="你是一个专业的助手。"),
            HumanMessage(content=prompt),
        ]
        response = self._llm.invoke(messages)
        return response.content

    @retry(max_retries=3, delay=1.0)
    def invoke_structured(self, prompt: str) -> Optional[T]:
        """调用结构化输出 LLM（带重试）

        Args:
            prompt: 输入 Prompt

        Returns:
            结构化输出对象，失败返回 None
        """
        if not self.structured_llm:
            return None

        messages = [
            SystemMessage(content="你是一个专业的助手。"),
            HumanMessage(content=prompt),
        ]

        try:
            return self.structured_llm.invoke(messages)
        except Exception as e:
            logger.warning(f"Structured output failed: {e}")
            return None


__all__ = ["BaseAgent"]