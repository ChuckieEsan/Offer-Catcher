"""Title Generator Prompts

使用 infrastructure.common.prompt.load_prompt_template 加载 prompt 文件。
"""

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent

__all__ = ["PROMPTS_DIR"]