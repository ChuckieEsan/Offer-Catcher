"""预热模块

在项目启动时初始化所有核心组件，避免冷启动延迟。

使用方式：
    # 在 Streamlit 入口处调用
    from app.utils.warmup import warmup
    warmup()
"""

from app.utils.logger import logger


def warmup() -> None:
    """预热所有核心组件

    初始化以下组件：
    1. OpenTelemetry（如果启用）
    2. LLM 实例
    3. ReAct Agent
    4. Chat System Prompt
    5. Embedding Tool
    6. Qdrant Manager
    7. Workflow
    8. Chat Agent
    9. Vision Extractor
    10. Scorer Agent
    11. Router Agent
    """
    logger.info("Starting warmup...")

    # 1. OpenTelemetry
    try:
        from app.config.settings import get_settings
        settings = get_settings()
        if getattr(settings, 'telemetry_enabled', False):
            from app.utils.telemetry import init_telemetry
            init_telemetry()
            logger.info("[Warmup] OpenTelemetry initialized")
    except Exception as e:
        logger.warning(f"[Warmup] OpenTelemetry init failed: {e}")

    # 2. LLM 实例
    try:
        from app.llm import get_llm
        get_llm("dashscope", "chat")
        logger.info("[Warmup] LLM instance created")
    except Exception as e:
        logger.warning(f"[Warmup] LLM init failed: {e}")

    # 3. ReAct Agent & Chat Prompt（核心）
    try:
        from app.agents.graph.nodes import _get_react_agent, _get_chat_system_prompt
        _get_react_agent()
        _get_chat_system_prompt()
        logger.info("[Warmup] ReAct Agent initialized")
    except Exception as e:
        logger.warning(f"[Warmup] ReAct Agent init failed: {e}")

    # 5. Embedding Tool
    try:
        from app.tools.embedding_tool import get_embedding_tool
        get_embedding_tool()
        logger.info("[Warmup] Embedding tool initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Embedding tool init failed: {e}")

    # 6. Qdrant Manager
    try:
        from app.db.qdrant_client import get_qdrant_manager
        get_qdrant_manager()
        logger.info("[Warmup] Qdrant manager initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Qdrant init failed: {e}")

    # 7. Workflow
    try:
        from app.agents.graph.workflow import get_workflow
        get_workflow()
        logger.info("[Warmup] Workflow initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Workflow init failed: {e}")

    # 8. Chat Agent
    try:
        from app.agents.chat_agent import get_chat_agent
        get_chat_agent()
        logger.info("[Warmup] Chat Agent initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Chat Agent init failed: {e}")

    # 9. Vision Extractor
    try:
        from app.agents.vision_extractor import get_vision_extractor
        get_vision_extractor()
        logger.info("[Warmup] Vision Extractor initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Vision Extractor init failed: {e}")

    # 10. Scorer Agent
    try:
        from app.agents.scorer import get_scorer_agent
        get_scorer_agent()
        logger.info("[Warmup] Scorer Agent initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Scorer Agent init failed: {e}")

    # 11. Router Agent
    try:
        from app.agents.router import get_router_agent
        get_router_agent()
        logger.info("[Warmup] Router Agent initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Router Agent init failed: {e}")

    logger.info("Warmup completed!")


async def warmup_async() -> None:
    """异步预热（可选，用于异步启动场景）"""
    import asyncio
    await asyncio.get_event_loop().run_in_executor(None, warmup)


__all__ = ["warmup", "warmup_async"]