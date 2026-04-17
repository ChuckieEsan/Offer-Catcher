"""恢复答案数据脚本

从备份文件中根据 ID 匹配恢复 question_answer 字段到当前 Qdrant 数据库。
"""

import pickle
from pathlib import Path
from qdrant_client import QdrantClient as QdrantSDKClient
from app.infrastructure.config.settings import get_settings


def restore_answers_by_id():
    """从备份根据 ID 恢复答案"""
    settings = get_settings()
    client = QdrantSDKClient(url=settings.qdrant_url)
    collection_name = settings.qdrant_collection

    # 读取备份
    backup_file = Path('/home/liuchenyu/Offer-Catcher/backups/qdrant_export_20260401_234153.pkl')
    with open(backup_file, 'rb') as f:
        backup_data = pickle.load(f)

    # 构建 ID -> answer 映射
    id_to_answer = {}
    for item in backup_data:
        payload = item.get('payload', {})
        point_id = item.get('id')
        qa = payload.get('question_answer')
        if point_id and qa:
            id_to_answer[point_id] = qa

    print(f"备份中有答案的记录: {len(id_to_answer)}")

    # 按 ID 更新答案
    restored = 0
    for point_id, answer in id_to_answer.items():
        client.set_payload(
            collection_name=collection_name,
            points=[point_id],
            payload={"question_answer": answer},
        )
        restored += 1
        if restored % 50 == 0:
            print(f"已恢复 {restored} 条答案...")

    print(f"\n恢复完成! 共恢复 {restored} 条答案")


if __name__ == "__main__":
    restore_answers_by_id()