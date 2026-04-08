"""OpenTelemetry 可观测性模块

提供全链路追踪和指标收集能力。

架构:
- Traces: OTLP → Jaeger (端口 4317)
- Metrics: Prometheus Exporter → 暴露 /metrics 端点 → Prometheus 抓取

装饰器风格与项目保持一致：@traced, @traced_async
"""

import time
import uuid
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, Union

from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
# Prometheus exporter - 暴露 HTTP 端点供 Prometheus 抓取
from opentelemetry.exporter.prometheus import PrometheusMetricReader

from app.config.settings import get_settings
from app.utils.logger import logger

T = TypeVar("T")

# ==================== Context Variables ====================

# Request ID 贯穿整个请求链路
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# Session ID 用于区分不同会话
_session_id_var: ContextVar[str] = ContextVar("session_id", default="")

# LLM 调用开始时间（用于计算 duration）
_llm_start_time_var: ContextVar[float] = ContextVar("llm_start_time", default=0.0)


def get_request_id() -> str:
    """获取当前请求 ID"""
    rid = _request_id_var.get()
    if not rid:
        rid = str(uuid.uuid4())[:8]
        _request_id_var.set(rid)
    return rid


def set_request_id(rid: Optional[str] = None) -> str:
    """设置请求 ID

    Args:
        rid: 可选的请求 ID，不传则自动生成

    Returns:
        设置的请求 ID
    """
    if rid is None:
        rid = str(uuid.uuid4())[:8]
    _request_id_var.set(rid)
    return rid


def get_session_id() -> str:
    """获取当前会话 ID"""
    return _session_id_var.get()


def set_session_id(sid: str) -> None:
    """设置会话 ID"""
    _session_id_var.set(sid)


# ==================== OpenTelemetry 初始化 ====================

_tracer: Optional[trace.Tracer] = None
_meter: Optional[metrics.Meter] = None

# ==================== Metrics ====================

# 工具调用指标
_tool_call_counter: Optional[metrics.Counter] = None
_tool_call_duration: Optional[metrics.Histogram] = None
_tool_call_errors: Optional[metrics.Counter] = None

# LLM Token 指标
_llm_token_input: Optional[metrics.Counter] = None
_llm_token_output: Optional[metrics.Counter] = None
_llm_call_duration: Optional[metrics.Histogram] = None
_llm_call_counter: Optional[metrics.Counter] = None

# 向量检索指标
_vector_query_duration: Optional[metrics.Histogram] = None
_vector_query_results: Optional[metrics.Histogram] = None


