"""FastAPI API 模块"""

from app.api.routes import chat, extract, score, questions, search, stats

__all__ = ["chat", "extract", "score", "questions", "search", "stats"]