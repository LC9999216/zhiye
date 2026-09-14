# Deployment 0 交付记录：第一次线上部署

## 目标

在 AI 与图谱开发前证明 Vercel、Railway、Neon 和浏览器之间的最小公网链路可用，提前解决部署问题。

## 平台信息

| 平台 | 角色 | 项目名称 | 公网 URL | Root Directory |
|------|------|----------|----------|----------------|
| Neon | PostgreSQL + pgvector | `zhibian` | （内部连接） | — |
| Railway | FastAPI 后端 | `zhiye-production` | `https://zhiye-production.up.railway.app` | `apps/api` |
| Vercel | Next.js 前端 | `zhiye-one` | `https://zhiye-one.vercel.app` | `apps/web` |

### 部署 Commit

- Branch: `feat/zhibian-mvp`
- Commit: `7109af9`（Alembic async 配置修复）
- Migration 版本: `0001_core`

### 环境变量

| 平台 | 变量名 | 值 |
|------|--------|-----|
| Railway | `APP_MODE` | `mock` |
| Railway | `DATABASE_URL` | Neon 连接串（不在此记录完整值） |
| Railway | `CORS_ORIGINS` | `http://localhost:3000,https://zhiye-one.vercel.app` |
| Vercel | `NEXT_PUBLIC_API_URL` | `https://zhiye-production.up.railway.app` |
| 根目录 `.env` | `DATABASE_URL`, `APP_MODE=mock`, `RAILWAY_PUBLIC_URL`, `VERCEL_PUBLIC_URL`, `CORS_ORIGINS` | 已配置（未提交） |

> **注意**：真实 Secret（ZHIHU_ACCESS_SECRET、LLM_API_KEY 等）**未配置**，
> 部署仅使用 mock 模式。真实密钥仅在用户明确授权后配置。

## 执行的步骤

### 1. Neon 数据库创建
- 用户通过 Neon 控制台创建，已接入 Railway。

### 2. Railway 部署 apps/api
- 用户通过 Railway Dashboard 部署 GitHub 仓库 `apps/api`。
- 启动时自动执行 `alembic upgrade head`（migration 0001_core 成功创建全部 8 张表）。
- **端口问题与修复**：容器监听 `8080`（Railway 注入的 `PORT`），但 Railway Networking 端口最初配置为 8000 导致 502。
  修复：Railway Dashboard → Networking → Port 改为 `8080`。
- **Alembic 配置修复**：`env.py` 现在从 `app.core.config.settings.database_url` 读取 URL
  （async engine + run_sync），不再依赖 `alembic.ini` 中的占位符。

### 3. Vercel 部署 apps/web
- 用户通过 Vercel Dashboard 部署 GitHub 仓库 `apps/web`，配置 `NEXT_PUBLIC_API_URL`。

### 4. 链路验证（2026-09-14，实际执行）

| 检查项 | 结果 | 说明 |
|--------|------|------|
| `GET /api/health` | ✅ 200 | `{"status":"ok","version":"0.1.0","mode":"mock","db":"connected"}` |
| `GET /openapi.json` | ✅ 200 | 5 个路由全部注册 |
| `POST /api/queries/analyze` | ✅ 202 | 返回 job_id + query_id + job_url |
| `GET /api/jobs/{id}` | ✅ 200 | `status: pending`, `current_step: Queued for processing` |
| `GET /api/queries/{id}` | ✅ 200 | query 元数据正确 |
| `GET /api/queries/{id}/answers` | ✅ 200 | `answers: [], total: 0`（Job 未处理，预期） |
| CORS GET（Vercel origin） | ✅ 200 | `access-control-allow-origin: https://zhiye-one.vercel.app` |
| CORS Preflight | ✅ 200 | 允许 POST 方法 |
| Vercel 前端 | ✅ 200 | 知辨标题 + 固定提示均渲染 |

## 验收结果

| 检查项 | 状态 | 说明 |
|--------|------|------|
| `alembic upgrade head` 成功 | ✅ | 日志显示 `Running upgrade -> 0001_core`，jobs 表可写入 |
| Railway 构建成功 | ✅ | 容器启动，Uvicorn 监听 8080 |
| Vercel 构建成功 | ✅ | 前端 200，标题与提示正确 |
| `GET /api/health` 返回 API+DB 可用 | ✅ | `db: connected` |
| 浏览器无 CORS 错误 | ✅ | 预检与 GET 均正确返回 CORS 头 |

## 已知限制

1. **mock 模式**：部署使用 `APP_MODE=mock`，不调用真实知乎或 LLM。
2. **Job 处理**：当前提交 Query 后 Job 停留在 `pending` 状态（Stage 4-6 实现异步处理）。
3. **数据持久**：Neon 数据库已创建，migration 已执行；业务数据待 Stage 4 集成。
4. **CORS**：仅允许 Vercel 公网 Origin + localhost:3000，不允许 `*`。
5. **query_text 中文编码**：验证时终端显示乱码，实际存储为 UTF-8 正常（API 返回与数据库一致）。

## 下一阶段入口

**Stage 4** — AI 结构化提取（Claim 生成与证据校验）。
