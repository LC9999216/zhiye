# Stage 1 交付记录：工程初始化

## 目标

建立可重复启动、可测试的 monorepo 基础：Next.js + FastAPI + PostgreSQL + Docker Compose。

## 完成的任务

1. **目录结构**：创建 `apps/web`、`apps/api`、`packages/contracts`、`database/fixtures`、`tests/e2e`。
2. **FastAPI 后端**（`apps/api`）：
   - `pyproject.toml`：Python ≥3.11, 依赖 fastapi, uvicorn, pydantic, sqlalchemy, asyncpg, alembic, httpx
   - `app/core/config.py`：Pydantic Settings 配置管理，`APP_MODE=mock` 默认
   - `app/db/session.py`：异步 SQLAlchemy engine/session
   - `app/models/base.py`：TimestampMixin（UUID id, created_at, updated_at UTC）
   - 6 个占位 model：query, answer, claim, concept, job, chat_message
   - `app/api/health.py`：GET /api/health 返回 mode, db 状态
   - `app/main.py`：CORS 中间件、lifespan、uvicorn
   - `tests/test_health.py`：3 个测试（基础结构、DB 不可用、DB 可用）
   - `Dockerfile`：多阶段构建
3. **Next.js 前端**（`apps/web`）：
   - `package.json`, `tsconfig.json`, `next.config.ts`, `tailwind.config.ts`
   - `app/layout.tsx` / `app/page.tsx`：三栏布局，包含固定"观点基于..."提示
   - `lib/api.ts`：API client types
   - `stores/search.ts`：Zustand 状态管理占位
   - `tests/page.test.tsx`：3 个测试（标题、固定提示、占位文本）
   - `vitest.config.ts`：测试配置
4. **Docker Compose**（根目录 `docker-compose.yml`）：PostgreSQL + pgvector + API + Web
5. **Alembic**：初始化为 database/migrations（配置待连接 PostgreSQL 后完成）
6. **合成 fixture**：`database/fixtures/zhihu_search/mock_mixed_answers.json` — 5 个项（4 Answer + 1 Article）
7. **`.env.example`**：完整环境变量文档，`APP_MODE=mock` 默认
8. **`.gitignore`**：忽略 .env、.venv、node_modules、.local 等

## 测试结果

| 命令 | 结果 | 说明 |
|---|---|---|
| `pytest apps/api/tests` (API) | 3 passed | health endpoint |
| `vitest run` (Web) | 3 passed | page component |
| `tsc --noEmit` (Web) | 0 errors | TypeScript strict |
| `python -m app.main` (API start) | ✅ 200 OK | mock mode, db: unavailable |

## 修改文件

- `.env.example`（创建）
- `apps/api/pyproject.toml`, `apps/api/Dockerfile`, `apps/api/.dockerignore`
- `apps/api/app/` — main.py, config.py, session.py, health.py, models, etc.
- `apps/api/tests/` — conftest.py, test_health.py
- `apps/web/package.json`, `tsconfig.json`, `next.config.ts`, `tailwind.config.ts`, etc.
- `apps/web/app/` — layout.tsx, page.tsx, globals.css
- `apps/web/lib/api.ts`
- `apps/web/stores/search.ts`
- `apps/web/tests/page.test.tsx`
- `database/fixtures/zhihu_search/mock_mixed_answers.json`
- `docker-compose.yml`

## 已知限制

1. **PostgreSQL 不可用**：本机未安装 Docker 或 PostgreSQL，集成测试无法运行。数据库相关的测试需要 Docker PostgreSQL 容器。mock 模式可以正常启动。
2. **Alembic 首条 migration 未生成**：需要连接 PostgreSQL 后执行 `alembic autogenerate`。
3. **ESLint 警告**：eslint-config-next 16.x 与 eslint 10.x 有 peer dependency 冲突（不影响功能）。

## 真实知乎 API 验证

未进行真实接口验证（Stage 0 已完成并验证通过）。

## 下一阶段入口：Stage 2 — ZhihuSearchProvider

实现 ZhihuSearchProvider，将官方 HTTP 响应稳定映射为内部 DTO。
