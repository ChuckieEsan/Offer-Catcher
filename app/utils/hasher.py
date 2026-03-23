"""哈希工具模块

提供生成 Deterministic ID 的函数，确保 question_id 的幂等性。
"""

import hashlib
from typing import Optional


def generate_question_id(company: str, question_text: str) -> str:
    """生成题目唯一标识 ID

    使用 MD5 哈希算法，基于公司名称和题目文本生成唯一标识。
    同一道题无论入库多少次，生成的 ID 保持一致（幂等性）。

    Args:
        company: 公司名称
        question_text: 题目文本内容

    Returns:
        32 位 MD5 哈希字符串

    Example:
        >>> generate_question_id("字节跳动", "什么是 RAG？")
        'a1b2c3d4e5f6...'

    Note:
        - 输入字符串会自动去除首尾空白
        - 拼接时使用 "|" 分隔符，避免哈希冲突
    """
    # 标准化输入
    company_normalized = company.strip()
    question_normalized = question_text.strip()

    # 拼接字符串（使用分隔符避免边界情况冲突）
    combined = f"{company_normalized}|{question_normalized}"

    # 生成 MD5 哈希
    md5_hash = hashlib.md5(combined.encode("utf-8"))

    return md5_hash.hexdigest()


def generate_short_id(company: str, question_text: str, length: int = 8) -> str:
    """生成短标识 ID

    生成指定长度的短标识，用于日志或展示场景。

    Args:
        company: 公司名称
        question_text: 题目文本内容
        length: 标识长度（默认 8 位）

    Returns:
        短标识字符串

    Example:
        >>> generate_short_id("字节跳动", "什么是 RAG？")
        'a1b2c3d4'
    """
    full_id = generate_question_id(company, question_text)
    return full_id[:length]


def verify_question_id(
    company: str, question_text: str, expected_id: str
) -> bool:
    """验证题目 ID 是否匹配

    Args:
        company: 公司名称
        question_text: 题目文本内容
        expected_id: 期望的题目 ID

    Returns:
        是否匹配
    """
    actual_id = generate_question_id(company, question_text)
    return actual_id == expected_id