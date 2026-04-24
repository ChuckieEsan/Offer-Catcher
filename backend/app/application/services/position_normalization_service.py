"""岗位归一化应用服务

实现 domain/question/services.py 中的 PositionNormalizer 接口。
提供岗位名称的完整生命周期管理：
1. aggregate(): 从题库聚合所有岗位名称及分布
2. normalize_batch(): 调用 LLM 批量生成标准化映射（结构化输出）
3. migrate(): 批量更新题库中的岗位字段
4. get_normalized(): 查询规范化名称（已知岗位）
5. normalize_and_cache(): 实时规范化新岗位并缓存（结构化输出）

映射文件存储于：config/position_mappings.json
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Optional

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.domain.question.services import PositionNormalizer
from app.infrastructure.config.settings import PROJECT_ROOT
from app.infrastructure.persistence.qdrant.client import get_qdrant_client
from app.infrastructure.adapters.llm_adapter import get_llm
from app.infrastructure.common.logger import logger
from app.application.agents.shared.base_agent import LLMType


# === 结构化输出模型 ===


class PositionMappingResult(BaseModel):
    """岗位归一化结果模型（批量）"""

    mappings: dict[str, str] = Field(
        description="岗位映射字典，键为原始名称，值为标准名称"
    )


class SinglePositionResult(BaseModel):
    """单个岗位归一化结果模型"""

    normalized: str = Field(description="归一化后的标准名称")


# === Prompt 定义（硬编码） ===

BATCH_NORMALIZATION_PROMPT = """你是一个岗位名称归一化专家。请将以下岗位名称归一化为最少数量的标准类别。

岗位列表（按出现次数排序）：
{position_list}

**预定义的标准岗位类别**（优先归入这些类别）：
- AI Agent开发：所有涉及 Agent、智能体、Agent应用开发的岗位
- AI开发：涉及 AI 应用开发、AI工程师、但不明确涉及 Agent 的岗位
- 后端开发：传统后端开发岗位（Java/Python/Go 等不涉及 AI）
- 大模型开发：涉及大模型、LLM 应用开发的岗位
- 大模型算法：涉及算法、算法工程师的岗位
- AI测试开发：涉及 AI 测试、评测的岗位
- 前端开发：前端相关岗位

**归一化原则**：
1. **大类优先**：尽可能归入预定义类别，而非创建新类别
2. **语义合并**：语义相近的岗位必须合并（如"AI Agent开发"和"AI Agent应用开发"都是"AI Agent开发"）
3. **去除修饰**：去掉"工程师"、"岗"、"应用"等冗余修饰词
4. **统一命名**：同一大类使用统一名称，不要保留变体

**必须合并的示例**：
- "AI Agent开发" / "AI Agent 应用开发" / "Java AI Agent开发" / "Agent开发" → 全部归为 "AI Agent开发"
- "AI开发工程师" / "AI应用开发" / "AI开发" → 全部归为 "AI开发"
- "大模型应用开发" / "大模型开发工程师" → 全部归为 "大模型开发"
- "后端开发工程师" / "Java后端开发" → 全部归为 "后端开发"

目标：输出结果中标准类别数量应尽可能少（不超过 8 个）。"""

SINGLE_NORMALIZATION_PROMPT = """你是一个岗位名称归一化专家。请将以下岗位名称归一化为标准类别。

岗位名称：{position}

**预定义的标准岗位类别**（优先归入这些类别）：
- AI Agent开发：所有涉及 Agent、智能体的岗位
- AI开发：涉及 AI 应用开发但不明确涉及 Agent 的岗位
- 后端开发：传统后端开发（Java/Python/Go 等不涉及 AI）
- 大模型开发：涉及大模型、LLM 应用开发的岗位
- 大模型算法：涉及算法的岗位
- AI测试开发：涉及 AI 测试的岗位
- 前端开发：前端相关岗位

**归一化原则**：
1. 优先归入预定义类别，而非创建新类别
2. 去掉"工程师"、"岗"、"应用"等冗余修饰词
3. 如果涉及 Agent，统一归为"AI Agent开发"""


