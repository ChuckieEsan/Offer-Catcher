"""工具模块

底层服务由 infrastructure/common 提供。
hasher 属于领域逻辑，由 domain/question/utils 提供。
此模块仅提供向后兼容的导入转发。
"""

from app.domain.question.utils import (
    generate_question_id,
    generate_short_id,
    verify_question_id,
)
from app.infrastructure.common.logger import logger, setup_logger
from app.infrastructure.common.cache import cached, singleton
from app.infrastructure.common.retry import retry
from app.infrastructure.common.circuit_breaker import (
    circuit_breaker,
    CircuitBreakerOpenError,
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
from app.utils.telemetry import (
    get_request_id,
    set_request_id,
    get_session_id,
    set_session_id,
    init_telemetry,
    get_tracer,
    get_meter,
    traced,
    traced_async,
    record_llm_tokens,
    record_vector_query,
    add_span_event,
    set_span_attribute,
)
from app.utils.warmup import warmup, warmup_async

__all__ = [
    # hasher
    "generate_question_id",
    "generate_short_id",
    "verify_question_id",
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
    # telemetry
    "get_request_id",
    "set_request_id",
    "get_session_id",
    "set_session_id",
    "init_telemetry",
    "get_tracer",
    "get_meter",
    "traced",
    "traced_async",
    "record_llm_tokens",
    "record_vector_query",
    "add_span_event",
    "set_span_attribute",
    # warmup
    "warmup",
    "warmup_async",
]