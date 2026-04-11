"""pytest 配置文件

定义共享的 fixtures 和测试配置。
"""

import sys
from pathlib import Path

# 添加项目路径到 sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def pytest_configure(config):
    """pytest 配置钩子"""
    # 注册自定义标记
    config.addinivalue_line("markers", "slow: 标记慢速测试")
    config.addinivalue_line("markers", "integration: 标记集成测试")
    config.addinivalue_line("markers", "e2e: 标记端到端测试")
    config.addinivalue_line("markers", "performance: 标记性能测试")
    config.addinivalue_line("markers", "eval: 标记评估测试")