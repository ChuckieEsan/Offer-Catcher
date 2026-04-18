"""启动模块"""

from app.infrastructure.bootstrap.warmup import warmup, warmup_async

__all__ = ["warmup", "warmup_async"]