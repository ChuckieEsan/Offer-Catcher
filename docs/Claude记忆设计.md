# Claude Code 记忆模块详解

Claude Code的记忆系统是一个多层次、智能的持久化记忆机制，旨在帮助AI模型在跨会话和长期交互中保持上下文连续性。下面是其核心设计和工作机制：

## 1. 记忆系统架构

### 1.1 记忆存储结构
- **主存储位置**: `~/.claude/projects/<sanitized-path>/memory/`
- **主索引文件**: `MEMORY.md` - 这是系统始终加载到上下文中的记忆索引
- **主题文件**: 每个记忆以单独的 `.md` 文件形式保存，使用frontmatter格式

### 1.2 四种记忆类型
Claude Code将记忆分为四个明确的类型，每种都有特定用途：

1. **用户记忆 (User)**: 关于用户的角色、目标、责任和知识的信息
2. **反馈记忆 (Feedback)**: 用户提供的关于如何工作的指导 - 需要避免什么和继续做什么
3. **项目记忆 (Project)**: 关于正在进行的工作、目标、计划、错误或事故的信息
4. **参考记忆 (Reference)**: 存储外部系统中信息指针的内存

### 1.3 记忆文件格式
每个记忆文件都包含frontmatter格式：
```markdown
---
name: {{memory name}}
description: {{one-line description}}
type: {{user, feedback, project, or reference}}
---
{{memory content}}
```

## 2. 记忆创建机制

### 2.1 主动记忆创建
当用户明确要求记住某些内容时，AI会：
1. 创建新的记忆文件（使用上述frontmatter格式）
2. 更新 `MEMORY.md` 索引文件，添加指向新文件的链接

### 2.2 自动记忆提取
在后台自动运行的 `extractMemories` 系统：
- 在每次查询循环结束时分析最新对话
- 使用forked agent从对话中提取重要信息
- 将相关信息保存为结构化记忆文件
- 自动更新索引

### 2.3 记忆提取流程
```typescript
async function runExtraction({
  context,
  appendSystemMessage,
  isTrailingRun,
}: {
  context: REPLHookContext
  appendSystemMessage?: AppendSystemMessageFn
  isTrailingRun?: boolean
}): Promise<void> {
  // 1. 检查是否已有主代理写入记忆（避免重复）
  if (hasMemoryWritesSince(messages, lastMemoryMessageUuid)) {
    // 跳过并更新游标
    return
  }

  // 2. 构建提取提示
  const userPrompt = feature('TEAMMEM') && teamMemoryEnabled
    ? buildExtractCombinedPrompt(/*...*/)
    : buildExtractAutoOnlyPrompt(/*...*/)

  // 3. 运行forked agent提取记忆
  const result = await runForkedAgent({
    promptMessages: [createUserMessage({ content: userPrompt })],
    cacheSafeParams,
    canUseTool,
    querySource: 'extract_memories',
    forkLabel: 'extract_memories',
    maxTurns: 5, // 限制轮次防止无限循环
  })

  // 4. 解析并保存写入的文件路径
  const writtenPaths = extractWrittenPaths(result.messages)
}
```

## 3. 记忆检索机制

### 3.1 智能记忆搜索
`findRelevantMemories` 函数实现实时记忆检索：
- 扫描记忆目录中的所有 `.md` 文件
- 读取每个文件的frontmatter（类型、描述等）
- 使用专门的Claude Sonnet模型根据用户查询选择最相关的记忆
- 返回匹配的记忆文件列表

### 3.2 检索算法
```typescript
export async function findRelevantMemories(
  query: string,
  memoryDir: string,
  signal: AbortSignal,
  recentTools: readonly string[] = [],
  alreadySurfaced: ReadonlySet<string> = new Set(),
): Promise<RelevantMemory[]> {
  // 1. 扫描所有记忆文件
  const memories = (await scanMemoryFiles(memoryDir, signal)).filter(
    m => !alreadySurfaced.has(m.filePath),
  )
  
  // 2. 使用AI选择相关记忆
  const selectedFilenames = await selectRelevantMemories(
    query,
    memories,
    signal,
    recentTools,
  )
  
  // 3. 返回匹配的记忆路径和时间戳
  return selected.map(m => ({ path: m.filePath, mtimeMs: m.mtimeMs }))
}
```

### 3.3 记忆召回触发机制

记忆召回由 `startRelevantMemoryPrefetch` 函数控制，位于 `src/utils/attachments.ts` 文件中。该函数负责在适当的条件下启动异步记忆检索。

#### 3.3.1 触发条件
记忆召回需满足以下条件：
1. `!isAutoMemoryEnabled()` - 自动记忆功能必须启用
2. `!getFeatureValue_CACHED_MAY_BE_STALE('tengu_moth_copse', false)` - 特定功能开关必须开启
3. 存在有效的用户消息
4. 输入必须包含至少一个空格（多词查询）
5. 已展示的记忆总字节数未超过60KB限制