def init_telemetry(service_name: str = "offer-catcher") -> None:
    """初始化 OpenTelemetry

    Args:
        service_name: 服务名称
    """
    global _tracer, _meter
    global _tool_call_counter, _tool_call_duration, _tool_call_errors
    global _llm_token_input, _llm_token_output, _llm_call_duration, _llm_call_counter
    global _vector_query_duration, _vector_query_results

    settings = get_settings()

    # 检查是否启用 telemetry
    if not getattr(settings, 'telemetry_enabled', False):
        logger.info("OpenTelemetry is disabled, skipping initialization")
        return

    otlp_endpoint = getattr(settings, 'otlp_endpoint', 'http://localhost:4317')
    prometheus_port = getattr(settings, 'prometheus_port', 9464)

    # 创建资源
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.0.0",
    })

    # 初始化 Tracer (发送到 Jaeger)
    trace_provider = TracerProvider(resource=resource)
    otlp_trace_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    trace_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))
    trace.set_tracer_provider(trace_provider)
    _tracer = trace.get_tracer(service_name)

    # 初始化 Metrics (Prometheus Exporter - 暴露 HTTP 端点)
    # Prometheus 会抓取 http://localhost:9464/metrics
    prometheus_reader = PrometheusMetricReader(port=prometheus_port)
    metric_provider = MeterProvider(resource=resource, metric_readers=[prometheus_reader])
    metrics.set_meter_provider(metric_provider)
    _meter = metrics.get_meter(service_name)

    # 创建工具调用指标
    _tool_call_counter = _meter.create_counter(
        name="tool.calls.total",
        description="Total number of tool calls",
        unit="1"
    )
    _tool_call_duration = _meter.create_histogram(
        name="tool.calls.duration",
        description="Duration of tool calls in milliseconds",
        unit="ms"
    )
    _tool_call_errors = _meter.create_counter(
        name="tool.calls.errors",
        description="Total number of tool call errors",
        unit="1"
    )

    # 创建 LLM 指标
    _llm_token_input = _meter.create_counter(
        name="llm.tokens.input",
        description="Total input tokens consumed",
        unit="1"
    )
    _llm_token_output = _meter.create_counter(
        name="llm.tokens.output",
        description="Total output tokens consumed",
        unit="1"
    )
    _llm_call_duration = _meter.create_histogram(
        name="llm.calls.duration",
        description="Duration of LLM calls in milliseconds",
        unit="ms"
    )
    _llm_call_counter = _meter.create_counter(
        name="llm.calls.total",
        description="Total number of LLM calls",
        unit="1"
    )

    # 创建向量检索指标
    _vector_query_duration = _meter.create_histogram(
        name="vector.query.duration",
        description="Duration of vector queries in milliseconds",
        unit="ms"
    )
    _vector_query_results = _meter.create_histogram(
        name="vector.query.results",
        description="Number of results returned from vector query",
        unit="1"
    )

    logger.info(f"OpenTelemetry initialized: service={service_name}, traces={otlp_endpoint}, metrics=prometheus:{prometheus_port}")


def get_tracer() -> trace.Tracer:
    """获取 Tracer 实例

    如果 telemetry 未初始化，返回 no-op tracer。
    """
    if _tracer is None:
        settings = get_settings()
        if getattr(settings, 'telemetry_enabled', False):
            init_telemetry()
        else:
            # 返回 no-op tracer
            return trace.NoOpTracer()
    return _tracer


def get_meter() -> metrics.Meter:
    """获取 Meter 实例

    如果 telemetry 未初始化，返回 no-op meter。
    """
    if _meter is None:
        settings = get_settings()
        if getattr(settings, 'telemetry_enabled', False):
            init_telemetry()
        else:
            # 返回 no-op meter
            return metrics.NoOpMeter()
    return _meter


# ==================== 装饰器 ====================

def traced(name: Optional[str] = None):
    """同步函数追踪装饰器

    自动记录调用次数、时长、成功/失败状态。

    Example:
        @traced
        def search_questions(query: str) -> str:
            ...

        @traced("custom_name")
        def my_function():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        span_name = name or func.__name__

        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            tracer = get_tracer()
            rid = get_request_id()
            sid = get_session_id()

            with tracer.start_as_current_span(
                span_name,
                attributes={
                    "code.function": func.__name__,
                    "request.id": rid,
                    "session.id": sid,
                }
            ) as span:
                start_time = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    # 记录成功指标
                    if _tool_call_counter is not None:
                        _tool_call_counter.add(1, {"name": span_name, "status": "success"})
                        _tool_call_duration.record(duration_ms, {"name": span_name})

                    span.set_attribute("status", "success")
                    span.set_attribute("duration_ms", duration_ms)

                    logger.debug(f"[{rid}] {span_name} succeeded in {duration_ms:.2f}ms")
                    return result

                except Exception as e:
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    # 记录失败指标
                    if _tool_call_counter is not None:
                        _tool_call_counter.add(1, {"name": span_name, "status": "error"})
                        _tool_call_errors.add(1, {"name": span_name, "error_type": type(e).__name__})

                    span.set_attribute("status", "error")
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    span.record_exception(e)

                    logger.error(f"[{rid}] {span_name} failed after {duration_ms:.2f}ms: {e}")
                    raise

        return wrapper

    # 支持无括号调用: @traced
    if callable(name):
        func = name
        name = None
        return decorator(func)

    return decorator


def traced_async(name: Optional[str] = None):
    """异步函数追踪装饰器

    Example:
        @traced_async
        async def react_loop_node(state, config):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        span_name = name or func.__name__

        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            tracer = get_tracer()
            rid = get_request_id()
            sid = get_session_id()

            with tracer.start_as_current_span(
                span_name,
                attributes={
                    "code.function": func.__name__,
                    "request.id": rid,
                    "session.id": sid,
                }
            ) as span:
                start_time = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    if _tool_call_counter is not None:
                        _tool_call_counter.add(1, {"name": span_name, "status": "success"})
                        _tool_call_duration.record(duration_ms, {"name": span_name})

                    span.set_attribute("status", "success")
                    span.set_attribute("duration_ms", duration_ms)

                    logger.debug(f"[{rid}] {span_name} succeeded in {duration_ms:.2f}ms")
                    return result

                except Exception as e:
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    if _tool_call_counter is not None:
                        _tool_call_counter.add(1, {"name": span_name, "status": "error"})
                        _tool_call_errors.add(1, {"name": span_name, "error_type": type(e).__name__})

                    span.set_attribute("status", "error")
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    span.record_exception(e)

                    logger.error(f"[{rid}] {span_name} failed after {duration_ms:.2f}ms: {e}")
                    raise

        return wrapper

    # 支持无括号调用
    if callable(name):
        func = name
        name = None
        return decorator(func)

    return decorator


