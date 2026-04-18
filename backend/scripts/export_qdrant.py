#!/usr/bin/env python3
"""Qdrant 数据库导出脚本

导出指定集合的所有数据为 joblib 文件。
"""

import joblib
import argparse
from datetime import datetime
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Filter

from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger


def export_collection(
    client: QdrantClient,
    collection_name: str,
    output_file: Path,
    batch_size: int = 100,
) -> int:
    """导出集合数据

    Args:
        client: Qdrant 客户端
        collection_name: 集合名称
        output_file: 输出文件路径
        batch_size: 每批读取数量

    Returns:
        导出记录数
    """
    # 获取集合信息
    collection_info = client.get_collection(collection_name)
    total_points = collection_info.points_count

    if total_points == 0:
        logger.warning(f"集合 '{collection_name}' 为空")
        return 0

    logger.info(f"集合 '{collection_name}' 共有 {total_points} 条记录")

    # 滚动读取所有数据
    points_data = []
    offset = None

    while True:
        results, offset = client.scroll(
            collection_name=collection_name,
            limit=batch_size,
            offset=offset,
            with_vectors=True,
            with_payload=True,
        )

        for point in results:
            points_data.append({
                "id": point.id,
                "vector": point.vector,
                "payload": point.payload,
            })

        logger.info(f"已读取 {len(points_data)}/{total_points} 条记录")

        if offset is None:
            break

    # 写入文件
    output_file.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(points_data, output_file)

    logger.info(f"导出完成: {output_file} ({len(points_data)} 条记录)")
    return len(points_data)


def main():
    parser = argparse.ArgumentParser(description="导出 Qdrant 集合数据")
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="输出文件路径 (默认: backups/qdrant_export_xxx.pkl)",
    )
    parser.add_argument(
        "-c", "--collection",
        type=str,
        default=None,
        help="集合名称 (默认: 从配置读取)",
    )
    parser.add_argument(
        "--with-vectors",
        action="store_true",
        help="是否导出向量数据",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="每批读取数量 (默认: 100)",
    )

    args = parser.parse_args()

    settings = get_settings()
    collection_name = args.collection or settings.qdrant_collection

    # 生成默认输出文件名
    if args.output:
        output_file = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = Path(__file__).parent.parent / "backups" / f"qdrant_export_{timestamp}.pkl"

    # 连接 Qdrant
    client = QdrantClient(url=settings.qdrant_url)
    logger.info(f"连接 Qdrant: {settings.qdrant_url}")

    try:
        count = export_collection(
            client=client,
            collection_name=collection_name,
            output_file=output_file,
            batch_size=args.batch_size,
        )
        print(f"\n导出成功: {count} 条记录 -> {output_file}")
    except Exception as e:
        logger.error(f"导出失败: {e}")
        raise


if __name__ == "__main__":
    main()