# Claude Code 上下文工程详解

Claude Code 的上下文工程是一套多层次、智能化的上下文管理机制，旨在在保持对话连续性的同时，有效控制上下文大小，避免超出模型的上下文窗口限制。

---

## 目录

1. [架构总览](#1-架构总览)
2. [完整数据流](#2-完整数据流)
3. [策略详解](#3-策略详解)
   - [3.1 Context Snipping（裁剪）- Stub](#31-context-snipping裁剪---stub)
   - [3.2 Microcompact（微压缩）](#32-microcompact微压缩)
   - [3.3 Context Collapse（上下文折叠）- Stub](#33-context-collapse上下文折叠---stub)
   - [3.4 Autocompact（自适应压缩）](#34-autocompact自适应压缩)
   - [3.5 Reactive Compact（响应式压缩）](#35-reactive-compact响应式压缩)
4. [熔断与降级机制](#4-熔断与降级机制)
5. [策略协调与优先级](#5-策略协调与优先级)
6. [Session Memory Compact（1M上下文优化）](#6-session-memory-compact1m上下文优化)
7. [UI层折叠（实际生效的视觉优化）](#7-ui层折叠实际生效的视觉优化)
8. [设计哲学总结](#8-设计哲学总结)

---

## 1. 架构总览

### 1.1 设计核心理念

传统的单层压缩策略面临几个关键问题：

| 问题 | 描述 |
|------|------|
| **过早压缩** | 简单的阈值触发会在对话尚未充分利用上下文时就压缩，导致信息丢失 |
| **压缩滞后** | 过于保守的阈值可能在超出限制后才响应，造成请求失败 |
| **一刀切处理** | 不同场景需要不同的处理力度，单一策略无法灵活应对 |
| **用户体验差** | 用户难以理解压缩的时机和原因，缺乏透明度 |

Claude Code 采用 **渐进式多层策略**，从轻微干预逐步过渡到深度处理：

### 1.2 五层策略架构

```
┌────────────────────────────────────────────────────────────────┐
│                    Claude Code 上下文工程架构                     │
│                                                                │
│  API请求前（query.ts 执行顺序）                                  │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Layer 1: Context Snipping    (第401-410行) ← Stub        │ │
│  │     ↓                                                     │ │
│  │ Layer 2: Microcompact        (第414-426行) ← 实际生效     │ │
│  │     ↓                                                     │ │
│  │ Layer 3: Context Collapse    (第440-447行) ← Stub        │ │
│  │     ↓                                                     │ │
│  │ Layer 4: Autocompact         (第454-468行) ← 实际生效     │ │
│  └──────────────────────────────────────────────────────────┘ │
│                          ↓                                     │
│                     发送 API 请求                               │
│                          ↓                                     │
│  API请求后（错误处理）                                           │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Layer 5: Reactive Compact    ← PTL错误触发               │ │
│  │     ↓                                                     │ │
│  │ truncateHeadForPTLRetry     ← 最后的逃生舱               │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 1.3 各层策略的设计权衡

| 层次 | 策略 | 当前状态 | 设计权衡 | 代价 | 收益 |
|------|------|----------|----------|------|------|
| 1 | Context Snipping | **Stub** | 最轻量级，快速响应 | 丢失最早对话历史 | 几乎无延迟，实时生效 |
| 2 | Microcompact | **生效** | 保留结构，清理内容 | 工具结果内容不可见 | 释放大量Token，不破坏结构 |
| 3 | Context Collapse | **Stub** | 视觉折叠，数据保留 | UI显示折叠 | 用户可展开，数据不丢失 |
| 4 | Autocompact | **生效** | AI驱动摘要 | 完整历史被压缩为摘要 | 大幅减少Token，保留关键信息 |
| 5 | Reactive Compact | **生效** | 紧急处理 | 需要额外的API调用 | 确保请求成功，避免失败 |

**重要发现**：当前实际生效的策略只有 **Microcompact、Autocompact、Reactive Compact**。

### 1.4 核心设计原则

- **智能保留**：保留最近和最相关的对话内容
- **渐进降级**：从轻微压缩逐步过渡到深度压缩
- **透明处理**：用户可以看到压缩摘要和边界信息
- **Token优化**：最大化上下文的效用/Token比
- **避免竞争**：各层策略之间有明确的优先级和协调机制
- **最小化损失**：只有所有压缩尝试都失败后，才会真正丢弃历史消息

### 1.5 关键设计假设与局限性

#### 1.5.1 核心假设：硬限制驱动而非质量驱动

当前上下文压缩的触发逻辑基于一个核心假设：**只要不超过模型的上下文窗口限制，模型就能有效处理**。

```
┌─────────────────────────────────────────────────────────────┐
│ Claude Code 的压缩触发逻辑                                    │
│                                                             │
│ 触发条件：tokenCount >= threshold（约93%窗口）               │
│                                                             │
│ 设计假设：                                                    │
│ • 模型在长上下文中表现良好                                    │
│ • 只要不超过窗口限制，模型就能有效处理                        │
│ • 用户需要完整历史来理解复杂任务                              │
│                                                             │
│ 不考虑的因素：                                                │
│ • 模型在长上下文中的注意力分散问题                            │
│ • "Lost in the Middle"现象（中间位置信息被忽略）             │
│ • 超长上下文可能导致的推理质量下降                            │
└─────────────────────────────────────────────────────────────┘
```

#### 1.5.2 设计权衡分析

| 方面 | 当前设计（硬限制驱动） | 潜在改进（质量驱动） |
|------|------------------------|---------------------|
| **触发时机** | 接近窗口限制（93%） | 可能更早（如60-70%） |
| **优化目标** | 避免 API 拒绝 | 保持模型推理质量 |
| **上下文利用** | 最大化利用窗口 | 可能浪费窗口空间 |
| **信息保留** | 尽可能多保留 | 更激进地压缩 |
| **适用场景** | 复杂长任务 | 一般任务 |

#### 1.5.3 为什么选择硬限制驱动？

**原因1：Claude 模型的长上下文优化**

Claude 模型本身针对长上下文进行了优化：
- 支持 200K+ 的上下文窗口
- 在长上下文中的表现相对稳定
- 相比其他模型，"Lost in the Middle"问题较轻

**原因2：用户需求优先**

```
场景示例：复杂项目开发

用户进行了以下操作：
├─ 读取了20个文件
├─ 执行了30次修改
├─ 讨论了架构决策
├─ 解决了多个bug
└─ 累计100轮对话

用户需求：
├─ 需要理解整个项目结构
├─ 需要知道之前的决策理由
├─ 需要追踪修改历史
└─ 如果过早压缩，可能丢失关键信息
```

过早基于"质量下降"触发压缩可能：
- 压缩掉用户仍需要的信息
- 破坏复杂任务的上下文连续性
- 需要用户反复提供相同信息

**原因3：难以量化"表现下降"**

| 潜在指标 | 量化困难 |
|----------|----------|
| 注意力分散 | 无法实时检测 |
| 推理质量下降 | 需要额外评估机制 |
| 响应相关性 | 需要对比分析 |

如果基于这些指标触发压缩，实现复杂度大幅增加。

#### 1.5.4 当前设计的局限性承认

| 承认的局限 | 当前的处理方式 |
|------------|----------------|
| 超长上下文可能导致注意力分散 | 依赖 Claude 模型的长上下文优化 |
| "Lost in the Middle"现象 | 未主动处理，假设模型设计已优化 |
| 推理质量可能随长度下降 | 未量化监控，依赖用户感知和反馈 |

**本质上是：将"长上下文性能问题"交给模型本身处理，而非客户端解决。**

#### 1.5.5 潜在的未来优化方向

```
┌─────────────────────────────────────────────────────────────┐
│ 可能的演进方向                                                │
│                                                             │
│ 方向1：动态阈值                                              │
│ • 根据任务类型调整压缩时机                                    │
│ • 简单任务：更早压缩                                         │
│ • 复杂任务：保持完整历史                                      │
│                                                             │
│ 方向2：语义重要性排序                                        │
│ • AI判断哪些历史更重要                                       │
│ • 保留高重要性内容                                           │
│ • 更早清理低重要性内容                                        │
│                                                             │
│ 方向3：性能监控触发                                          │
│ • 监控模型响应质量指标                                       │
│ • 检测到质量下降时触发压缩                                   │
│ • 需要建立质量评估机制                                       │
│                                                             │
│ 方向4：位置感知压缩                                          │
│ • 针对"Lost in the Middle"问题                               │
│ • 保留开头和结尾的关键信息                                   │
│ • 更激进压缩中间位置内容                                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 完整数据流

### 2.1 主查询循环处理流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                     query.ts 主循环完整数据流                         │
│                                                                     │
│  用户输入                                                            │
│      ↓                                                              │
│  构建消息数组 messages[]                                             │
│      ↓                                                              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Pre-API 预处理阶段                                            │   │
│  │                                                               │   │
│  │ 1. 记忆预取 (第301行)                                          │   │
│  │    startRelevantMemoryPrefetch()                             │   │
│  │    → 异步召回相关记忆，不阻塞主流程                             │   │
│  │                                                               │   │
│  │ 2. Context Snip (第401-410行) ← Stub                          │   │
│  │    snipCompactIfNeeded() → { messages, changed: false }      │   │
│  │    → 当前不执行任何裁剪                                        │   │
│  │                                                               │   │
│  │ 3. Microcompact (第414-426行) ← 实际生效                       │   │
│  │    evaluateTimeBasedTrigger() 检查时间间隔                    │   │
│  │    → gapMinutes >= 60 → 清除旧工具结果内容                    │   │
│  │    → 保留最近5个工具结果                                       │   │
│  │                                                               │   │
│  │ 4. Context Collapse (第440-447行) ← Stub                      │   │
│  │    applyCollapsesIfNeeded() → { messages, changed: false }   │   │
│  │    → 当前不执行任何折叠                                        │   │
│  │                                                               │   │
│  │ 5. Autocompact (第454-468行) ← 实际生效                        │   │
│  │    shouldAutoCompact() 六层决策                               │   │
│  │    → tokenCount >= threshold (~93%)                          │   │
│  │    → 执行 AI 摘要压缩                                          │   │
│  │    → 或 Session Memory Compact（1M窗口模型）                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│      ↓                                                              │
│  构建最终 messagesForQuery[]                                         │
│      ↓                                                              │
│  发送 API 请求                                                       │
│      ↓                                                              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ API 响应处理                                                  │   │
│  │                                                               │   │
│  │ 正常响应 → yield 消息流 → 完成                                │   │
│  │                                                               │   │
│  │ PTL错误 (HTTP 413) →                                          │   │
│  │    1. Context Collapse drain (stub，当前跳过)                 │   │
│  │    2. Reactive Compact 触发                                   │   │
│  │       → reactiveCompactOnPromptTooLong()                     │   │
│  │       → 成功 → 重试请求                                       │   │
│  │       → 也PTL → truncateHeadForPTLRetry()                    │   │
│  │                  → 真正裁剪最早消息                           │   │
│  │       → 失败 → 显示错误退出                                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 上下文大小与触发阈值

```
┌──────────────────────────────────────────────────────────────┐
│ 上下文大小 0% ──────────────────────────────────────── 100%  │
│                                                              │
│                    约60分钟                                   │
│                      ↓                                       │
│    [Time-based MC触发] ← 缓存过期，清除工具结果内容            │
│                                                              │
│                     约93%                                    │
│                       ↓                                      │
│    [Autocompact阈值] ← 可能触发AI摘要压缩                      │
│                       ↓                                      │
│           被以下条件抑制：                                    │
│           • 熔断 (consecutiveFailures >= 3)                  │
│           • 用户禁用                                         │
│           • 响应式优先模式                                   │
│                                                              │
│                     约95%                                    │
│                       ↓                                      │
│    [阻塞限制] ← 无法创建新Agent                               │
│                                                              │
│                     100%                                     │
│                       ↓                                      │
│    [API拒绝] ← PTL错误 → Reactive Compact                    │
│                       ↓                                      │
│    压缩也失败 → truncateHeadForPTLRetry（裁剪）               │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 策略详解

### 3.1 Context Snipping（裁剪）- Stub

#### 3.1.1 当前实现状态

**关键发现**：Context Snipping 当前是 **Stub 实现**，不执行任何实际裁剪。

```typescript
// snipCompact.ts 当前实现
export function snipCompactIfNeeded<T>(messages: T, _options?: unknown): {
  messages: T
  changed: boolean
  tokensFreed: number
  boundaryMessage?: Message
} {
  return { messages, changed: false, tokensFreed: 0 }  // ← 直接返回，不做修改
}
```

#### 3.1.2 设计初衷

虽然当前未实现，但其设计理念值得了解：

- **实时裁剪**：最轻量级的干预，几乎零延迟
- **最早的消息最不相关**：优先移除影响最小
- **Token传递**：记录节省的Token数供后续策略参考

#### 3.1.3 query.ts 中的调用

```typescript
// query.ts 第401-410行
if (feature('HISTORY_SNIP')) {
  queryCheckpoint('query_snip_start')
  const snipResult = snipModule!.snipCompactIfNeeded(messagesForQuery)
  messagesForQuery = snipResult.messages        // ← 原样返回
  snipTokensFreed = snipResult.tokensFreed      // ← 0
  if (snipResult.boundaryMessage) {
    yield snipResult.boundaryMessage            // ← 无
  }
  queryCheckpoint('query_snip_end')
}
```

---

### 3.2 Microcompact（微压缩）

#### 3.2.1 核心创新：利用服务器缓存过期机制

Microcompact 的设计基于一个关键洞察：**Anthropic API 的服务器端缓存有 60 分钟的过期时间**。

```
┌─────────────────────────────────────────────────────┐
│ Anthropic API 缓存机制                               │
│                                                     │
│ 用户请求 → 服务器缓存建立                             │
│     ↓                                               │
│ 缓存内容：System Prompt + 对话历史                   │
│ 缓存 TTL：60 分钟                                    │
│     ↓                                               │
│ 60分钟后 → 缓存过期 → 整个前缀需要重写                │
│     ↓                                               │
│ 如果对话历史包含大量工具结果 → 重写成本很高           │
└─────────────────────────────────────────────────────┘
```

**智慧的机会主义**：
- 缓存过期后，重写**必然发生**，损失已确定
- 此时主动清除旧工具结果内容 → 减少重写数据量
- 不是"遗忘"，而是"缓存过期后的优化"

#### 3.2.2 触发条件

```typescript
// timeBasedMCConfig.ts
type TimeBasedMCConfig = {
  enabled: boolean           // 主开关
  gapThresholdMinutes: 60   // 与服务器缓存 TTL 精确对应
  keepRecent: 5             // 保留最近5个工具结果
}

// microCompact.ts 第422-444行
export function evaluateTimeBasedTrigger(
  messages: Message[],
  querySource: QuerySource | undefined,
): { gapMinutes: number; config: TimeBasedMCConfig } | null {
  const config = getTimeBasedMCConfig()

  // 计算距离上次助手响应的时间间隔
  const gapMinutes =
    (Date.now() - new Date(lastAssistant.timestamp).getTime()) / 60_000

  // 只有超过60分钟才触发（确保缓存确实过期）
  if (!Number.isFinite(gapMinutes) || gapMinutes < config.gapThresholdMinutes) {
    return null  // 不触发
  }

  return { gapMinutes, config }
}
```

#### 3.2.3 清除操作实现

```typescript
// microCompact.ts
function maybeTimeBasedMicrocompact(
  messages: Message[],
  querySource: QuerySource | undefined,
): MicrocompactResult | null {
  const trigger = evaluateTimeBasedTrigger(messages, querySource)
  if (!trigger) return null

  const { config } = trigger

  // 只保留最近的N个可压缩的工具结果
  const keepRecent = Math.max(1, config.keepRecent)  // 默认5个
  const keepSet = new Set(compactableIds.slice(-keepRecent))
  const clearSet = new Set(compactableIds.filter(id => !keepSet.has(id)))

  // 将选定工具结果的内容替换为占位符
  const TIME_BASED_MC_CLEARED_MESSAGE = '[Old tool result content cleared]'

  // ... 执行清除操作
}
```

#### 3.2.4 可压缩的工具类型

```typescript
// microCompact.ts 第41-50行
const COMPACTABLE_TOOLS = new Set<string>([
  FILE_READ_TOOL_NAME,    // 文件读取结果（通常最大）
  SHELL_TOOL_NAMES,       // Shell命令输出
  GREP_TOOL_NAME,         // 搜索结果
  GLOB_TOOL_NAME,         // 文件匹配结果
  WEB_SEARCH_TOOL_NAME,   // 网络搜索结果
  WEB_FETCH_TOOL_NAME,    // 网页获取结果
  FILE_EDIT_TOOL_NAME,    // 文件编辑结果
  FILE_WRITE_TOOL_NAME,   // 文件写入结果
])
```

#### 3.2.5 清除前后对比

```typescript
// 清除前：完整的工具结果（可能100KB）
{
  type: 'user',
  message: {
    content: [
      {
        type: 'tool_result',
        tool_use_id: 'read_001',
        content: '这里是100KB的完整文件内容...'  // ← 大量token
      }
    ]
  }
}

// 清除后：保留结构，清空内容
{
  type: 'user',
  message: {
    content: [
      {
        type: 'tool_result',
        tool_use_id: 'read_001',  // ← ID保留（结构完整）
        content: '[Old tool result content cleared]'  // ← 内容被清空
      }
    ]
  }
}
```

#### 3.2.6 实际效果分析

```
场景示例：用户午休后回来继续工作

09:00 AM → 用户开始工作
  ├─ Claude读取多个文件（工具结果累计50KB）
  ├─ 执行多个Shell命令（输出累计20KB）
  └─ 总工具结果：70KB
  └─ 缓存建立，包含这70KB内容

12:05 PM → 用户回来（3小时后）
  ├─ 缓存已过期（TTL=60分钟）
  ├─ Time-based MC检测到gap > 60分钟
  ├─ 清除09:00的工具结果内容（保留最近5个）
  └─ 新请求发送：历史从70KB → 约7KB

效果：
  ├─ 服务器重写成本降低约90%
  ├─ 对话结构完整（知道读取过什么文件）
  ├─ 用户可随时重新读取文件恢复内容
  └─ 几乎无感知（工具结果仍可重新获取）
```

---

### 3.3 Context Collapse（上下文折叠）- Stub

#### 3.3.1 当前实现状态

**关键发现**：Context Collapse 当前是 **Stub 实现**，不执行任何实际折叠。

```typescript
// contextCollapse/index.ts 当前实现
export function isContextCollapseEnabled(): boolean {
  return false  // 功能未启用
}

export async function applyCollapsesIfNeeded<T>(messages: T): Promise<{
  messages: T
  changed: boolean
}> {
  return { messages, changed: false }  // ← 直接返回，不做修改
}
```

#### 3.3.2 设计初衷

设计的预期功能：
- 维护一个折叠的上下文视图
- 增量折叠不重要部分
- 提供更细粒度的控制（90%提交阈值、95%阻塞阈值）
- 可恢复的折叠机制

#### 3.3.3 与 Autocompact 的协调（预期）

```typescript
// autoCompact.ts 第215-222行：预期协调逻辑
if (feature('CONTEXT_COLLAPSE')) {
  if (isContextCollapseEnabled()) {
    return false  // 抑制Autocompact，让Collapse处理
  }
}
```

**当前实际状态**：由于 `isContextCollapseEnabled()` 返回 `false`，Autocompact 不受抑制。

---

### 3.4 Autocompact（自适应压缩）

#### 3.4.1 设计动机

**为什么需要 AI 驱动的摘要？**
- 简单的裁剪和清理可能丢失重要的上下文信息
- 长对话中包含大量冗余，但哪些是冗余需要智能判断
- AI 能理解对话的语义，提取关键信息，生成高质量摘要
- 比机械删除更能保持对话的连贯性和有用性

#### 3.4.2 阈值计算体系

```typescript
// autoCompact.ts 关键常量
const MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000   // p99.99摘要为17,387 tokens
const AUTOCOMPACT_BUFFER_TOKENS = 13_000       // 安全缓冲
const MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3 // 熔断阈值

// 有效上下文窗口计算
export function getEffectiveContextWindowSize(model: string): number {
  const reservedTokensForSummary = Math.min(
    getMaxOutputTokensForModel(model),
    MAX_OUTPUT_TOKENS_FOR_SUMMARY,
  )
  let contextWindow = getContextWindowForModel(model, getSdkBetas())

  // 可通过环境变量调整
  const autoCompactWindow = process.env.CLAUDE_CODE_AUTO_COMPACT_WINDOW
  if (autoCompactWindow) {
    const parsed = parseInt(autoCompactWindow, 10)
    if (!isNaN(parsed) && parsed > 0) {
      contextWindow = Math.min(contextWindow, parsed)
    }
  }

  return contextWindow - reservedTokensForSummary
}

// 自动压缩阈值
export function getAutoCompactThreshold(model: string): number {
  return getEffectiveContextWindowSize(model) - AUTOCOMPACT_BUFFER_TOKENS
}
```

**阈值计算示例（200K上下文窗口）**：

```
原始上下文窗口：200,000 tokens
减去输出预留：- 20,000 tokens（摘要空间）
有效窗口：180,000 tokens
减去缓冲空间：- 13,000 tokens（安全缓冲）
自动压缩阈值：167,000 tokens（约93%）
```

#### 3.4.2.1 p99.99 = 17,387 tokens 的数据来源

**关键设计**：这个数值来自生产环境的遥测统计，而非人工估算。

**遥测数据收集机制**：

每次压缩操作时，系统会记录 `tengu_compact` 事件，包含详细的 Token 统计：

```typescript
// compact.ts 第650-680行
logEvent('tengu_compact', {
  preCompactTokenCount,
  postCompactTokenCount,
  // ...
  compactionInputTokens: compactionUsage?.input_tokens,
  compactionOutputTokens: compactionUsage?.output_tokens,  // ← 摘要输出 Token 数
  compactionCacheReadTokens: compactionUsage?.cache_read_input_tokens ?? 0,
  compactionCacheCreationTokens: compactionUsage?.cache_creation_input_tokens ?? 0,
})
```

**数据流**：

```
┌─────────────────────────────────────────────────────────────┐
│                    遥测数据收集流程                           │
│                                                             │
│  compactConversation() 执行                                 │
│      ↓                                                      │
│  streamCompactSummary() 调用 API                            │
│      ↓                                                      │
│  API 返回 summaryResponse                                   │
│      ↓                                                      │
│  getTokenUsage(summaryResponse)                             │
│      ↓                                                      │
│  {                                                          │
│    input_tokens: xxx,                                       │
│    output_tokens: 17xxx,  ← 摘要的输出Token数                 │
│    ...                                                      │
│  }                                                          │
│      ↓                                                      │
│  logEvent('tengu_compact', { compactionOutputTokens })      │
│      ↓                                                      │
│  发送到 Statsig / Datadog                                   │
│      ↓                                                      │
│  后台统计分析 → 得出 p99.99 = 17,387                        │
└─────────────────────────────────────────────────────────────┘
```

**为什么选择 p99.99？**

| 百分位 | 含义 | 选择原因 |
|--------|------|----------|
| p50 | 中位数，一半摘要小于这个值 | 太小，会截断一半摘要 |
| p99 | 99%的摘要小于这个值 | 仍有1%会超出，可能失败 |
| **p99.99** | 只有0.01%超出 | 几乎所有摘要都能成功生成 |
| p100 | 最大值 | 会预留过多空间，浪费上下文 |

**生产数据分布示例**：

```
摘要输出Token分布：
┌────────────────────────────────────────┐
│ p50   :  3,500 tokens  (50%的摘要)     │ ← 大多数摘要较短
│ p90   :  8,000 tokens  (90%的摘要)     │
│ p99   : 12,000 tokens  (99%的摘要)     │
│ p99.9 : 15,000 tokens  (99.9%的摘要)   │
│ p99.99: 17,387 tokens  (99.99%的摘要)  │ ← 选择这个
│ max   : 25,000 tokens  (极端情况)      │
└────────────────────────────────────────┘

预留 20,000 tokens（略大于 p99.99）：
• 覆盖几乎所有场景（99.99%）
• 只有 0.01% 会超出 → 极少失败
• 不会像 max 那样预留过多空间
```

**设计哲学：数据驱动而非强制限制**

```
传统做法（强制限制）：
┌──────────────────────────────────────┐
│ 摘要提示："请用不超过500字概括对话..." │
│                                      │
│ 问题：                                │
│ • 500字够不够？不知道                  │
│ • 复杂对话可能丢失关键信息              │
│ • 简单对话浪费Token                      │
└──────────────────────────────────────┘

Claude Code的做法（数据驱动）：
┌──────────────────────────────────────┐
│ 摘要提示："请全面概括对话的关键内容..." │
│                                      │
│ 然后：                                │
│ • 让模型自然输出                       │
│ • 收集生产数据                         │
│ • 统计得到 p99.99 = 17,387            │
│ • 用这个值预留空间                     │
└──────────────────────────────────────┘
```

**为什么不强制限制输出长度？**

| 对话复杂度 | 需要的摘要长度 |
|------------|----------------|
| 简单问答（5轮） | 几百 tokens |
| 中等任务（20轮，多个文件） | 几千 tokens |
| 复杂项目（100轮，多文件，多次修改） | 上万 tokens |

强制限制会导致：
- 复杂对话的摘要不够详细，丢失关键信息
- 后续对话无法理解之前做了什么

**核心思路**：让 AI 做它擅长的事（生成高质量摘要），让数据告诉我们需要预留多少空间。

#### 3.4.3 六层决策机制

```typescript
// autoCompact.ts 第160-239行
export async function shouldAutoCompact(
  messages: Message[],
  model: string,
  querySource?: QuerySource,
  snipTokensFreed = 0,
): Promise<boolean> {

  // 第1层：递归防护
  if (querySource === 'session_memory' || querySource === 'compact') {
    return false  // 避免死锁
  }

  // 第2层：特殊源防护
  if (querySource === 'marble_origami') {
    return false  // 防止破坏主线程折叠状态
  }

  // 第3层：功能开关检查
  if (!isAutoCompactEnabled()) {
    return false  // 用户禁用
  }

  // 第4层：响应式优先模式
  if (getFeatureValue_CACHED_MAY_BE_STALE('tengu_cobalt_raccoon', false)) {
    return false  // 让Reactive Compact作为后备
  }

  // 第5层：上下文折叠优先
  if (isContextCollapseEnabled()) {
    return false  // 当前stub，返回false，不影响
  }

  // 第6层：最终Token阈值判断
  const tokenCount = tokenCountWithEstimation(messages) - snipTokensFreed
  const threshold = getAutoCompactThreshold(model)

  return tokenCount >= threshold
}
```

**六层决策的设计动机**：

| 层次 | 检查 | 设计动机 |
|------|------|----------|
| 1 | 递归防护 | session_memory/compact 本身会调用压缩逻辑，允许触发会造成无限递归 |
| 2 | 特殊源防护 | marble_origami 是上下文折叠代理，压缩会破坏主线程状态 |
| 3 | 功能开关 | 用户可能明确禁用自动压缩 |
| 4 | 响应式优先 | 某些场景下让 Reactive Compact 作为后备更合适 |
| 5 | 折叠优先 | Context Collapse 提供更细粒度控制（当前stub） |
| 6 | Token阈值 | 最终的触发条件，约93%有效窗口 |

#### 3.4.4 执行优先级

```typescript
// autoCompact.ts 第287-333行
// 优先级1：Session Memory Compact（针对1M窗口）
const sessionMemoryResult = await trySessionMemoryCompaction(...)
if (sessionMemoryResult) {
  return { wasCompacted: true, compactionResult: sessionMemoryResult }
}

// 优先级2：传统 AI 摘要压缩
const compactionResult = await compactConversation(
  messages,
  toolUseContext,
  cacheSafeParams,
  true,   // Suppress user questions for autocompact
  undefined,
  true,   // isAutoCompact
  recompactionInfo,
)
```

#### 3.4.5 熔断机制

```typescript
// autoCompact.ts 第260-265行
if (
  tracking?.consecutiveFailures !== undefined &&
  tracking.consecutiveFailures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES
) {
  return { wasCompacted: false }  // 停止尝试
}
```

**生产数据支撑**：
> 1,279 sessions had 50+ consecutive failures (up to 3,272) in a single session, wasting ~250K API calls/day globally.

熔断机制避免了每天约 25 万次无效 API 调用。

#### 3.4.6 触发场景清单

**会触发的条件组合**：

| 条件 | 要求 |
|------|------|
| Token阈值 | `tokenCount >= threshold`（约93%） |
| 用户配置 | `isAutoCompactEnabled() === true` |
| 熔断状态 | `consecutiveFailures < 3` |
| 请求源 | 不是 `session_memory`/`compact`/`marble_origami` |

**不会触发的场景**：

| 场景 | 原因 |
|------|------|
| `DISABLE_AUTO_COMPACT=1` | 功能开关关闭 |
| 连续失败 >= 3 次 | 熔断机制生效 |
| 正在执行压缩/记忆提取 | 递归防护 |

---

### 3.5 Reactive Compact（响应式压缩）

#### 3.5.1 设计动机

**为什么需要错误驱动的压缩？**
- 主动预测很难完美：总有预测失败的情况
- API 的实际限制可能与客户端估算不同
- 媒体文件（图片、PDF）的Token估算可能有误差
- 需要一个可靠的"救火机制"确保请求成功

#### 3.5.2 触发时机

在 API 返回 PTL（Prompt Too Long）错误后触发：

```typescript
// query.ts 第1070-1083行
const isWithheld413 =
  lastMessage?.type === 'assistant' &&
  lastMessage.isApiErrorMessage &&
  isPromptTooLongMessage(lastMessage)

const isWithheldMedia =
  mediaRecoveryEnabled &&
  reactiveCompact?.isWithheldMediaSizeError(lastMessage)
```

#### 3.5.3 处理流程

```typescript
// query.ts 第1085-1165行
if (isWithheld413) {
  // 1. 先尝试 Context Collapse drain（当前stub，跳过）
  if (feature('CONTEXT_COLLAPSE') && contextCollapse) {
    const drained = contextCollapse.recoverFromOverflow(...)
    if (drained.committed > 0) {
      state = { messages: drained.messages, transition: { reason: 'collapse_drain_retry' } }
      continue  // 重试请求
    }
  }

  // 2. Reactive Compact 触发
  if ((isWithheld413 || isWithheldMedia) && reactiveCompact) {
    const compacted = await reactiveCompact.tryReactiveCompact({
      hasAttempted: hasAttemptedReactiveCompact,
      querySource,
      messages: messagesForQuery,
      // ...
    })

    if (compacted) {
      // 压缩成功 → 重试请求
      const postCompactMessages = buildPostCompactMessages(compacted)
      state = { messages: postCompactMessages, hasAttemptedReactiveCompact: true }
      continue
    }

    // 3. 压缩失败 → 显示错误
    yield lastMessage
    return { reason: 'prompt_too_long' }
  }
}
```

#### 3.5.4 状态防护

```typescript
hasAttemptedReactiveCompact: true  // 防止螺旋式重试
```

只尝试一次，避免反复压缩失败。

---

## 4. 熔断与降级机制

### 4.1 熔断后的完整处理路径

**关键设计**：熔断后不立即裁剪，而是等待 API 错误触发 Reactive Compact。

```
┌─────────────────────────────────────────────────────────────┐
│                   熔断后的处理流程                            │
│                                                             │
│  Autocompact 熔断 (consecutiveFailures >= 3)               │
│       ↓                                                     │
│  autoCompactIfNeeded 返回 { wasCompacted: false }          │
│       ↓                                                     │
│  query.ts 继续执行，不进行任何压缩                           │
│       ↓                                                     │
│  发送 API 请求（使用完整的 messagesForQuery）               │
│       ↓                                                     │
│  ┌─────────────────┬─────────────────────────────────┐     │
│  │ 请求成功        │ 请求失败 (PTL错误)               │     │
│  │                 │                                  │     │
│  │ 正常响应        │ 触发 Reactive Compact           │     │
│  │                 │      ↓                          │     │
│  │                 │ ┌───────────┬──────────────┐    │     │
│  │                 │ │压缩成功   │压缩也PTL     │    │     │
│  │                 │ │           │              │    │     │
│  │                 │ │重试请求   │truncateHead  │    │     │
│  │                 │ │           │ForPTLRetry   │    │     │
│  │                 │ │           │(真正裁剪!)   │    │     │
│  └─────────────────┴─────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 为什么熔断后不立即裁剪？

| 设计决策 | 原因 |
|----------|------|
| 熔断后不立即裁剪 | 熔断只是"停止自动压缩尝试"，不代表一定会超限 |
| 等待 API 错误 | API 的实际限制比客户端估算更准确 |
| Reactive Compact 作为后备 | 确保在任何情况下都有恢复路径 |

### 4.3 最后的逃生舱：truncateHeadForPTLRetry

```typescript
// compact.ts 第243-291行
export function truncateHeadForPTLRetry(
  messages: Message[],
  ptlResponse: AssistantMessage,
): Message[] | null {
  // 按API轮次分组
  const groups = groupMessagesByApiRound(input)
  if (groups.length < 2) return null

  // 精确裁剪：根据API返回的超出Token数计算
  const tokenGap = getPromptTooLongTokenGap(ptlResponse)
  if (tokenGap !== undefined) {
    let acc = 0
    for (const g of groups) {
      acc += roughTokenCountEstimationForMessages(g)
      dropCount++
      if (acc >= tokenGap) break  // 丢弃直到覆盖超出的Token数
    }
  } else {
    // Fallback：丢弃20%的组
    dropCount = Math.max(1, Math.floor(groups.length * 0.2))
  }

  // 至少保留一组
  dropCount = Math.min(dropCount, groups.length - 1)

  const sliced = groups.slice(dropCount).flat()

  // 如果裁剪后首条是assistant，补一个合成user消息
  if (sliced[0]?.type === 'assistant') {
    return [
      createUserMessage({
        content: '[earlier conversation truncated for compaction retry]',
        isMeta: true
      }),
      ...sliced
    ]
  }
  return sliced
}
```

### 4.4 裁剪触发条件总结

| 场景 | 是否裁剪 | 触发时机 |
|------|----------|----------|
| Autocompact 熔断 | **否** | 熔断只是停止主动尝试 |
| 主请求 PTL 错误 | **尝试压缩** | Reactive Compact 触发 |
| 压缩请求也 PTL | **是** | `truncateHeadForPTLRetry` 执行 |

### 4.5 压缩失败层级

```
┌──────────────────────────────────────┐
│ Layer 1: Autocompact 主动尝试        │ ← 正常路径
│     ↓ 失败                           │
│ Layer 2: 熔断，停止主动尝试           │ ← 保护机制
│     ↓                                │
│ Layer 3: 等待API错误                  │ ← 观察阶段
│     ↓ 发生PTL错误                    │
│ Layer 4: Reactive Compact 触发       │ ← 后备机制
│     ↓ 压缩请求也PTL                  │
│ Layer 5: truncateHeadForPTLRetry     │ ← 最后手段
│     ↓                                │
│ 真正裁剪最早消息                       │
└──────────────────────────────────────┘
```

---

## 5. 策略协调与优先级

### 5.1 策略间的协调机制

```
┌─────────────────────────────────────────────────────────────┐
│                    策略协调关系                               │
│                                                             │
│  Time-based MC                                              │
│      ↓ 时间触发，独立运行                                     │
│                                                             │
│  Autocompact                                                │
│      ↓ 受以下条件抑制：                                       │
│      ├─ isContextCollapseEnabled() → 抑制（当前false）       │
│      ├─ tengu_cobalt_raccoon → 抑制                         │
│      ├─ consecutiveFailures >= 3 → 熔断                     │
│      └─ 递归防护                                             │
│                                                             │
│  Reactive Compact                                           │
│      ↓ 作为 Autocompact 的后备                               │
│      ├─ 只在 API 错误后触发                                   │
│      ├─ hasAttemptedReactiveCompact 防止重复                 │
│      └─ 与 Autocompact 共享压缩逻辑                          │
│                                                             │
│  truncateHeadForPTLRetry                                    │
│      ↓ 最后手段                                              │
│      └─ 只在 Reactive Compact 也失败时执行                   │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 querySource 防护机制

```typescript
// 防止递归调用的 querySource 检查
const RECURSION_GUARD_QUERY_SOURCES = [
  'session_memory',  // 记忆提取代理
  'compact',         // 压缩代理本身
  'marble_origami',  // 上下文折叠代理
]

if (RECURSION_GUARD_QUERY_SOURCES.includes(querySource)) {
  return false  // 不触发 Autocompact
}
```

---

## 6. Session Memory Compact（1M上下文优化）

### 6.1 设计动机

某些模型支持 1M（100万）Token的上下文窗口，传统压缩策略不适用于如此大的窗口。

### 6.2 配置体系

```typescript
// sessionMemoryCompact.ts
type SessionMemoryCompactConfig = {
  minTokens: 10_000          // 压缩后保留的最小Token数
  minTextBlockMessages: 5    // 保留的最小含文本块的消息数
  maxTokens: 40_000          // 压缩后保留的最大Token数（硬上限）
}
```

### 6.3 执行优先级

```typescript
// autoCompact.ts 第287-310行
// Autocompact 执行时，优先尝试 Session Memory Compact
const sessionMemoryResult = await trySessionMemoryCompaction(...)
if (sessionMemoryResult) {
  return { wasCompacted: true, compactionResult: sessionMemoryResult }
}

// 如果不适用，再使用传统 Compact
const compactionResult = await compactConversation(...)
```

---

## 7. UI层折叠（实际生效的视觉优化）

### 7.1 与 Context Collapse 的区别

| 层面 | 实现位置 | 当前状态 | 是否修改数据 |
|------|----------|----------|--------------|
| UI层折叠 | `collapseReadSearch.ts` | **生效** | ✗ 仅视觉变换 |
| Context Collapse | `contextCollapse/index.ts` | **Stub** | 未实现 |

### 7.2 实现机制

```typescript
// collapseReadSearch.ts 第762-949行
export function collapseReadSearchGroups(
  messages: RenderableMessage[],
  tools: Tools,
): RenderableMessage[] {
  const result: CollapsedReadSearchGroup = {
    type: 'collapsed_read_search',
    searchCount: group.searchCount,     // 搜索次数摘要
    readCount: group.readCount,         // 读取文件数摘要
    messages: group.messages,           // ← 原始消息完整保留！
    displayMessage: firstMsg,
  }
  return result
}
```

### 7.3 可折叠的操作类型

- Read（文件读取）
- Grep（内容搜索）
- Glob（文件匹配）
- Bash 搜索命令（`grep`, `find`, `ls`, `cat`）
- List 操作（目录列出）
- MCP 工具调用

### 7.4 视觉效果

```
默认显示（折叠模式）：
┌─────────────────────────────────────────────┐
│ ⎿ Read 5 files, searched 3 patterns         │ ← 简洁摘要
└─────────────────────────────────────────────┘

详细显示（Ctrl+O模式）：
┌─────────────────────────────────────────────┐
│ ⎿ Read 5 files, searched 3 patterns         │
│   ├─ Read README.md                         │ ← 展开的详细内容
│   ├─ Read src/index.ts                      │
│   ├─ Grep "function" src/                   │
└─────────────────────────────────────────────┘
```

### 7.5 关键结论

**UI层折叠不修改发送给 API 的内容**：
- 显示层：摘要形式
- API层：原始 `messages[]` 完整保留

---

## 8. 设计哲学总结

### 8.1 核心设计原则

| 原则 | 具体体现 |
|------|----------|
| **深度理解底层机制** | Time-based MC 基于 API 缓存 TTL 的精确理解 |
| **渐进式降级** | 从微压缩 → AI摘要 → 紧急裁剪，逐步加深 |
| **智能协调** | 六层决策机制避免策略竞争 |
| **多层容错** | Autocompact → Reactive Compact → truncateHead，三级后备 |
| **最小化损失** | 只有所有压缩尝试都失败后才真正裁剪 |
| **透明可控** | 用户可看到压缩摘要，支持手动压缩 |

### 8.2 当前生效的策略

| 策略 | 状态 | 触发条件 | 主要作用 |
|------|------|----------|----------|
| **Microcompact** | ✅ 生效 | gap >= 60分钟 | 清除旧工具结果内容，减少缓存重写成本 |
| **Autocompact** | ✅ 生效 | token >= 93% | AI摘要压缩，保留关键信息 |
| **Reactive Compact** | ✅ 生效 | PTL错误 | 紧急压缩后备 |
| **truncateHeadForPTLRetry** | ✅ 生效 | Reactive也失败 | 最后手段，真正裁剪 |
| **Context Snipping** | ❌ Stub | - | 设计存在，未实现 |
| **Context Collapse** | ❌ Stub | - | 设计存在，未实现 |
| **UI层折叠** | ✅ 生效 | 渲染时 | 仅视觉优化，不修改数据 |

### 8.3 架构亮点

1. **Time-based Microcompact**：智慧的机会主义，利用缓存过期特性优化
2. **熔断机制**：数据驱动的保护设计，避免无效API调用
3. **五层降级**：最小化信息丢失，裁剪只在最后手段
4. **六层决策**：避免递归、竞争、不当触发
5. **UI与数据分离**：视觉优化不影响API数据