#### 3.3.2 完整的调用链路
```
query.ts (主查询循环) 
→ startRelevantMemoryPrefetch() 
→ getRelevantMemoryAttachments() 
→ findRelevantMemories() 
→ sideQuery() (AI驱动的异步查询)
```

#### 3.3.3 异步召回实现机制
- **Promise封装**: 使用Promise包装记忆检索操作，确保不阻塞主线程
```
const promise = getRelevantMemoryAttachments(
  input, // 用户输入
  toolUseContext.options.agentDefinitions.activeAgents, // 活跃代理
  toolUseContext.readFileState, // 已读文件状态
  collectRecentSuccessfulTools(messages, lastUserMessage), // 最近使用的工具
  controller.signal, // 取消信号
  surfaced.paths, // 已展示过的路径
)
```

- **后台预取**: 通过 `sideQuery` 函数在后台进行AI查询，不影响主对话流程
- **取消支持**: 使用AbortController支持取消机制，用户可随时中断查询
- **预加载策略**: 在主对话继续的同时提前检索相关记忆

#### 3.3.4 AI驱动的选择算法
`selectRelevantMemories` 函数使用Claude Sonnet模型进行相关性判断：
- 使用专门的系统提示 (`SELECT_MEMORIES_SYSTEM_PROMPT`)
- 发送用户查询和可用记忆清单给AI
- 请求AI选择最多5个最相关的记忆文件

AI选择系统提示内容：
```
"You are selecting memories that will be useful to Claude Code as it processes a user's query.
Return a list of filenames for the memories that will clearly be useful to Claude Code 
as it processes the user's query (up to 5). Only include memories that you are certain 
will be helpful based on their name and description."

- 如果不确定某个记忆对处理用户查询有用，则不要包含它
- 如果列表中没有清楚有用的记忆，则返回空列表
- 如果提供了最近使用的工具列表，则不要选择这些工具的参考文档
```

#### 3.3.5 过滤和验证阶段
在AI选择之后，还有重要的过滤和验证步骤：
- **有效性验证**: 验证AI返回的文件名确实存在于扫描的文件列表中
- **去重过滤**: 过滤掉已经读取过的文件 (`readFileState`) 和已展示过的文件 (`alreadySurfaced`)
- **数量限制**: 限制返回结果为最多5个文件
- **文件路径映射**: 根据选中的文件名重新构建文件路径和时间戳信息

```typescript
const byFilename = new Map(memories.map(m => [m.filename, m]))
const selected = selectedFilenames
  .map(filename => byFilename.get(filename))
  .filter((m): m is MemoryHeader => m !== undefined)
```

#### 3.3.6 特殊处理规则
- **工具关联过滤**: 如果最近使用了某个工具，则不选择该工具的参考文档（因为已经有工作中的使用示例）
- **重复预防**: 通过 `alreadySurfaced` 集合防止重复显示相同记忆
- **文件新鲜度追踪**: 返回文件修改时间戳以便展示文件更新情况
- **性能优化**: 仅在多词查询时启动召回（单词查询缺乏足够上下文）

整个召回机制是高度智能化的，利用专门的AI模型来判断记忆的相关性，而不是简单的关键词匹配。这确保了只有真正与当前上下文相关的记忆才会被召回和显示，既提高了效率又减少了噪音。

## 4. 记忆系统的安全机制

### 4.1 工具访问控制
`createAutoMemCanUseTool` 函数限制提取代理只能访问特定操作：
- 允许读取工具：Read, Grep, Glob
- 允许只读bash命令：ls, find, grep, cat, stat, wc, head, tail
- 允许写入工具：仅限记忆目录下的Edit/Write

### 4.2 路径验证
所有路径都会经过规范化验证，防止路径遍历攻击。

## 5. 记忆管理功能

### 5.1 /remember 技能
提供专门的技能来审查和组织记忆：
- 分析当前记忆景观
- 建议将临时记忆提升到永久配置文件（CLAUDE.md, CLAUDE.local.md）
- 检测重复、过时和冲突的记忆条目

### 5.2 记忆整理
- 自动检测重复条目
- 识别过时内容
- 建议合并相似记忆

## 6. 记忆系统的优势

1. **持久性**: 记忆在会话间保持，提供了长期的上下文连续性
2. **结构性**: 使用分类和元数据，便于管理和检索
3. **自动化**: 后台自动提取重要信息
4. **安全性**: 严格的访问控制和路径验证
5. **可扩展性**: 支持团队记忆和私有记忆
6. **智能检索**: 基于AI的相关性匹配

## 7. 与上下文压缩的关系

记忆系统与上下文压缩机制紧密协作：
- 重要的对话内容被提取为结构化记忆
- 在上下文压缩时，关键信息不会丢失
- 压缩后的对话可以引用相关记忆
- 维持长期上下文而不受令牌限制影响

这种设计使得Claude Code能够在长期、复杂的开发任务中维持高效的上下文管理，同时确保重要信息得以保存和复用。