# CLAUDE.md - Offer-Catcher Frontend Project Guidelines

<role>
你是本项目的 AI 编码协作助手，专注于前端开发。

核心能力：
- Next.js App Router 开发经验
- React + Ant Design 组件开发
- TypeScript 类型系统
- API 客户端设计与错误处理

行为边界：
- 写代码前理解组件职责和数据流
- 遵循既有组件模式和样式约定
- API 调用必须正确传递 X-User-Id header
</role>

---

<architecture>
前端采用 Next.js App Router 架构：

| 目录 | 职责 |
|------|------|
| `app/` | 页面路由 (chat, interview, extract, questions, favorites, dashboard) |
| `components/` | 共享组件 (MainLayout, VoiceInput) |
| `lib/api.ts` | API 客户端，统一处理请求和 header |
| `types/index.ts` | TypeScript 类型定义 |

后端仓库：`~/OfferCatcher` (Java Spring Boot)
后端 API 基础路径：`/api/v1`（通过 Next.js rewrites 代理）
</architecture>

---

<multi_user>
多用户隔离机制：

- 所有需要用户数据的接口必须传递 `X-User-Id` header
- `getUserId()` 函数自动生成/获取用户 UUID
- 用户数据隔离：对话、面试会话、提取任务、收藏、记忆

**需要 X-User-Id 的接口**：
- `/conversations/*`
- `/chat/stream`
- `/interview/sessions/*`
- `/extract/tasks/*`
- `/favorites/*`
- `/memory/me/*`
- `/questions` (列表、删除)
- `/search`
</multi_user>

---

<coding_rules>
开发规范：

**类型约束**
- 所有 API 响应必须有 TypeScript 类型
- 禁止裸 `any`，使用 `unknown` 或具体类型

**API 调用**
- 使用 `lib/api.ts` 导出的函数，不直接 fetch
- 流式接口用 `chatStream()` 等专用函数
- 错误处理：统一用 Ant Design message 组件

**组件开发**
- 页面组件放 `app/` 目录
- 共享组件放 `components/` 目录
- 使用 Ant Design 组件库
- 样式用 inline style 或 Tailwind CSS

**Import 规范**
- 所有 import 放模块顶部
- 使用 `@/` 别名引用 src 目录
</coding_rules>

---

<development>
```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务
npm run dev

# 构建
npm run build
```

后端服务地址配置（`.env` 或环境变量）：
- `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1`
</development>