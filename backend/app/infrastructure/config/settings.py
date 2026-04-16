"""基础设施层配置

从应用层配置导入，保持配置统一。
"""

from app.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]