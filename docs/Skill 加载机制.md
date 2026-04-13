我想知道现在的 agent 是怎么做到 skill 的动态加载和卸载的？一旦 skill 被加载到上下文当中，还会被移除吗？

可以先把它理解成一种**分层、按需注入**，而不是“把所有 skill 一次性塞进上下文里”。公开资料里能确认的部分，大致是这样：

ChatGPT 会先持有每个 skill 的**元信息**，主要是名字和描述，用来判断“这时候该不该用这个 skill”。当它判断某个 skill 相关时，才会进一步读取该 skill 的 `SKILL.md` 主说明；再往下，脚本、参考资料、模板这类支持资源，也是**只在当前步骤确实需要时才继续读取或执行**。OpenAI 把这个机制描述成 **incremental / progressive loading**，目的就是节省上下文空间。([OpenAI Help Center][1])

所以你问的“动态加载”这一半，公开答案基本是：**是的，skill 不是全量常驻，而是按相关性逐步加载。** 这也解释了为什么 skill 设计文档会反复强调：`SKILL.md` 要短、小、像控制面；大块知识放到 references 里，需要时再读。因为 skill 和系统提示、对话历史、其他已激活的 skill，都是在**共享同一个上下文预算**。([OpenAI Academy][2])

至于“卸载”这一半，公开文档**没有把内部运行时的 eviction / unload 机制讲到实现细节**。没有看到官方说“加载后一定会在第 N 步移除”或者“会一直驻留到会话结束”。但从官方对 progressive loading 和 context efficiency 的描述，可以比较稳妥地推断：

* **skill 的元信息**大概率是持续可用的，用于后续继续判断要不要再用它。
* **skill 的完整说明和附加资源**并不保证会一直留在活跃上下文里；随着对话推进、上下文预算变化、当前任务焦点变化，它们很可能只是在需要时被重新取用，而不是永久占住窗口。这个结论是基于公开描述做的推断，不是 OpenAI 已公开披露的底层实现。([OpenAI Help Center][1])

换句话说，更接近下面这个模型：

1. **始终可见的路由层**：name / description
2. **命中后加载的控制层**：`SKILL.md`
3. **执行到某一步才加载的资源层**：脚本、参考文档、模板、资产
4. **是否继续保留在活跃上下文**：取决于后续相关性和上下文预算，官方没公开精确策略

你要是把它类比成 RAG / tool routing，会比较好理解：
它不像传统程序里 `import module` 以后就常驻内存不动；更像是**先保留索引，再按需取正文，再按需取附件**。

再直接回答你的两个问题：

**1. 现在的 agent 是怎么做到 skill 的动态加载和卸载的？**
公开可确认的是：靠 **skill 元信息做触发判断**，然后 **逐步加载 `SKILL.md` 和所需资源**。至于更底层到底是 prompt 拼接、上下文裁剪、还是内部调度缓存，官方没有公开到那个粒度。([OpenAI Help Center][1])

**2. 一旦 skill 被加载到上下文当中，还会被移除吗？**
公开资料没有明说“移除规则”，但从“共享上下文窗口”和“按需渐进加载”来看，**不能假设它会永久留在活跃上下文里**；更合理的理解是：**会按相关性被再次取用，而不是一直完整驻留。** 元信息更像常驻路由索引，详细内容更像临时工作集。([OpenAI Help Center][1])

如果你愿意，我可以继续往下讲一层：我可以把这个机制画成一个“agent 路由器 + skill 控制面 + 资源懒加载”的简化架构图。

[1]: https://help.openai.com/zh-hant-hk/articles/20001066-skills-in-chatgpt?utm_source=chatgpt.com "Skills in ChatGPT | OpenAI Help Center"
[2]: https://academy.openai.com/public/resources/skills?utm_source=chatgpt.com "Skills - Resource | OpenAI Academy"
