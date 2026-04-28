"""执行数据库迁移脚本

添加 memory enhancement 字段到 session_summaries 表。
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.infrastructure.persistence.postgres.client import get_postgres_client
from app.infrastructure.common.logger import logger


def run_migration():
    """执行迁移"""
    # 从 backend 目录查找 migrations 文件
    # run_migration.py -> postgres -> persistence -> infrastructure -> app -> backend
    backend_dir = Path(__file__).parent.parent.parent.parent.parent
    migration_file = backend_dir / "migrations" / "001_add_memory_enhancement_fields.sql"

    if not migration_file.exists():
        logger.error(f"Migration file not found: {migration_file}")
        return False

    # 读取 SQL
    sql_content = migration_file.read_text()

    # 按语句逐个执行（处理多行语句）
    client = get_postgres_client()

    # 定义每个 ALTER TABLE 和 CREATE INDEX 作为单独语句
    statements = [
        # ALTER TABLE statements
        "ALTER TABLE session_summaries ADD COLUMN IF NOT EXISTS importance_score FLOAT DEFAULT 0.5",
        "ALTER TABLE session_summaries ADD COLUMN IF NOT EXISTS topics TEXT[] DEFAULT '{}'",
        "ALTER TABLE session_summaries ADD COLUMN IF NOT EXISTS memory_layer VARCHAR(20) DEFAULT 'short_term'",
        "ALTER TABLE session_summaries ADD COLUMN IF NOT EXISTS access_count INT DEFAULT 0",
        "ALTER TABLE session_summaries ADD COLUMN IF NOT EXISTS feedback_score INT DEFAULT 0",
        "ALTER TABLE session_summaries ADD COLUMN IF NOT EXISTS last_accessed TIMESTAMP DEFAULT NULL",
        "ALTER TABLE session_summaries ADD COLUMN IF NOT EXISTS decay_factor FLOAT DEFAULT 1.0",
        "ALTER TABLE session_summaries ADD COLUMN IF NOT EXISTS marked_for_deletion BOOLEAN DEFAULT FALSE",
        # CREATE INDEX statements
        "CREATE INDEX IF NOT EXISTS idx_memory_user_layer ON session_summaries(user_id, memory_layer)",
        "CREATE INDEX IF NOT EXISTS idx_memory_topics ON session_summaries USING GIN(topics)",
        "CREATE INDEX IF NOT EXISTS idx_memory_importance ON session_summaries(importance_score DESC)",
        "CREATE INDEX IF NOT EXISTS idx_memory_decay ON session_summaries(decay_factor ASC)",
        # ADD CONSTRAINT statements
        "ALTER TABLE session_summaries ADD CONSTRAINT chk_importance_range CHECK (importance_score >= 0.0 AND importance_score <= 1.0)",
        "ALTER TABLE session_summaries ADD CONSTRAINT chk_decay_range CHECK (decay_factor >= 0.0 AND decay_factor <= 1.0)",
        "ALTER TABLE session_summaries ADD CONSTRAINT chk_memory_layer CHECK (memory_layer IN ('short_term', 'long_term'))",
    ]

    try:
        with client.conn.cursor() as cur:
            for stmt in statements:
                if stmt:
                    try:
                        cur.execute(stmt)
                        logger.info(f"Executed: {stmt[:60]}...")
                    except Exception as e:
                        error_msg = str(e).lower()
                        # 如果字段/索引/约束已存在，跳过
                        if "already exists" in error_msg or "duplicate" in error_msg:
                            logger.warning(f"Skipped (already exists): {stmt[:60]}...")
                        else:
                            logger.error(f"Error: {stmt[:60]}... - {e}")
                            raise

        client.conn.commit()
        logger.info("Migration completed successfully")
        return True

    except Exception as e:
        client.conn.rollback()
        logger.error(f"Migration failed: {e}")
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)