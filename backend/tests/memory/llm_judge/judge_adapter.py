"""Judge API 适配器 - 支持多模型作为 Judge

支持 OpenAI、Anthropic、DeepSeek 作为评测 Judge。
使用真实 API 调用，替代 mock 评估。
"""

import asyncio
import json
import os
from abc import ABC, abstractmethod
from typing import Any

from app.infrastructure.common.logger import logger


class JudgeAdapter(ABC):
    """Judge LLM 适配器基类

    所有 Judge 必须实现 evaluate 方法，
    返回结构化的 JSON 评估结果。
    """

    @abstractmethod
    async def evaluate(self, prompt: str) -> dict:
        """执行评估

        Args:
            prompt: 评估 Prompt（包含评估标准和输入信息）

        Returns:
            结构化 JSON 评估结果
        """
        pass

    @abstractmethod
    async def evaluate_batch(self, prompts: list[str]) -> list[dict]:
        """批量评估

        Args:
            prompts: 多个评估 Prompt

        Returns:
            多个评估结果
        """
        pass


class OpenAIJudgeAdapter(JudgeAdapter):
    """OpenAI Judge 适配器

    使用 GPT-4o-mini 作为默认 Judge，
    支持 JSON mode 输出。
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        api_key: str | None = None,
    ):
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
        )
        self.model = model
        self.temperature = temperature

    async def evaluate(self, prompt: str) -> dict:
        """执行评估"""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            result = json.loads(content)

            logger.debug(f"OpenAI Judge evaluation complete: {self.model}")
            return result

        except Exception as e:
            logger.error(f"OpenAI Judge evaluation failed: {e}")
            return {"error": str(e), "overall_score": 0}

    async def evaluate_batch(self, prompts: list[str]) -> list[dict]:
        """批量评估"""
        results = await asyncio.gather(
            *[self.evaluate(p) for p in prompts],
            return_exceptions=True,
        )

        # 处理异常
        processed_results = []
        for r in results:
            if isinstance(r, Exception):
                processed_results.append({"error": str(r), "overall_score": 0})
            else:
                processed_results.append(r)

        return processed_results


class AnthropicJudgeAdapter(JudgeAdapter):
    """Anthropic Judge 适配器

    使用 Claude Haiku 作为默认 Judge，
    需手动解析 JSON 输出。
    """

    def __init__(
        self,
        model: str = "claude-3-5-haiku-20241022",
        temperature: float = 0.0,
        api_key: str | None = None,
    ):
        from anthropic import AsyncAnthropic

        self.client = AsyncAnthropic(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY"),
        )
        self.model = model
        self.temperature = temperature

    async def evaluate(self, prompt: str) -> dict:
        """执行评估"""
        try:
            # 添加 JSON 输出要求
            enhanced_prompt = f"{prompt}\n\n请输出 JSON 格式的结果，不要包含其他内容。"

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                temperature=self.temperature,
                messages=[{"role": "user", "content": enhanced_prompt}],
            )

            content = response.content[0].text

            # 尝试解析 JSON
            # 处理可能的 markdown 包裹
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content.strip())

            logger.debug(f"Anthropic Judge evaluation complete: {self.model}")
            return result

        except Exception as e:
            logger.error(f"Anthropic Judge evaluation failed: {e}")
            return {"error": str(e), "overall_score": 0}

    async def evaluate_batch(self, prompts: list[str]) -> list[dict]:
        """批量评估"""
        results = await asyncio.gather(
            *[self.evaluate(p) for p in prompts],
            return_exceptions=True,
        )

        processed_results = []
        for r in results:
            if isinstance(r, Exception):
                processed_results.append({"error": str(r), "overall_score": 0})
            else:
                processed_results.append(r)

        return processed_results


class DeepSeekJudgeAdapter(JudgeAdapter):
    """DeepSeek Judge 适配器

    使用项目已有的 DeepSeek 配置，
    作为低成本 Judge 替代。
    """

    def __init__(
        self,
        model: str = "deepseek-chat",
        temperature: float = 0.0,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY"),
            base_url=base_url or os.getenv(
                "DEEPSEEK_BASE_URL",
                "https://api.deepseek.com",
            ),
        )
        self.model = model
        self.temperature = temperature

    async def evaluate(self, prompt: str) -> dict:
        """执行评估"""
        try:
            enhanced_prompt = f"{prompt}\n\n请输出 JSON 格式的结果，不要包含其他内容。"

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": enhanced_prompt}],
                temperature=self.temperature,
            )

            content = response.choices[0].message.content

            # 处理可能的 markdown 包裹
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content.strip())

            logger.debug(f"DeepSeek Judge evaluation complete: {self.model}")
            return result

        except Exception as e:
            logger.error(f"DeepSeek Judge evaluation failed: {e}")
            return {"error": str(e), "overall_score": 0}

    async def evaluate_batch(self, prompts: list[str]) -> list[dict]:
        """批量评估"""
        results = await asyncio.gather(
            *[self.evaluate(p) for p in prompts],
            return_exceptions=True,
        )

        processed_results = []
        for r in results:
            if isinstance(r, Exception):
                processed_results.append({"error": str(r), "overall_score": 0})
            else:
                processed_results.append(r)

        return processed_results


def get_judge_adapter(
    provider: str = "openai",
    model: str | None = None,
    temperature: float = 0.0,
    **kwargs,
) -> JudgeAdapter:
    """获取 Judge 适配器

    Args:
        provider: Judge 提供商（openai/anthropic/deepseek）
        model: 模型名称（可选，使用默认值）
        temperature: 温度参数（默认 0.0 确定性输出）
        **kwargs: 其他参数

    Returns:
        JudgeAdapter 实例
    """
    adapters = {
        "openai": OpenAIJudgeAdapter,
        "anthropic": AnthropicJudgeAdapter,
        "deepseek": DeepSeekJudgeAdapter,
    }

    adapter_class = adapters.get(provider, OpenAIJudgeAdapter)

    # 默认模型
    default_models = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-haiku-20241022",
        "deepseek": "deepseek-chat",
    }

    if model is None:
        model = default_models.get(provider, "gpt-4o-mini")

    return adapter_class(
        model=model,
        temperature=temperature,
        **kwargs,
    )


__all__ = [
    "JudgeAdapter",
    "OpenAIJudgeAdapter",
    "AnthropicJudgeAdapter",
    "DeepSeekJudgeAdapter",
    "get_judge_adapter",
]