# API 接口文档

## 基础信息

- **Base URL**: `/api/v1`
- **认证**: Header `X-User-ID`（当前默认 `default_user`）
- **格式**: JSON

---

## 面经解析 API

### 提交解析任务

```http
POST /extract/submit
Content-Type: application/json
X-User-ID: {user_id}

# 文本解析
{
  "source_type": "text",
  "source_content": "字节跳动面经：\n1. 什么是RAG？\n2. 讲讲你的Agent项目"
}

# 图片解析
{
  "source_type": "image",
  "source_images": ["data:image/jpeg;base64,/9j/4AAQ..."]
}

Response 200:
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "任务已提交，请稍后查询结果"
}
```

### 获取任务列表

```http
GET /extract/tasks?status={status}&page={page}&page_size={page_size}
X-User-ID: {user_id}

Query Parameters:
- status: 可选，pending/processing/completed/failed/confirmed
- page: 页码，默认 1
- page_size: 每页数量，默认 20

Response 200:
{
  "items": [
    {
      "task_id": "xxx",
      "status": "completed",
      "source_type": "image",
      "company": "字节跳动",
      "position": "AI开发",
      "question_count": 12,
      "created_at": "2026-04-09T10:00:00",
      "updated_at": "2026-04-09T10:01:30"
    }
  ],
  "total": 5,
  "page": 1,
  "page_size": 20
}
```

### 获取任务详情

```http
GET /extract/tasks/{task_id}
X-User-ID: {user_id}

Response 200:
{
  "task_id": "xxx",
  "user_id": "default_user",
  "source_type": "image",
  "status": "completed",
  "created_at": "2026-04-09T10:00:00",
  "updated_at": "2026-04-09T10:01:30",
  "result": {
    "company": "字节跳动",
    "position": "AI Agent开发工程师",
    "questions": [
      {
        "question_id": "abc123",
        "question_text": "什么是RAG？",
        "question_type": "knowledge",
        "core_entities": ["RAG", "检索增强生成"]
      }
    ]
  }
}

Response 404:
{
  "detail": "任务不存在"
}
```

### 编辑解析结果

```http
PUT /extract/tasks/{task_id}
Content-Type: application/json
X-User-ID: {user_id}

{
  "company": "字节跳动",
  "position": "AI Agent开发工程师",
  "questions": [
    {
      "question_id": "abc123",
      "question_text": "什么是RAG？请详细说明",
      "question_type": "knowledge",
      "company": "字节跳动",
      "position": "AI Agent开发工程师",
      "core_entities": ["RAG"]
    }
  ]
}

Response 200:
{ /* 更新后的完整任务对象 */ }

Response 400:
{
  "detail": "仅可编辑已完成的任务"
}
```

### 确认入库

```http
POST /extract/tasks/{task_id}/confirm
X-User-ID: {user_id}

Response 200:
{
  "processed": 12,
  "async_tasks": 10,
  "question_ids": ["abc123", "def456", ...]
}

Response 400:
{
  "detail": "仅可确认已完成的任务"
}
```

### 删除任务

```http
DELETE /extract/tasks/{task_id}
X-User-ID: {user_id}

Response 200:
{
  "success": true
}
```

---

## 题目管理 API

### 获取题目列表

```http
GET /questions?company={company}&question_type={type}&mastery_level={level}&cluster_id={cluster_id}&keyword={keyword}&page={page}&page_size={page_size}

Query Parameters:
- company: 公司名称过滤
- question_type: 题目类型过滤 (knowledge/project/behavioral/scenario/algorithm)
- mastery_level: 熟练度过滤 (0/1/2)
- cluster_id: 聚类过滤
- keyword: 关键词搜索
- page: 页码
- page_size: 每页数量

Response 200:
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

### 获取单个题目

```http
GET /questions/{question_id}

Response 200:
{
  "question_id": "xxx",
  "question_text": "什么是RAG？",
  "company": "字节跳动",
  "position": "AI开发",
  "question_type": "knowledge",
  "mastery_level": 0,
  "core_entities": ["RAG"],
  "question_answer": "...",
  "cluster_ids": ["cluster_rag_retrieval"]
}
```

### 更新题目

```http
PUT /questions/{question_id}
Content-Type: application/json

{
  "question_text": "更新后的题目",
  "question_answer": "更新后的答案",
  "mastery_level": 1
}
```

### 删除题目

```http
DELETE /questions/{question_id}

Response 200:
{
  "success": true
}
```

### 重新生成答案

```http
POST /questions/{question_id}/regenerate?preview={true/false}

Query Parameters:
- preview: 是否仅预览，默认 true

Response 200:
{
  "question_answer": "新生成的答案..."
}
```

---

## 统计 API

### 总览统计

```http
GET /stats/overview

Response 200:
{
  "total_questions": 661,
  "total_companies": 15,
  "total_positions": 23,
  "by_type": {
    "knowledge": 400,
    "project": 150,
    "behavioral": 50,
    "scenario": 61
  },
  "by_mastery": {
    "0": 500,
    "1": 100,
    "2": 61
  },
  "has_answer": 400,
  "no_answer": 261
}
```

### 公司统计

```http
GET /stats/companies

Response 200:
[
  {
    "company": "字节跳动",
    "count": 204,
    "mastered": 30,
    "has_answer": 150
  },
  ...
]
```

### 聚类统计

```http
GET /stats/clusters

Response 200:
[
  {
    "cluster_id": "cluster_rag_retrieval",
    "count": 25
  },
  ...
]
```

---

## 对话 API

### 流式对话

```http
POST /chat/stream
Content-Type: application/json

{
  "message": "帮我搜索 RAG 相关的题目",
  "conversation_id": "conv-xxx",
  "user_id": "default_user"
}

Response: text/event-stream
data: {"type": "token", "content": "我"}
data: {"type": "token", "content": "找到"}
data: {"type": "update", "node": "react_loop", "content": "..."}
data: {"type": "final", "content": "..."}
```

### 获取对话列表

```http
GET /conversations?limit=50
X-User-ID: {user_id}

Response 200:
{
  "items": [
    {
      "id": "conv-xxx",
      "title": "RAG 相关题目",
      "created_at": "2026-04-09T10:00:00",
      "updated_at": "2026-04-09T10:30:00"
    }
  ],
  "total": 10
}
```

---

## 搜索 API

### 向量搜索

```http
POST /search
Content-Type: application/json

{
  "query": "RAG 检索增强",
  "company": "字节跳动",
  "k": 5
}

Response 200:
{
  "results": [
    {
      "question_id": "xxx",
      "question_text": "什么是RAG？",
      "score": 0.85
    }
  ]
}
```