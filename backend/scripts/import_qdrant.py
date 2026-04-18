#!/usr/bin/env python3
"""Qdrant 数据库导入脚本

从 joblib 文件导入数据到 Qdrant 集合。
"""

import joblib
import argparse
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger


def import_collection(
    client: QdrantClient,
    collection_name: str,
    input_file: Path,
    batch_size: int = 100,
    with_vectors: bool = True,
) -> int:
    """导入数据到集合

    Args:
        client: Qdrant 客户端
        collection_name: 集合名称
        input_file: 输入文件路径
        batch_size: 每批导入数量
        with_vectors: 是否包含向量数据

    Returns:
        导入记录数
    """
    # 读取 JSON 文件
    points_data = joblib.load(input_file)

    if not points_data:
        logger.warning(f"文件为空: {input_file}")
        return 0

    total = len(points_data)
    logger.info(f"准备导入 {total} 条记录到 '{collection_name}'")

    # 批量导入
    imported = 0
    for i in range(0, total, batch_size):
        batch = points_data[i:i + batch_size]
        points = []

        for item in batch:
            point = PointStruct(
                id=item["id"],
                vector=item.get("vector") if with_vectors else None,
                payload=item.get("payload"),
            )
            points.append(point)

        client.upsert(
            collection_name=collection_name,
            points=points,
        )

        imported += len(batch)
        logger.info(f"已导入 {imported}/{total} 条记录")

    logger.info(f"导入完成: {imported} 条记录")
    return imported


def main():
    parser = argparse.ArgumentParser(description="导入数据到 Qdrant 集合")
    parser.add_argument(
        "input",
        type=str,
        help="输入 joblib 文件路径",
    )
    parser.add_argument(
        "-c", "--collection",
        type=str,
        default=None,
        help="集合名称 (默认: 从配置读取)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="每批导入数量 (默认: 100)",
    )
    parser.add_argument(
        "--no-vectors",
        action="store_true",
        help="不导入向量数据",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="导入前先删除并重建集合",
    )

    args = parser.parse_args()

    input_file = Path(args.input)
    if not input_file.exists():
        raise FileNotFoundError(f"文件不存在: {input_file}")

    settings = get_settings()
    collection_name = args.collection or settings.qdrant_collection

    # 连接 Qdrant
    client = QdrantClient(url=settings.qdrant_url)
    logger.info(f"连接 Qdrant: {settings.qdrant_url}")

    # 如果需要重建集合
    if args.recreate:
        logger.warning(f"删除集合: {collection_name}")
        client.delete_collection(collection_name)
        # 重新创建（使用默认设置）
        from qdrant_client.models import Distance
        client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "size": settings.qdrant_vector_size,
                "distance": Distance.COSINE,
            },
        )
        logger.info(f"集合已重建: {collection_name}")

    try:
        count = import_collection(
            client=client,
            collection_name=collection_name,
            input_file=input_file,
            batch_size=args.batch_size,
            with_vectors=not args.no_vectors,
        )
        print(f"\n导入成功: {count} 条记录")
    except Exception as e:
        logger.error(f"导入失败: {e}")
        raise


if __name__ == "__main__":
    main()