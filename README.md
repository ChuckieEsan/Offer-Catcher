# Offer-Catcher Frontend: 面经智能体系统前端

**版本**: v3.0
**后端仓库**: `~/OfferCatcher` (Java Spring Boot)

---

## 项目简介

Offer-Catcher 前端是面经智能体系统的用户界面，基于 Next.js App Router 构建，提供：

- **AI 对话**: 与 AI 进行智能对话，支持面经提取、题目搜索
- **模拟面试**: 选择岗位和题目数量进行模拟面试练习
- **面经导入**: 上传文本或图片，异步提取题目并入库
- **题库管理**: 查看、编辑、删除已录入的题目
- **收藏管理**: 收藏重点题目，便于复习
- **数据仪表盘**: 查看统计数据和考频分析
- **记忆系统**: 管理用户偏好和行为记忆

---

## 多用户隔离

系统支持多用户数据隔离：
- 前端自动生成用户 UUID（存储在 localStorage）
- 所有用户数据接口传递 `X-User-Id` header
- 用户数据隔离：对话、面试会话、提取任务、收藏、记忆

---

## 技术栈

| 类别 | 技术 |
|------|------|
| 框架 | Next.js 15 (App Router) |
| UI 库 | React 19 |
| 组件库 | Ant Design 5 |
| 样式 | Tailwind CSS |
| 类型 | TypeScript |
| HTTP | Axios |

---

## 项目结构

```text
frontend/
├── src/
│   ├── app/                    # App Router 页面
│   │   ├── chat/               # AI 对话
│   │   ├── interview/          # 模拟面试
│   │   ├── practice/           # 刷题练习
│   │   ├── questions/          # 题库管理
│   │   ├── extract/            # 面经导入
│   │   ├── favorites/          # 收藏管理
│   │   ├── dashboard/          # 数据看板
│   │   ├── memory/             # 记忆系统
│   │   └── page.tsx            # 首页
│   │
│   ├── components/             # 共享组件
│   │   ├── MainLayout.tsx      # 主布局
│   │   └── VoiceInput.tsx      # 语音输入
│   │
│   ├── lib/
│   │   └── api.ts              # API 客户端
│   │
│   └── types/
│   │   └── index.ts            # TypeScript 类型
│   │
│   └── app/
│       ├── globals.css         # 全局样式
│       └── layout.tsx          # 根布局
│
├── public/                     # 静态资源
├── package.json
├── tsconfig.json
├── next.config.ts
└── .env.example
```

---

## 快速开始

### 环境要求

- Node.js 18+
- npm 或 pnpm

### 1. 安装依赖

```bash
cd frontend
npm install
```

### 2. 配置环境变量

```bash
cp .env.example .env.local
# 编辑 .env.local，配置后端地址
```

默认配置：
```
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

### 3. 启动开发服务

```bash
npm run dev
```

访问 http://localhost:3000。

### 4. 构建

```bash
npm run build
npm run start
```

---

## API 接口

前端通过 Next.js rewrites 代理连接后端，主要接口：

### 对话
- `GET /api/v1/conversations` - 获取对话列表
- `POST /api/v1/conversations` - 创建对话
- `POST /api/v1/chat/stream` - 流式聊天 (SSE)

### 面试
- `POST /api/v1/interview/sessions` - 创建面试会话
- `GET /api/v1/interview/sessions` - 获取会话列表
- `POST /api/v1/interview/sessions/{id}/answer` - 提交答案

### 面经提取
- `POST /api/v1/extract/submit` - 提交解析任务
- `GET /api/v1/extract/tasks` - 获取任务列表
- `POST /api/v1/extract/tasks/{id}/confirm` - 确认入库

### 题目
- `GET /api/v1/questions` - 题目列表
- `GET/PUT/DELETE /api/v1/questions/{id}` - 单题操作
- `POST /api/v1/questions/{id}/regenerate` - 重新生成答案

### 其他
- `GET /api/v1/stats/overview` - 统计总览
- `POST /api/v1/favorites` - 收藏管理
- `GET /api/v1/memory/me` - 记忆系统

---

## 开发规范

参见 [CLAUDE.md](CLAUDE.md)。

---

## License

MIT