"""预热模块

在项目启动时初始化所有核心组件，避免冷启动延迟。

使用方式：
    # 在 FastAPI lifespan 中调用
    from app.utils.warmup import warmup
    warmup()
"""

from app.utils.logger import logger


def warmup() -> None:
    """预热所有核心组件

    初始化以下组件（按依赖顺序）：
    1. Settings & OpenTelemetry
    2. 数据库连接：PostgreSQL, Redis, Qdrant
    3. Embedding Tool（模型加载）
    4. LLM 实例
    5. Agents：Router, Scorer, Vision Extractor, Title Generator, Answer Specialist
    6. Workflow & Chat Agent
    7. Pipelines：Ingestion, Retrieval
    8. Web Search Tool
    """
    logger.info("Starting warmup...")

    # ========== Tier 1: 核心基础设施 ==========

    # 1. Settings & OpenTelemetry
    try:
        from app.config.settings import get_settings
        settings = get_settings()
        if getattr(settings, 'telemetry_enabled', False):
            from app.utils.telemetry import init_telemetry
            init_telemetry()
            logger.info("[Warmup] OpenTelemetry initialized")
    except Exception as e:
        logger.warning(f"[Warmup] OpenTelemetry init failed: {e}")

    # 2. PostgreSQL Client
    try:
        from app.db.postgres_client import get_postgres_client
        get_postgres_client()
        logger.info("[Warmup] PostgreSQL client initialized")
    except Exception as e:
        logger.warning(f"[Warmup] PostgreSQL init failed: {e}")

    # 3. Redis Client
    try:
        from app.db.redis_client import get_redis_client
        get_redis_client()
        logger.info("[Warmup] Redis client initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Redis init failed: {e}")

    # 4. Qdrant Manager
    try:
        from app.db.qdrant_client import get_qdrant_manager
        get_qdrant_manager()
        logger.info("[Warmup] Qdrant manager initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Qdrant init failed: {e}")

    # 5. Embedding Tool（模型加载，耗时操作）
    try:
        from app.tools.embedding_tool import get_embedding_tool
        get_embedding_tool()
        logger.info("[Warmup] Embedding tool initialized (model loaded)")
    except Exception as e:
        logger.warning(f"[Warmup] Embedding tool init failed: {e}")

    # ========== Tier 2: LLM & Agents ==========

    # 6. LLM 实例
    try:
        from app.llm import get_llm
        get_llm("dashscope", "chat")
        logger.info("[Warmup] LLM instance created")
    except Exception as e:
        logger.warning(f"[Warmup] LLM init failed: {e}")

    # 7. Scorer Agent
    try:
        from app.agents.scorer import get_scorer_agent
        get_scorer_agent()
        logger.info("[Warmup] Scorer Agent initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Scorer Agent init failed: {e}")

    # 8. Vision Extractor
    try:
        from app.agents.vision_extractor import get_vision_extractor
        get_vision_extractor()
        logger.info("[Warmup] Vision Extractor initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Vision Extractor init failed: {e}")

    # 10. Title Generator Agent
    try:
        from app.agents.title_generator import get_title_generator_agent
        get_title_generator_agent()
        logger.info("[Warmup] Title Generator Agent initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Title Generator Agent init failed: {e}")

    # 11. Answer Specialist
    try:
        from app.agents.answer_specialist import get_answer_specialist
        get_answer_specialist()
        logger.info("[Warmup] Answer Specialist initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Answer Specialist init failed: {e}")

    # ========== Tier 3: Workflow & Pipelines ==========

    # 12. ReAct Agent
    try:
        from app.agents.graph.nodes import _get_react_agent
        _get_react_agent()
        logger.info("[Warmup] ReAct Agent initialized")
    except Exception as e:
        logger.warning(f"[Warmup] ReAct Agent init failed: {e}")

    # 13. Workflow
    try:
        from app.agents.graph.workflow import get_workflow
        get_workflow()
        logger.info("[Warmup] Workflow initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Workflow init failed: {e}")

    # 14. Chat Agent
    try:
        from app.agents.chat_agent import get_chat_agent
        get_chat_agent()
        logger.info("[Warmup] Chat Agent initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Chat Agent init failed: {e}")

    # 15. Ingestion Pipeline
    try:
        from app.pipelines.ingestion import get_ingestion_pipeline
        get_ingestion_pipeline()
        logger.info("[Warmup] Ingestion Pipeline initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Ingestion Pipeline init failed: {e}")

    # 16. Retrieval Pipeline
    try:
        from app.pipelines.retrieval import get_retrieval_pipeline
        get_retrieval_pipeline()
        logger.info("[Warmup] Retrieval Pipeline initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Retrieval Pipeline init failed: {e}")

    # 17. Web Search Tool
    try:
        from app.tools.web_search_tool import get_web_search_tool
        get_web_search_tool()
        logger.info("[Warmup] Web Search Tool initialized")
    except Exception as e:
        logger.warning(f"[Warmup] Web Search Tool init failed: {e}")

    logger.info("Warmup completed!")


async def warmup_async() -> None:
    """异步预热（可选，用于异步启动场景）"""
    import asyncio
    await asyncio.get_event_loop().run_in_executor(None, warmup)


__all__ = ["warmup", "warmup_async"]