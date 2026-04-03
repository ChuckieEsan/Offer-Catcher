"""前端可复用组件"""

from gateways.components.question_card import (
    render_question_card,
    render_question_list,
    render_question_compact,
    get_default_handlers,
)

__all__ = [
    "render_question_card",
    "render_question_list",
    "render_question_compact",
    "get_default_handlers",
]