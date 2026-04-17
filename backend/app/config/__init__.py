"""配置管理模块（向后兼容导入转发）

配置已迁移至 infrastructure/config。
"""

from app.infrastructure.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]