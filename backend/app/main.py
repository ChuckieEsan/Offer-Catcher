"""FastAPI 应用入口

Offer-Catcher API 服务。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, extract, score, questions, search, stats, conversations, interview, speech, favorites
from app.utils.logger import logger
from app.utils.warmup import warmup


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("Starting Offer-Catcher API...")

    # 预热核心组件（包含所有初始化逻辑）
    warmup()

    logger.info("Offer-Catcher API started")

    yield

    # 关闭时清理
    logger.info("Shutting down Offer-Catcher API...")


app = FastAPI(
    title="Offer-Catcher API",
    description="面试准备智能助手 API - 基于 Multi-Agent 架构与混合 RAG",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置（允许前端访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js 开发服务器
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(conversations.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(extract.router, prefix="/api/v1")
app.include_router(score.router, prefix="/api/v1")
app.include_router(questions.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")
app.include_router(interview.router, prefix="/api/v1")
app.include_router(speech.router, prefix="/api/v1")
app.include_router(favorites.router, prefix="/api/v1")


@app.get("/health")
async def health():
    """健康检查端点"""
    return {"status": "ok", "service": "offer-catcher-api"}


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Welcome to Offer-Catcher API",
        "docs": "/docs",
        "health": "/health"
    }


# 用于直接运行
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )