"""DeepEval 配置模块

配置 DeepEval 使用项目已有的 DeepSeek API 作为 Judge。
"""

import os
from typing import Optional

from deepeval.models import DeepEvalBaseLLM


class DeepSeekJudgeModel(DeepEvalBaseLLM):
    """DeepSeek Judge 模型适配器

    用于 DeepEval 的自定义 Judge 模型实现。
    将 DeepSeek API 封装为 DeepEval 所需的格式。

    使用方法：
        model = DeepSeekJudgeModel()
        metric = GEval(model=model, ...)
    """

    def __init__(self, model: Optional[str] = None):
        from openai import OpenAI

        super().__init__(model=model or "deepseek-chat")

        self._model_name = model or "deepseek-chat"
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )

    def load_model(self):
        """加载模型（DeepEval 要求的方法）"""
        return self

    def generate(self, prompt: str, *args, **kwargs) -> str:
        """同步生成"""
        response = self.client.chat.completions.create(
            model=self._model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        return response.choices[0].message.content

    async def a_generate(self, prompt: str, *args, **kwargs) -> str:
        """异步生成"""
        from openai import AsyncOpenAI

        async_client = AsyncOpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )

        response = await async_client.chat.completions.create(
            model=self._model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        return response.choices[0].message.content

    def get_model_name(self) -> str:
        """获取模型名称"""
        return self._model_name


def get_deepeval_judge_model() -> DeepSeekJudgeModel:
    """获取 DeepEval Judge 模型实例

    Returns:
        DeepSeekJudgeModel 实例
    """
    return DeepSeekJudgeModel()


def setup_deepeval():
    """设置 DeepEval 环境

    在测试开始前调用，确保 DeepEval 正确配置。
    注意：DeepEval 3.x 需要在创建 Metric 时显式传入 model 参数。
    """
    # DeepEval 使用环境变量配置默认模型
    os.environ["DEEPEVAL_MODEL"] = os.getenv(
        "DEEPEVAL_MODEL",
        "deepseek-chat"
    )


__all__ = [
    "DeepSeekJudgeModel",
    "get_deepeval_judge_model",
    "setup_deepeval",
]