# Claude Code 记忆系统详解

> 本文档系统性地解析 Claude Code 的记忆模块设计，涵盖架构、检索、写入、更新等核心机制。

---

## 目录

- [一、概述](#一概述)
- [二、记忆系统架构](#二记忆系统架构)
- [三、容量与限制](#三容量与限制)
- [四、记忆检索机制](#四记忆检索机制)
- [五、记忆写入机制](#五记忆写入机制)
- [六、记忆更新机制](#六记忆更新机制)
- [七、记忆管理功能](#七记忆管理功能)
- [八、记忆系统的优势](#八记忆系统的优势)
- [九、安全机制](#九安全机制)
- [十、与上下文压缩的关系](#十与上下文压缩的关系)
- [十一、总结](#十一总结)

---

## 一、概述

### 1.1 什么是记忆系统

Claude Code 的记忆系统是一个**多层次、智能的持久化记忆机制**，旨在帮助 AI 模型在跨会话和长期交互中保持上下文连续性。

### 1.2 核心设计理念

| 设计目标 | 实现方式 |
|----------|----------|
| **持久性** | 记忆文件存储在本地磁盘，跨会话保留 |
| **结构性** | 四种类型分类 + frontmatter 元数据 |
| **智能检索** | AI 驱动的相关性匹配，而非关键词匹配 |
| **自动化** | 后台 Forked Agent 自动提取重要信息 |
| **安全性** | 严格的工具访问控制和路径验证 |

### 1.3 核心流程概览

```
用户输入 → 记忆检索（异步预取） → 注入相关记忆 → AI 响应 → Stop Hook → 记忆提取（后台）
    ↑                                                              ↓
    └──────────────────── 下一轮对话重新检索 ────────────────────────┘
```

---

## 二、记忆系统架构

### 2.1 存储结构

```
~/.claude/projects/<sanitized-path>/memory/
├── MEMORY.md              # 索引文件（常加载到系统提示）
├── user_role.md           # 用户记忆
├── feedback_testing.md    # 反馈记忆
├── project_release.md     # 项目记忆
├── reference_jira.md      # 参考记忆
└── team/                  # 团队记忆目录（可选）
    ├── MEMORY.md
    └── ...
```

**关键点**：
- **MEMORY.md**：索引文件，始终加载到系统提示中（最多 200 行 / 25KB）
- **主题文件**：每个记忆独立存储，使用 frontmatter 格式

### 2.2 四种记忆类型

| 类型 | 用途 | 存放位置 | 触发场景 |
|------|------|----------|----------|
| **user** | 用户画像、角色、技能、偏好 | 私有目录 | "我是数据科学家"、"我写了10年Go" |
| **feedback** | 用户指导、纠正、确认 | 默认私有，项目约定可放团队 | "不要用mock"、"对，单个PR是对的" |
| **project** | 项目进度、约束、背景 | 默认团队 | "周四之后冻结merge"、"合规重构" |
| **reference** | 外部系统指针 | 默认团队 | "bugs在Linear项目INGEST里追踪" |

### 2.3 记忆文件格式

```markdown
---
name: {{memory name}}
description: {{one-line description}}
type: {{user, feedback, project, or reference}}
---

{{memory content}}

**Why:** {{原因}}
**How to apply:** {{如何应用}}
```

**注意**：feedback 和 project 类型建议包含 `Why` 和 `How to apply` 字段。

### 2.4 私有记忆与团队记忆

```
私有记忆目录（~/.claude/projects/<path>/memory/）
├── user 记忆（always private）
├── feedback 记忆（default private）
└── 其他个人偏好

团队记忆目录（memory/team/）
├── project 记忆（strongly team）
├── reference 记忆（usually team）
└── 项目级约定（如测试策略）
```

### 2.5 常加载 vs 按需加载

| 内容 | 加载时机 | 加载方式 |
|------|----------|----------|
| **MEMORY.md 索引** | 每轮对话开始 | 常加载（系统提示） |
| **具体记忆文件** | AI 判断相关时 | 按需加载（最多 5 个） |

**索引文件只包含链接和描述**，完整内容在 AI 判断相关后才注入。

---

## 三、容量与限制

### 3.1 记忆文件数量限制

```typescript
const MAX_MEMORY_FILES = 200        // 最大文件数量
const FRONTMATTER_MAX_LINES = 30   // 扫描时只读 frontmatter 行数
```

| 限制项 | 说明 |
|--------|------|
| **所有类型共享** | user + feedback + project + reference 共享 200 个 |
| **所有目录共享** | 私有记忆 + 团队记忆共享 200 个 |
| **选择策略** | 按文件修改时间排序，保留最新的 200 个 |

### 3.2 MEMORY.md 索引文件限制

```typescript
const MAX_ENTRYPOINT_LINES = 200      // 最大行数
const MAX_ENTRYPOINT_BYTES = 25_000  // 最大字节数 (25KB)
```

**估算 Token**：
- 按 4 字符/token 估算：~6,250 tokens
- 每行 ~150 字符（~37 tokens）：200 行 ≈ ~7,400 tokens

**截断机制**：
1. 先按行截断（到 200 行）
2. 再按字节截断（到 25KB）
3. 添加警告信息

**写入约束**：
- 每条索引一行，~150 字符以内
- 只写链接和简短描述

### 3.3 检索结果限制

```typescript
// findRelevantMemories.ts
"Return a list of filenames for the memories that will clearly be useful 
(up to 5). Only include memories that you are certain will be helpful."
```

| 阶段 | 处理内容 | 数量限制 |
|------|----------|----------|
| 扫描 | 所有 `.md` 文件的 frontmatter（30行） | 最多 200 个 |
| 清单 | 文件名 + 描述 + 类型 + 时间戳 | 所有扫描到的文件 |
| 精选 | Sonnet 从清单中选择 | **最多 5 个** |
| 加载 | 选中文件的完整内容 | 最多 5 个文件（每文件 4KB） |

### 3.4 会话累积限制

```typescript
export const RELEVANT_MEMORIES_CONFIG = {
  MAX_SESSION_BYTES: 60 * 1024,  // 60KB
}
```

| 限制类型 | 数值 | 说明 |
|----------|------|------|
| 每轮最多注入 | 5 条 × 4KB ≈ 20KB | 单次注入上限 |
| 会话累积上限 | **60KB** | 约等于 3 次完整注入后停止 |

**累积流程**：
```
Round 1: 注入 A, B, C（15KB） → 累计 15KB
Round 2: 注入 D, E, F（12KB） → 累计 27KB
Round 3: 注入 G, H（8KB）    → 累计 35KB
Round 4+: 累计 ≥ 60KB → 停止检索
```

**Compact 重置**：对话压缩时移除旧 attachment，计数器自然重置。

---

## 四、记忆检索机制

### 4.1 检索触发条件

记忆检索在**每轮用户输入时启动**，需满足以下条件：

| 条件 | 说明 |
|------|------|
| `isAutoMemoryEnabled()` | 自动记忆功能必须启用 |
| `tengu_moth_copse` | Feature Gate 必须开启 |
| 存在有效用户消息 | 最后一条非 meta 用户消息 |
| 输入包含空格 | 单词查询缺乏上下文，不触发 |
| 累积字节 < 60KB | 超过会话限制则不触发 |

### 4.2 两阶段筛选机制

#### 第一阶段：构建清单（Manifest）

只读取 frontmatter（最多 30 行），生成清单：

```
- [user] user_role.md (2026-03-15T10:30:00Z): user is a senior engineer
- [feedback] feedback_testing.md (2026-03-14T09:00:00Z): always run tests
- [project] project_release.md (2026-03-10T14:00:00Z): freeze on March 20
```

#### 第二阶段：AI 精选

使用 **Sonnet 模型**从清单中选择最多 5 个相关记忆：

```typescript
const SELECT_MEMORIES_SYSTEM_PROMPT = `
You are selecting memories that will be useful to Claude Code 
as it processes a user's query. Return a list of filenames 
(up to 5). Only include memories that you are certain will be helpful.
`
```

#### 第三阶段：加载选中内容

只有被选中的记忆文件的**完整内容**才加载到上下文。

### 4.3 检索时传入的内容

**不传入完整对话上下文**，只传入精简信息：

```
Query: 帮我修复登录页面的 bug

Available memories:
- [user] user_role.md (2026-04-10T14:30:00Z): user is a frontend developer
- [feedback] feedback_testing.md (2026-04-08T09:00:00Z): always write tests
- [project] project_login.md (2026-04-05T10:00:00Z): login page refactor
- [reference] reference_jira.md (2026-03-20T08:00:00Z): bugs in Jira AUTH

Recently used tools: Bash, Read
```

| 传入内容 | 来源 | 说明 |
|----------|------|------|
| `query` | 最后一条用户消息 | 只有文本，不含工具结果 |
| `manifest` | 扫描记忆文件 | 文件名 + 类型 + 时间戳 + 描述 |
| `toolsSection` | 最近成功使用的工具 | 用于过滤工具文档记忆 |

| 不传入的内容 | 原因 |
|--------------|------|
| 完整对话历史 | 太长，节省 token |
| assistant 响应 | 不需要 |
| 工具调用结果 | 只传用户原始输入 |
| 图片/附件 | 只提取文本 |

### 4.4 异步预取与注入时机

```typescript
// query.ts - 每轮用户输入启动预取
using pendingMemoryPrefetch = startRelevantMemoryPrefetch(
  state.messages,
  state.toolUseContext,
)
```

**特点**：
- `using` 关键字确保退出时自动清理
- 非阻塞执行，主流程继续
- 在循环迭代中检查是否完成
- 完成后标记 `consumedOnIteration`，不再重复注入

**注入检查**：
```typescript
if (
  pendingMemoryPrefetch &&
  pendingMemoryPrefetch.settledAt !== null &&     // 已完成
  pendingMemoryPrefetch.consumedOnIteration === -1  // 未消费
) {
  // 注入记忆...
}
```

### 4.5 去重与累积机制

#### 去重机制

```typescript
// 扫描历史消息，收集已注入路径
export function collectSurfacedMemories(messages) {
  const paths = new Set<string>()
  for (const m of messages) {
    if (m.attachment.type === 'relevant_memories') {
      for (const mem of m.attachment.memories) {
        paths.add(mem.path)  // 收集已注入路径
      }
    }
  }
  return { paths, totalBytes }
}

// 传入选择器作为过滤条件
findRelevantMemories(..., alreadySurfaced = surfaced.paths)
```

#### 新一轮时的行为

```
Round 1:
  ├─ 启动 prefetch 1
  ├─ 检索完成 → 注入记忆 A, B, C
  └─ consumedOnIteration = 0

Round 2:
  ├─ prefetch 1 自动 dispose
  ├─ 启动 prefetch 2
  ├─ collectSurfacedMemories → {A, B, C}
  ├─ 选择器排除 A, B, C
  └─ 可能选择 D, E, F（新的记忆）
```

### 4.6 时间戳与排序

#### 时间戳来源

来自**文件系统修改时间（mtime）**，不是内容字段：

```typescript
const { content, mtimeMs } = await readFileInRange(filePath, ...)
```

#### 排序逻辑

```typescript
.sort((a, b) => b.mtimeMs - a.mtimeMs)  // 最新在前
.slice(0, MAX_MEMORY_FILES)              // 截断到 200 个
```

#### 显示格式

**清单格式**：`- [user] user_role.md (2026-04-10T14:30:00Z): description`

**注入格式**：
- 新鲜记忆：`Memory (saved today): user_role.md:`
- 过期记忆：`Memory (saved 47 days ago): feedback_testing.md:` + 过期警告

#### 新鲜度警告

超过 1 天的记忆自动添加警告：
```
This memory is 47 days old. Memories are point-in-time observations, 
not live state — claims about code behavior may be outdated. 
Verify against current code before asserting as fact.
```

---

## 五、记忆写入机制

### 5.1 主 Agent 直接写入（实时）

**触发场景**：用户明确要求记住某事

```
用户: "请记住我偏好使用 bun 而不是 npm"
Claude: 立即执行 Write 工具写入 feedback_package_manager.md
```

**特点**：
- 即时响应，无延迟
- Prompt 包含完整保存指导
- 写入后后台提取跳过（互斥）

### 5.2 后台提取 Agent 写入（异步）

**触发时机**：每轮对话**结束时**（Stop Hook）

```typescript
// stopHooks.ts
if (feature('EXTRACT_MEMORIES') && !toolUseContext.agentId && isExtractModeActive()) {
  void extractMemoriesModule.executeExtractMemories(stopHookContext, ...)
}
```

**执行流程**：
```
用户输入 → Claude 响应 → 工具调用 → 最终响应 → Stop Hook
                                              ↓
                                      启动后台提取 Agent
                                              ↓
                                      Forked Agent 分析对话
                                              ↓
                                      判断是否需要保存
                                              ↓
                                      写入 .md 文件（可能不写）
```

### 5.3 触发条件链

不是每轮都会实际执行写入，需通过多层检查：

```
每轮结束 → Stop Hook → executeExtractMemories()
                            ↓
                    ┌─────────────────┐
                    │ 1. agentId?     │ → 子agent → 跳过
                    └─────────────────┘
                            ↓
                    ┌─────────────────┐
                    │ 2. Feature Gate │ → 关闭 → 跳过
                    └─────────────────┘
                            ↓
                    ┌─────────────────┐
                    │ 3. 记忆功能启用? │ → 关闭 → 跳过
                    └─────────────────┘
                            ↓
                    ┌─────────────────┐
                    │ 4. Remote Mode? │ → 是 → 跳过
                    └─────────────────┘
                            ↓
                    ┌─────────────────┐
                    │ 5. inProgress?  │ → 是 → stash等待
                    └─────────────────┘
                            ↓
                    ┌─────────────────┐
                    │ 6. 主agent已写? │ → 是 → 跳过（互斥）
                    └─────────────────┘
                            ↓
                    ┌─────────────────┐
                    │ 7. 节流检查     │ → 未达阈值 → 跳过
                    └─────────────────┘
                            ↓
                    ┌─────────────────┐
                    │ 执行提取        │
                    └─────────────────┘
```

### 5.4 节流与互斥机制

#### 节流机制

```typescript
if (!isTrailingRun) {
  turnsSinceLastExtraction++
  if (turnsSinceLastExtraction < threshold) return  // 节流跳过
}
turnsSinceLastExtraction = 0  // 重置
```

| 配置值 | 行为 |
|--------|------|
| `tengu_bramble_lintel = 1` (默认) | 每轮都尝试 |
| `tengu_bramble_lintel = 2` | 每 2 轮执行 |
| `tengu_bramble_lintel = 3` | 每 3 轮执行 |

#### 互斥机制

```typescript
// 主 agent 已写入时跳过
if (hasMemoryWritesSince(messages, lastMemoryMessageUuid)) {
  logForDebugging('[extractMemories] skipping — already wrote to memory')
  return
}
```

#### 防重叠机制

```typescript
// 正在执行时 stash 新请求
if (inProgress) {
  pendingContext = { context, appendSystemMessage }
  return
}

// finally 中处理 stash 的请求
if (pendingContext) {
  await runExtraction({ context: pendingContext.context, isTrailingRun: true })
}
```

#### 游标机制详解

**游标定义**：`lastMemoryMessageUuid` 是一个消息 UUID，记录上次处理的位置，划定"已处理区域"和"待处理区域"。

```
┌────────────────────────────────────────────────────────────┐
│  已处理区域（游标之前）  │  待处理区域（游标之后）          │
│  lastMemoryMessageUuid  │  新消息，需要分析是否提取记忆    │
└────────────────────────────────────────────────────────────┘
```

**hasMemoryWritesSince 检查逻辑**：

```typescript
function hasMemoryWritesSince(messages, sinceUuid) {
  let foundStart = false
  for (const message of messages) {
    if (!foundStart) {
      if (message.uuid === sinceUuid) foundStart = true  // 找到游标位置
      continue  // 游标之前的消息跳过
    }
    // 只检查游标之后的 assistant 消息
    if (message.type === 'assistant') {
      for (const block of content) {
        if (isAutoMemPath(filePath)) return true  // 发现主 Agent 写入
      }
    }
  }
  return false
}
```

**互斥的本质**：基于消息游标的协议，而非锁或等待。

| 机制 | 说明 |
|------|------|
| **游标** | `lastMemoryMessageUuid`，记录上次处理位置 |
| **互斥检查** | `hasMemoryWritesSince` 只检查游标之后的区域 |
| **主 Agent 优先** | 主 Agent 写入后，后台 Agent 检查到就跳过 |
| **游标推进** | 处理完成后更新游标到 `messages.at(-1)` |

#### 并发场景时序分析

**问题**：主 Agent 和后台 Agent 是完全独立的异步进程，可能并发执行。

```
第 N 轮：
┌─────────────────────────────────────────────────────┐
│ 用户输入 → 主 Agent 响应 → Stop Hook                 │
│     ↓                                                │
│ void extractMemories() ← fire-and-forget，不等待     │
│     ↓                                                │
│ 后台 Agent N 开始执行（可能耗时几秒）                 │
└─────────────────────────────────────────────────────┘

第 N+1 轮（后台 Agent N 还在执行）：
┌─────────────────────────────────────────────────────┐
│ 用户: "请记住我喜欢用 bun"                            │
│     ↓                                                │
│ 主 Agent 立即执行 Write（不等待后台 Agent）          │
│     ↓                                                │
│ 写入完成 → Stop Hook                                 │
│     ↓                                                │
│ 检查 inProgress=true → stash pendingContext         │
└─────────────────────────────────────────────────────┘

后台 Agent N 完成：
┌─────────────────────────────────────────────────────┐
│ 游标更新到 messages.at(-1)（第 N+1 轮末尾）          │
│     ↓                                                │
│ finally 块执行 trailing run                          │
│     ↓                                                │
│ hasMemoryWritesSince 检查游标之后                    │
│     ↓                                                │
│ 游标之后无新消息 → newMessageCount = 0               │
│ 或发现主 Agent 已写入 → 跳过                         │
└─────────────────────────────────────────────────────┘
```

**关键结论**：

| 问题 | 答案 |
|------|------|
| 主 Agent 会等待后台 Agent 吗？ | ❌ **不会**，完全异步 |
| 主 Agent 写入会被阻塞吗？ | ❌ **不会**，独立执行 |
| 会有冲突吗？ | ❌ **不会**，游标互斥保证不重复 |
| 会丢失记忆吗？ | ❌ **不会**，主 Agent 已写入用户请求的记忆 |

#### Trailing Run 特性

| 特性 | 正常 Run | Trailing Run |
|------|----------|--------------|
| 节流检查 | ✓ 受限制 | ✗ 跳过 |
| 消息范围 | 自游标后所有消息 | 两次调用间新增消息 |
| 执行时机 | 调用时立即 | 上一个完成后 |

### 5.5 写入工具设计

#### 工具类型

| 工具 | 用途 | 主 Agent | 后台 Agent |
|------|------|----------|------------|
| **Write** | 创建新记忆文件或完全覆盖 | ✓ 任意路径 | ⚠️ 仅记忆目录 |
| **Edit** | 更新现有记忆文件的部分内容 | ✓ 任意路径 | ⚠️ 仅记忆目录 |
| **Read** | 读取文件 | ✓ 任意路径 | ✓ 任意路径 |
| **Grep/Glob** | 搜索文件 | ✓ 任意路径 | ✓ 任意路径 |
| **Bash** | 执行命令 | ✓ 任意命令 | ⚠️ 仅只读命令 |
| **Agent/MCP 等** | 其他工具 | ✓ 允许 | ❌ 禁止 |

#### 后台 Agent 工具权限控制

```typescript
// extractMemories.ts - createAutoMemCanUseTool
export function createAutoMemCanUseTool(memoryDir: string): CanUseToolFn {
  return async (tool: Tool, input: Record<string, unknown>) => {
    // ✓ 允许 Read/Grep/Glob（完全允许，只读）
    if (tool.name === FILE_READ_TOOL_NAME || 
        tool.name === GREP_TOOL_NAME || 
        tool.name === GLOB_TOOL_NAME) {
      return { behavior: 'allow' }
    }

    // ✓ 允许 Bash（仅只读命令：ls/find/cat/stat/wc/head/tail）
    if (tool.name === BASH_TOOL_NAME && tool.isReadOnly(input)) {
      return { behavior: 'allow' }
    }

    // ⚠️ Edit/Write：仅限记忆目录内
    if ((tool.name === FILE_EDIT_TOOL_NAME || tool.name === FILE_WRITE_TOOL_NAME)) {
      if (isAutoMemPath(input.file_path)) {
        return { behavior: 'allow' }
      }
      return { behavior: 'deny', message: 'Only memory directory allowed' }
    }

    // ❌ 其他工具全部拒绝
    return { behavior: 'deny' }
  }
}
```

#### 路径验证设计

```typescript
// paths.ts
export function isAutoMemPath(absolutePath: string): boolean {
  // SECURITY: Normalize to prevent path traversal bypasses via .. segments
  const normalizedPath = normalize(absolutePath)
  return normalizedPath.startsWith(getAutoMemPath())
}
```

**安全措施**：
- 使用 `normalize()` 防止 `../` 路径遍历
- 检查路径是否以记忆目录开头
- 路径扩展（`expandPath`）防止 `~` 或相对路径绕过

#### 写入验证流程

**Write 工具验证**：

```
validateInput 验证阶段：
├─ 1. 秘密检查（checkTeamMemSecrets）
├─ 2. 权限设置检查（matchingRuleForInput）
├─ 3. 文件读取状态检查（readFileState）
└─ 4. 时间戳检查（防止并发写入）

call 执行阶段：
├─ mkdir（确保父目录存在）
├─ fileHistoryTrackEdit（备份，可选）
├─ 再次时间戳检查（原子性保护）
├─ writeTextContent（写入磁盘）
├─ LSP 通知（didChange + didSave）
├─ VSCode 通知（diff view）
├─ 更新 readFileState
└─ 日志事件
```

**原子性保护**：

```typescript
// FileWriteTool.ts 关键注释
// Please avoid async operations between here and writing to disk 
// to preserve atomicity.
```

- 验证后立即写入，中间无异步操作
- 两次时间戳检查（validateInput + call）
- 防止并发写入导致数据损坏

### 5.6 记忆内容与提示词设计

#### Agent 自主决定的内容

| 决定内容 | 指导方式 | 实际决定者 |
|----------|----------|------------|
| **记忆类型** | `<when_to_save>` 标签 | AI 判断 |
| **文件命名** | 示例 `{type}_{topic}.md` | AI 选择 |
| **description** | 提示"用于判断相关性" | AI 撰写 |
| **记忆正文** | frontmatter 格式 + Why/How 结构 | AI 撰写 |
| **是否保存** | 排除列表指导 | AI 判断 |

#### 类型判断提示词

Prompt 通过 XML 标签提供类型判断指导：

```xml
<type>
  <name>user</name>
  <scope>always private</scope>
  <when_to_save>When you learn any details about the user's role, 
                 preferences, responsibilities, or knowledge</when_to_save>
</type>

<type>
  <name>feedback</name>
  <scope>default to private. Save as team only when the guidance is 
         clearly a project-wide convention</scope>
  <when_to_save>Any time the user corrects your approach OR confirms 
                 a non-obvious approach worked</when_to_save>
</type>

<type>
  <name>project</name>
  <scope>private or team, but strongly bias toward team</scope>
  <when_to_save>When you learn who is doing what, why, or by when. 
                 Always convert relative dates to absolute dates 
                 (e.g., "Thursday" → "2026-03-05")</when_to_save>
</type>

<type>
  <name>reference</name>
  <scope>usually team</scope>
  <when_to_save>When you learn about resources in external systems 
                 and their purpose</when_to_save>
</type>
```

#### 文件命名建议

```markdown
# prompts.ts
'Write each memory to its own file (e.g., `user_role.md`, `feedback_testing.md`)'

命名模式建议：{type}_{topic}.md
```

**示例**：
- `user_role.md` - 用户角色记忆
- `feedback_testing.md` - 测试策略反馈
- `project_release.md` - 发布计划
- `reference_jira.md` - Jira 链接

#### Frontmatter 格式

```markdown
# memoryTypes.ts
---
name: {{memory name}}
description: {{one-line description — used to decide relevance in future conversations}}
type: {{user, feedback, project, or reference}}
---

{{memory content — for feedback/project types: rule/fact, then **Why:** and **How to apply:**}}
```

#### 内容结构建议

**feedback 和 project 类型**：

```
Lead with the rule itself, then:
**Why:** {{原因 — often a past incident or strong preference}}
**How to apply:** {{如何应用 — when/where this guidance kicks in}}
```

#### 写入流程（两步）

```markdown
# prompts.ts
**Step 1** — write the memory to its own file using frontmatter format

**Step 2** — add a pointer to that file in `MEMORY.md`
           Each entry: one line, under ~150 characters
           Format: `- [Title](file.md) — one-line hook`
```

**索引示例**：
```
- [User Role](user_role.md) — user is a data scientist
- [Testing Policy](feedback_testing.md) — use real database, not mocks
```

#### 明确排除的内容

```markdown
# memoryTypes.ts:183-195
## What NOT to save in memory

- Code patterns, conventions, architecture — derivable from code
- Git history, recent changes — `git log` / `git blame` are authoritative
- Debugging solutions — the fix is in the code
- Anything already documented in CLAUDE.md files
- Ephemeral task details: in-progress work, temporary state
```

### 5.7 记忆类型判断（简要版）

**AI 自主判断**，Prompt 提供指导：

| 类型 | `<when_to_save>` |
|------|-------------------|
| **user** | 用户提到职业、技能、偏好 |
| **feedback** | 用户纠正或确认做法 |
| **project** | 涉及项目进度、约束 |
| **reference** | 指向外部系统资源 |

**明确排除**：
- Code patterns, conventions（可从代码推导）
- Git history（git log 是权威）
- Debugging solutions（修复在代码中）
- 已在 CLAUDE.md 文档的内容
- 临时任务状态

---

## 六、记忆更新机制

### 6.1 概述

记忆更新**没有自动定时机制**，通过 **Prompt 指导 AI 自主判断**。

### 6.2 更新时机

| 更新时机 | 触发条件 | 执行者 |
|----------|----------|--------|
| 后台提取时 | Prompt 指导检查现有记忆 | Forked Agent |
| 使用记忆时 | 发现记忆与当前状态冲突 | 主 Agent |
| 用户请求时 | 用户明确要求更新 | 主 Agent |

### 6.3 更新指导

#### 后台提取时

```typescript
// prompts.ts
`## Existing memory files\n\n${existingMemories}\n\n
Check this list before writing — update an existing file 
rather than creating a duplicate.`
```

```typescript
'- Update or remove memories that turn out to be wrong or outdated',
'- Do not write duplicate memories. First check if there is an existing memory you can update.',
```

#### 使用记忆时

```typescript
// memoryTypes.ts (MEMORY_DRIFT_CAVEAT)
'If a recalled memory conflicts with current information, 
trust what you observe now — and update or remove the stale memory 
rather than acting on it.'
```

### 6.4 更新流程

**场景 1：后台提取时**
```
提取 Agent 分析对话 → 查看现有记忆清单 → 判断是否需要更新
    ↓
├─ 是 → Edit 更新现有文件
├─ 否 → Write 创建新文件（或不写）
```

**场景 2：使用时发现冲突**
```
检索到记忆："项目使用 npm" → AI 观察代码发现使用 bun
    ↓
冲突！信任当前观察 → Edit 更新记忆："项目使用 bun"
```

### 6.5 没有自动清理

| 问题 | 答案 |
|------|------|
| 有定时清理吗？ | ❌ 没有 |
| 有自动过期吗？ | ❌ 没有 |
| 有大小触发清理吗？ | ❌ 没有 |

**记忆会一直保留**，除非：
1. AI 在提取时判断需要更新/移除
2. AI 在使用时发现冲突并主动更新
3. 用户明确要求更新/删除

---

## 七、记忆管理功能

### 7.1 /remember 技能

提供专门的技能来审查和组织记忆：
- 分析当前记忆景观
- 建议将临时记忆提升到永久配置文件（CLAUDE.md, CLAUDE.local.md）
- 检测重复、过时和冲突的记忆条目

### 7.2 记忆整理

- 自动检测重复条目
- 识别过时内容
- 建议合并相似记忆

---

## 八、记忆系统的优势

| 优势 | 说明 |
|------|------|
| **持久性** | 记忆在会话间保持，提供了长期的上下文连续性 |
| **结构性** | 使用分类和元数据，便于管理和检索 |
| **自动化** | 后台自动提取重要信息 |
| **安全性** | 严格的访问控制和路径验证 |
| **可扩展性** | 支持团队记忆和私有记忆 |
| **智能检索** | 基于AI的相关性匹配 |

---

## 九、安全机制

### 9.1 工具访问控制

后台提取 Agent 的权限被严格限制：

| 工具 | 权限 |
|------|------|
| Read, Grep, Glob | ✓ 完全允许 |
| Bash（只读命令） | ✓ ls/find/cat/stat/wc/head/tail |
| Edit, Write | ✓ 仅限记忆目录内 |
| Bash rm | ❌ 禁止 |
| MCP, Agent 等 | ❌ 禁止 |

```typescript
// createAutoMemCanUseTool
if (tool.name === FILE_WRITE_TOOL_NAME || tool.name === FILE_EDIT_TOOL_NAME) {
  if (!isAutoMemPath(filePath)) {
    return { behavior: 'deny', message: 'Only memory directory allowed' }
  }
}
```

### 9.2 路径验证

所有路径经过规范化验证，防止：
- 路径遍历攻击（`../`）
- Unicode 规范化攻击
- URL 编码绕过
- 符号链接逃逸

```typescript
// validateTeamMemWritePath
const resolvedPath = resolve(filePath)
if (!resolvedPath.startsWith(teamDir)) {
  throw new PathTraversalError('Path escapes team memory directory')
}
```

---

## 十、与上下文压缩的关系

记忆系统与上下文压缩机制紧密协作：

| 方面 | 说明 |
|------|------|
| **信息保存** | 重要对话内容被提取为结构化记忆 |
| **压缩时** | 关键信息不会丢失，可引用相关记忆 |
| **累积重置** | Compact 移除旧 attachment，记忆累积计数器重置 |
| **长期上下文** | 维持长期记忆而不受 token 限制 |

---

## 十一、总结

### 核心数据流

```
┌─────────────────────────────────────────────────────────────────────┐
│                          用户输入                                    │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│  记忆检索（异步预取）                                                 │
│  ├─ 扫描 200 个记忆文件的 frontmatter                                 │
│  ├─ Sonnet 从清单选择最多 5 个相关记忆                                │
│  ├─ 加载选中文件的完整内容（每文件 4KB）                              │
│  └─ 注入到上下文（累积上限 60KB）                                     │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│  AI 响应 + 工具调用                                                   │
│  ├─ 可能直接写入记忆（用户明确请求）                                  │
│  ├─ 可能更新过期记忆（发现冲突）                                      │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│  Stop Hook → 后台提取 Agent                                          │
│  ├─ 检查 7 层触发条件                                                 │
│  ├─ 分析对话内容                                                      │
│  ├─ 查看现有记忆清单                                                  │
│  └─ 决定：更新现有 / 创建新文件 / 不写                                │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
                      下一轮对话（重复流程）
```

### 关键限制汇总

| 项目 | 限制值 |
|------|--------|
| 记忆文件总数 | 200 个 |
| MEMORY.md 行数 | 200 行 |
| MEMORY.md 字节 | 25 KB |
| 每轮检索数量 | 5 个 |
| 每个记忆文件 | 4 KB |
| 会话累积上限 | 60 KB |
| 提取 Agent 最大轮次 | 5 轮 |

### 设计亮点

1. **智能检索**：AI 驱动的相关性匹配，而非关键词匹配
2. **异步预取**：不阻塞主对话流程
3. **增量累积**：旧记忆保留，新记忆累积（有上限）
4. **自动重置**：Compact 自然重置累积限制
5. **互斥保护**：主 agent 写入后后台跳过
6. **新鲜度警告**：过期记忆自动提示验证

---

*文档生成日期：2026-04-14*