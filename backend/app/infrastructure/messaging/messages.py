"""RabbitMQ 消息结构定义

定义在主系统和异步 Worker 之间传递任务上下文的消息模型。
作为 Infrastructure 层组件，纯技术实现。
"""

from pydantic import BaseModel, Field


class MQTaskMessage(BaseModel):
    """RabbitMQ 任务消息模型

    用于在主系统和异步 Worker 之间传递任务上下文。
    """

    question_id: str = Field(description="题目唯一标识")
    question_text: str = Field(description="题目文本")
    company: str = Field(description="公司名称")
    position: str = Field(description="岗位名称")
    core_entities: list[str] = Field(default_factory=list, description="知识点实体列表")


__all__ = [
    "MQTaskMessage",
]