# ==================== 指标记录函数 ====================

def record_llm_tokens(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: float,
    call_type: str = "chat"
) -> None:
    """记录 LLM Token 消耗

    Args:
        provider: LLM 提供商 (dashscope, openai, etc.)
        model: 模型名称
        input_tokens: 输入 Token 数
        output_tokens: 输出 Token 数
        duration_ms: 调用时长（毫秒）
        call_type: 调用类型 (chat, vision, embedding)
    """
    if _llm_token_input is None:
        return

    attrs = {"provider": provider, "model": model, "call_type": call_type}

    _llm_token_input.add(input_tokens, attrs)
    _llm_token_output.add(output_tokens, attrs)
    _llm_call_duration.record(duration_ms, attrs)
    _llm_call_counter.add(1, attrs)

    # 设置当前 Span 属性
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("llm.provider", provider)
        span.set_attribute("llm.model", model)
        span.set_attribute("llm.input_tokens", input_tokens)
        span.set_attribute("llm.output_tokens", output_tokens)
        span.set_attribute("llm.duration_ms", duration_ms)

    logger.debug(
        f"[{get_request_id()}] LLM: provider={provider}, model={model}, "
        f"tokens={input_tokens}/{output_tokens}, duration={duration_ms:.2f}ms"
    )


def record_vector_query(duration_ms: float, results_count: int, collection: str = "questions") -> None:
    """记录向量检索指标

    Args:
        duration_ms: 查询时长（毫秒）
        results_count: 返回结果数量
        collection: 集合名称
    """
    if _vector_query_duration is None:
        return

    attrs = {"collection": collection}
    _vector_query_duration.record(duration_ms, attrs)
    _vector_query_results.record(results_count, attrs)

    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("vector.duration_ms", duration_ms)
        span.set_attribute("vector.results_count", results_count)
        span.set_attribute("vector.collection", collection)


# ==================== Span 工具函数 ====================

def add_span_event(name: str, attributes: Optional[dict] = None) -> None:
    """向当前 Span 添加事件"""
    span = trace.get_current_span()
    if span.is_recording():
        span.add_event(name, attributes or {})


def set_span_attribute(key: str, value: Any) -> None:
    """设置当前 Span 属性"""
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute(key, value)


__all__ = [
    # Context
    "get_request_id",
    "set_request_id",
    "get_session_id",
    "set_session_id",
    # Init
    "init_telemetry",
    "get_tracer",
    "get_meter",
    # Decorators
    "traced",
    "traced_async",
    # Recording
    "record_llm_tokens",
    "record_vector_query",
    # Span utils
    "add_span_event",
    "set_span_attribute",
]