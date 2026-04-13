# 异步面经解析系统设计文档

## 概述

异步面经解析系统将原有的同步阻塞式解析改造为异步任务模式，提升用户体验和系统稳定性。

## 问题背景

原有同步模式：
```
用户上传 → 等待 OCR + LLM 解析 (30-60s) → 返回结果 → 用户确认 → 入库
```

问题：
1. 前端长时间等待，容易超时
2. 用户无法中途离开
3. 无法批量提交多个任务
4. 无法查看历史解析任务

## 解决方案

异步任务模式：
```
用户上传 → 返回 task_id → Worker 异步解析 → 用户轮询/查看 → 编辑/入库
```

## 架构设计

```
┌───────────────────────────────────────────────────────────────┐
│                         前端                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │ 提交任务  │  │ 任务列表  │  │ 任务详情  │  │ 确认入库  │     │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘     │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│                       FastAPI 路由                             │
│  POST /extract/submit  GET /extract/tasks  PUT /extract/{id}  │
└───────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│    PostgreSQL     │ │     RabbitMQ      │ │      Redis        │
│  (任务持久化)      │ │   (可选通知)       │ │    (缓存)         │
│  - task_id        │ │                   │ │                   │
│  - status         │ │                   │ │                   │
│  - result (JSONB) │ │                   │ │                   │
│  - images (gzip)  │ │                   │ │                   │
└───────────────────┘ └───────────────────┘ └───────────────────┘
          │
          ▼
┌───────────────────────────────────────────────────────────────┐
│                     Extract Worker                             │
│  1. 轮询 pending 任务                                          │
│  2. 调用 Vision Extractor 解析                                 │
│  3. 更新任务状态和结果                                          │
└───────────────────────────────────────────────────────────────┘
```

## 数据模型

### ExtractTask

```python
class ExtractTask(BaseModel):
    task_id: str                    # 任务 ID (UUID)
    user_id: str                    # 用户 ID
    
    # 输入
    source_type: str                # image / text
    source_content: Optional[str]   # 文本内容
    source_images_gz: Optional[str] # 图片 Base64 (gzip 压缩)
    
    # 状态
    status: str                     # pending/processing/completed/failed/confirmed
    error_message: Optional[str]    # 错误信息
    created_at: datetime
    updated_at: datetime
    
    # 解析结果
    result: Optional[ExtractedInterview]
```

### 状态流转

```
pending → processing → completed → confirmed
                  ↘ failed
```

## 图片存储策略

使用 gzip 压缩 Base64 数据：

```python
# 写入时压缩
import gzip
import json

images_json = json.dumps(base64_images)
compressed = gzip.compress(images_json.encode())

# 存储到 PostgreSQL BYTEA 字段

# 读取时解压
decompressed = gzip.decompress(source_images_gz).decode()
images = json.loads(decompressed)
```

## API 设计

### 提交任务

```http
POST /extract/submit
Content-Type: application/json
X-User-ID: user123

{
  "source_type": "image",
  "source_images": ["data:image/jpeg;base64,/9j/4AAQ..."]
}

Response:
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "任务已提交，请稍后查询结果"
}
```

### 查询任务列表

```http
GET /extract/tasks?status=completed&page=1&page_size=20
X-User-ID: user123

Response:
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

### 查询任务详情

```http
GET /extract/tasks/{task_id}
X-User-ID: user123

Response:
{
  "task_id": "xxx",
  "status": "completed",
  "source_type": "image",
  "result": {
    "company": "字节跳动",
    "position": "AI开发",
    "questions": [...]
  }
}
```

### 编辑解析结果

```http
PUT /extract/tasks/{task_id}
X-User-ID: user123

{
  "company": "字节跳动",
  "position": "AI Agent开发工程师",
  "questions": [...]
}
```

### 确认入库

```http
POST /extract/tasks/{task_id}/confirm
X-User-ID: user123

Response:
{
  "processed": 12,
  "async_tasks": 10,
  "question_ids": [...]
}
```

## 前端实现

### 任务列表页

- 分页展示所有任务
- 支持状态筛选
- 自动刷新进行中的任务（3秒轮询）
- 点击查看详情

### 任务详情页

- 显示解析结果（公司、岗位、题目列表）
- 支持编辑题目（修改/删除）
- 确认入库按钮

## Worker 实现

```python
async def process_extract_task(task_id: str) -> bool:
    # 1. 获取任务
    task = pg.get_extract_task(task_id)
    
    # 2. 更新状态
    pg.update_extract_task_status(task_id, "processing")
    
    # 3. 执行解析
    if task.source_type == "text":
        result = extractor.extract(task.source_content)
    else:
        images = decompress_images(task.source_images_gz)
        result = extractor.extract(images, use_ocr=True)
    
    # 4. 更新结果
    pg.update_extract_task_result(task_id, result)
```

## 错误处理

| 错误场景 | 处理方式 |
|---------|---------|
| OCR 失败 | 更新状态为 failed，记录 error_message |
| LLM 解析失败 | 更新状态为 failed，记录 error_message |
| Worker 崩溃 | 任务保持 processing 状态，重启后继续 |

## 监控与告警

建议添加：
- 任务积压监控（pending 数量）
- 任务失败率监控
- 平均解析时间监控