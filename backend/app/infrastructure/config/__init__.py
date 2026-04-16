"""基础设施层配置

包含数据库配置等。
"""

from app.infrastructure.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]