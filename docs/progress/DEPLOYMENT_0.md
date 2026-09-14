# Deployment 0 交付记录：第一次线上部署

## 目标

在 AI 与图谱开发前证明 Vercel、Railway、Neon 和浏览器之间的最小公网链路可用，提前解决部署问题。

## 平台信息

| 平台 | 角色 | 项目名称 | 公网 URL | Root Directory |
|------|------|----------|----------|----------------|
| Neon | PostgreSQL + pgvector | `zhibian` | （内部连接） | — |
| Railway | FastAPI 后端 | `zhibian-api` | *待填写* | `apps/api` |
| Vercel | Next.js 前端 | `zhibian-web` | *待填写* | `apps/web` |

### 部署 Commit

- Branch: `feat/zhibian-mvp`
- Commit: *待填写*
- Migration 版本: `0001_core`

### 环境变量

| 平台 | 变量名 | 值 |
|------|--------|-----|
| Railway | `APP_MODE` | `mock` |
| Railway | `DATABASE_URL` | Neon 连接串（不在此记录完整值） |
| Railway | `CORS_ORIGINS` | Vercel 公网 URL |
| Vercel | `NEXT_PUBLIC_API_URL` | Railway 公网 URL |

> **注意**：真实 Secret（ZHIHU_ACCESS_SECRET、LLM_API_KEY 等）**未配置**，
> 部署仅使用 mock 模式。真实密钥仅在用户明确授权后配置。

## 执行的步骤

### 1. Neon 数据库创建
- *待填写*：创建项目、获取连接串

### 2. Railway 部署 apps/api
- *待填写*：创建项目、配置构建命令、启动命令、环境变量
- Pre-deploy 命令: `alembic upgrade head`
- 启动命令: `sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"`

### 3. Vercel 部署 apps/web
- *待填写*：创建项目、配置 Framework Preset、环境变量

### 4. 链路验证
- *待填写*：Browser → Web → API → DB 完整链路

## 验收结果

| 检查项 | 状态 | 说明 |
|--------|------|------|
| `alembic upgrade head` 成功 | ⏳ | *待验证* |
| Railway 构建成功 | ⏳ | *待验证* |
| Vercel 构建成功 | ⏳ | *待验证* |
| `GET /api/health` 返回 API+DB 可用 | ⏳ | *待验证* |
| 浏览器无 CORS 错误 | ⏳ | *待验证* |

## 已知限制

1. **mock 模式**：部署使用 `APP_MODE=mock`，不调用真实知乎或 LLM。
2. **Job 处理**：当前提交 Query 后 Job 停留在 `pending` 状态（Stage 4-6 实现异步处理）。
3. **数据持久**：Neon 数据库已创建，但业务表数据暂未写入（等待 Stage 4 集成）。
4. **CORS**：仅允许 Vercel 公网 Origin，不允许 `*`。

## 下一阶段入口

**Stage 4** — AI 结构化提取（Claim 生成与证据校验）。
