-- Migration: Add memory enhancement fields to session_summaries
-- Date: 2026-04-22
-- Description: 为 session_summaries 表添加 importance_score, topics, memory_layer 等新字段
--              支持记忆重要性评级、话题标签、STM/LTM 分层存储

-- 1. 添加重要性分数字段
ALTER TABLE session_summaries
ADD COLUMN IF NOT EXISTS importance_score FLOAT DEFAULT 0.5;

-- 2. 添加话题标签字段（数组类型）
ALTER TABLE session_summaries
ADD COLUMN IF NOT EXISTS topics TEXT[] DEFAULT '{}';

-- 3. 添加记忆层级字段
ALTER TABLE session_summaries
ADD COLUMN IF NOT EXISTS memory_layer VARCHAR(20) DEFAULT 'short_term';

-- 4. 添加访问计数字段（Phase 5: STM → LTM 升级判断）
ALTER TABLE session_summaries
ADD COLUMN IF NOT EXISTS access_count INT DEFAULT 0;

-- 5. 添加反馈分数字段（Phase 5: 用户反馈机制）
ALTER TABLE session_summaries
ADD COLUMN IF NOT EXISTS feedback_score INT DEFAULT 0;

-- 6. 添加最后访问时间字段（Phase 5: 衰减判断）
ALTER TABLE session_summaries
ADD COLUMN IF NOT EXISTS last_accessed TIMESTAMP DEFAULT NULL;

-- 7. 添加衰减因子字段（Phase 5: 衰减机制）
ALTER TABLE session_summaries
ADD COLUMN IF NOT EXISTS decay_factor FLOAT DEFAULT 1.0;

-- 8. 添加标记删除字段（Phase 5: 衰减后标记删除）
ALTER TABLE session_summaries
ADD COLUMN IF NOT EXISTS marked_for_deletion BOOLEAN DEFAULT FALSE;

-- 9. 创建索引优化查询性能
CREATE INDEX IF NOT EXISTS idx_memory_user_layer
ON session_summaries(user_id, memory_layer);

CREATE INDEX IF NOT EXISTS idx_memory_topics
ON session_summaries USING GIN(topics);

CREATE INDEX IF NOT EXISTS idx_memory_importance
ON session_summaries(importance_score DESC);

CREATE INDEX IF NOT EXISTS idx_memory_decay
ON session_summaries(decay_factor ASC);

-- 10. 添加约束
ALTER TABLE session_summaries
ADD CONSTRAINT chk_importance_range
CHECK (importance_score >= 0.0 AND importance_score <= 1.0);

ALTER TABLE session_summaries
ADD CONSTRAINT chk_decay_range
CHECK (decay_factor >= 0.0 AND decay_factor <= 1.0);

ALTER TABLE session_summaries
ADD CONSTRAINT chk_memory_layer
CHECK (memory_layer IN ('short_term', 'long_term'));

-- 注释
COMMENT ON COLUMN session_summaries.importance_score IS '重要性分数（0.0-1.0），由 Memory Agent 自判断';
COMMENT ON COLUMN session_summaries.topics IS '话题标签列表，用于话题匹配检索';
COMMENT ON COLUMN session_summaries.memory_layer IS '记忆层级：short_term（STM）或 long_term（LTM）';
COMMENT ON COLUMN session_summaries.access_count IS '访问计数，用于 STM → LTM 升级判断';
COMMENT ON COLUMN session_summaries.feedback_score IS '反馈分数，用户正向/负向反馈累计';
COMMENT ON COLUMN session_summaries.last_accessed IS '最后访问时间，用于衰减判断';
COMMENT ON COLUMN session_summaries.decay_factor IS '衰减因子，STM 随时间衰减，LTM 不衰减';
COMMENT ON COLUMN session_summaries.marked_for_deletion IS '是否标记删除，衰减到阈值后标记';