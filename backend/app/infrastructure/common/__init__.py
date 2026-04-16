"""基础设施层通用工具

包含日志、缓存、重试、断路器、图片处理、Prompt加载等通用组件。
"""

from app.infrastructure.common.logger import logger, setup_logger
from app.infrastructure.common.cache import cached, singleton
from app.infrastructure.common.retry import retry
from app.infrastructure.common.circuit_breaker import (
    circuit_breaker,
    CircuitBreakerOpenError,
    create_circuit_breaker,
    get_circuit_breaker,
    reset_circuit_breaker,
    list_circuit_breakers,
)
from app.infrastructure.common.image import (
    encode_image_to_base64,
    build_vision_message_content,
    get_image_mime_type,
)
from app.infrastructure.common.prompt import (
    load_prompt_template,
    build_prompt,
    load_prompt_content,
)

__all__ = [
    # logger
    "logger",
    "setup_logger",
    # cache
    "cached",
    "singleton",
    # retry
    "retry",
    # circuit_breaker
    "circuit_breaker",
    "CircuitBreakerOpenError",
    "create_circuit_breaker",
    "get_circuit_breaker",
    "reset_circuit_breaker",
    "list_circuit_breakers",
    # image
    "encode_image_to_base64",
    "build_vision_message_content",
    "get_image_mime_type",
    # prompt
    "load_prompt_template",
    "build_prompt",
    "load_prompt_content",
]