class PositionNormalizationService(PositionNormalizer):
    """岗位归一化应用服务

    实现 PositionNormalizer 接口。
    使用 LangChain 结构化输出确保 LLM 返回格式正确。

    设计原则：
    - 映射文件外置，便于人工干预
    - 幂等性：已归一化的岗位不重复处理
    - 结构化输出：避免手动解析 JSON
    """

    MAPPINGS_FILE = PROJECT_ROOT / "config" / "position_mappings.json"

    def __init__(
        self,
        llm: Optional[LLMType] = None,
    ) -> None:
        """初始化服务

        Args:
            llm: LLM 实例（支持依赖注入，默认使用 deepseek）
        """
        self._qdrant = get_qdrant_client()
        self._llm = llm or get_llm("deepseek", "chat")
        self._structured_llm_batch = self._llm.with_structured_output(PositionMappingResult)
        self._structured_llm_single = self._llm.with_structured_output(SinglePositionResult)
        self._mappings: dict[str, str] = {}
        self._load_mappings()

    def _load_mappings(self) -> None:
        """加载已有映射文件"""
        if self.MAPPINGS_FILE.exists():
            with open(self.MAPPINGS_FILE, encoding="utf-8") as f:
                self._mappings = json.load(f)
            logger.info(f"Loaded {len(self._mappings)} position mappings")

    def _save_mappings(self) -> None:
        """保存映射文件"""
        self.MAPPINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.MAPPINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._mappings, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(self._mappings)} mappings to {self.MAPPINGS_FILE}")

    def aggregate(self) -> dict[str, int]:
        """从题库聚合所有岗位名称及分布

        扫描 Qdrant 所有数据，统计各岗位名称的出现次数。

        Returns:
            {岗位名称: 数量} 字典，按数量降序
        """
        logger.info("Aggregating positions from Qdrant...")

        positions = Counter()
        offset: Optional[str] = None
        total_scanned = 0

        while True:
            records, next_offset = self._qdrant.scroll(limit=100, offset=offset)
            if not records:
                break

            for record in records:
                payload = record.payload
                if payload:
                    position = payload.get("position", "")
                    if position:
                        positions[position] += 1

            total_scanned += len(records)

            if next_offset is None:
                break
            offset = next_offset

        result = dict(positions.most_common())
        logger.info(f"Aggregated {len(result)} unique positions from {total_scanned} records")

        return result

    async def normalize_batch(self, positions: dict[str, int]) -> dict[str, str]:
        """调用 LLM 批量生成岗位名称标准化映射

        使用 LangChain 结构化输出，确保返回格式正确。

        Args:
            positions: {岗位名称: 数量} 字典

        Returns:
            {原始名称: 标准名称} 映射字典
        """
        if not positions:
            logger.warning("No positions to normalize")
            return {}

        position_list = json.dumps(list(positions.keys()), ensure_ascii=False)
        logger.info(f"Normalizing {len(positions)} positions with LLM (structured output)...")

        prompt = BATCH_NORMALIZATION_PROMPT.format(position_list=position_list)

        try:
            result: PositionMappingResult = self._structured_llm_batch.invoke(
                [HumanMessage(content=prompt)]
            )
            new_mappings = result.mappings
        except Exception as e:
            logger.error(f"Structured output failed: {e}")
            raise ValueError(f"LLM structured output failed: {e}")

        # 合并到已有映射
        self._mappings.update(new_mappings)
        self._save_mappings()

        logger.info(f"Generated {len(new_mappings)} new mappings")
        return new_mappings

    def migrate(self, mappings: Optional[dict[str, str]] = None) -> dict[str, int]:
        """批量更新题库中的岗位字段

        Args:
            mappings: 映射字典，默认使用已加载的映射

        Returns:
            {原始名称: 更新数量} 迁移统计
        """
        if mappings is None:
            mappings = self._mappings

        if not mappings:
            logger.warning("No mappings to migrate")
            return {}

        logger.info("Migrating positions in Qdrant...")
        migration_stats: dict[str, int] = {}

        for original, normalized in mappings.items():
            if original == normalized:
                continue

            # 查询该岗位的所有记录
            query_filter = self._qdrant.build_filter(position=original)
            offset: Optional[str] = None
            ids_to_update: list[str] = []

            while True:
                records, next_offset = self._qdrant.scroll(
                    limit=100,
                    offset=offset,
                    query_filter=query_filter,
                )
                if not records:
                    break

                ids_to_update.extend(str(r.id) for r in records)

                if next_offset is None:
                    break
                offset = next_offset

            if ids_to_update:
                # 批量更新 payload
                self._qdrant.set_payload(
                    ids=ids_to_update,
                    payload={"position": normalized},
                )
                migration_stats[original] = len(ids_to_update)
                logger.info(f"Migrated: {original} → {normalized} ({len(ids_to_update)} records)")

        logger.info(f"Migration completed: {len(migration_stats)} positions updated")
        return migration_stats

    def get_normalized(self, position: str) -> str:
        """获取岗位的规范化名称（已知岗位）

        Args:
            position: 原始岗位名称

        Returns:
            规范化后的名称
        """
        return self._mappings.get(position, position)

    async def normalize_and_cache(self, position: str) -> str:
        """规范化并缓存（入库时新岗位使用）

        使用 LangChain 结构化输出。

        Args:
            position: 原始岗位名称

        Returns:
            规范化后的名称
        """
        # 已知岗位直接返回
        if position in self._mappings:
            return self._mappings[position]

        # 实时调用 LLM 归一化单个岗位
        logger.info(f"Normalizing new position with LLM (structured output): {position}")

        prompt = SINGLE_NORMALIZATION_PROMPT.format(position=position)

        try:
            result: SinglePositionResult = self._structured_llm_single.invoke(
                [HumanMessage(content=prompt)]
            )
            normalized = result.normalized
        except Exception as e:
            logger.error(f"Structured output failed: {e}")
            # Fallback: 返回原值
            return position

        # 写入映射文件
        self._mappings[position] = normalized
        self._save_mappings()

        logger.info(f"Added mapping: {position} → {normalized}")
        return normalized

    async def run_pipeline(self) -> dict[str, int]:
        """执行完整归一化流程

        流程：聚合 → LLM归一化 → 迁移

        Returns:
            迁移统计
        """
        logger.info("Starting full position normalization pipeline...")

        # 1. 聚合
        positions = self.aggregate()

        # 2. LLM归一化（结构化输出）
        mappings = await self.normalize_batch(positions)

        # 3. 迁移
        stats = self.migrate(mappings)

        logger.info("Position normalization pipeline completed")
        return stats


# 单例获取函数
_position_normalization_service: Optional[PositionNormalizationService] = None


def get_position_normalization_service() -> PositionNormalizationService:
    """获取岗位归一化服务单例"""
    global _position_normalization_service
    if _position_normalization_service is None:
        _position_normalization_service = PositionNormalizationService()
    return _position_normalization_service


__all__ = [
    "PositionNormalizationService",
    "get_position_normalization_service",
    "PositionNormalizer",
]