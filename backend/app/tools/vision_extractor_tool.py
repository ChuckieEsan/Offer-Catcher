"""Vision Extractor 工具封装

将 VisionExtractor 封装为 LangChain Tool，供 Agent 调用。
"""

from langchain_core.tools import tool

from app.agents.vision_extractor import get_vision_extractor
from app.utils.logger import logger


@tool
def extract_interview_questions(
    source: str,
    source_type: str = "text",
) -> str:
    """从文本或图片中提取面经题目信息

    当用户上传面试经验图片、分享面经文本时自动调用此工具。

    Args:
        source: 输入内容（文本/图片路径）
        source_type: 输入类型 "text" | "image"

    Returns:
        提取的面经信息，包含公司、岗位、题目列表

    Note:
        图片输入会自动进行 OCR 识别，然后结构化提取。
    """
    try:
        extractor = get_vision_extractor()
        # 图片默认使用 OCR，文本直接处理
        use_ocr = (source_type == "image")
        result = extractor.extract(source, source_type, use_ocr=use_ocr)

        # 构建可读输出
        output_parts = [f"公司: {result.company}"]
        output_parts.append(f"岗位: {result.position}")
        output_parts.append(f"题目列表 ({len(result.questions)} 道):")

        type_emoji_map = {
            "knowledge": "[知识]",
            "project": "[项目]",
            "behavioral": "[行为]",
            "scenario": "[场景]",
            "algorithm": "[算法]",
        }

        for i, q in enumerate(result.questions, 1):
            type_label = type_emoji_map.get(q.question_type.value, "")
            output_parts.append(f"  {i}. {type_label} {q.question_text[:80]}")
            if q.core_entities:
                output_parts.append(f"     知识点: {', '.join(q.core_entities[:3])}")

        return "\n".join(output_parts)

    except Exception as e:
        logger.error(f"Vision extraction failed: {e}")
        return f"提取失败: {str(e)}"


__all__ = ["extract_interview_questions"]