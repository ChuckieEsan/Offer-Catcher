"""Chat Domain Services - 接口定义

定义 Chat Domain 的领域服务接口（Protocol）。
遵循依赖倒置原则：Domain 层只定义接口，Application 层实现。

接口列表：
- TitleGenerator: 会话标题生成器接口
"""

from typing import Protocol, List


class TitleGenerator(Protocol):
    """会话标题生成器接口

    由 TitleGeneratorAgent 实现，在 Application 层。
    """

    def generate_title(self, messages: List) -> str:
        """生成会话标题

        Args:
            messages: 对话消息列表

        Returns:
            生成的标题（不超过 20 个字符）
        """
        ...


__all__ = ["TitleGenerator"]