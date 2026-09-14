# Stage 6 — 三栏 Web 界面

## 状态
- [x] 已完成（开发验证 + 自动化验收通过；人工浏览器验收待用户执行）
- 分支：`feat/zhibian-mvp`
- 前置：Stage 5 通过；Query/Answer/Graph/Job API 稳定

## 目标
让用户看到真实数据并完成主要浏览动作：桌面优先三栏布局，左栏问题输入 + Job 进度 + 回答列表，中栏 Sigma.js 知识图谱，右栏禁用的 AI 面板骨架 + 选中节点上下文预览。

## 任务与完成情况

### 1. API 客户端（`lib/api.ts`）
- 新增 `AnalyzeResponse` / `JobResponse` / `AnswerItem` / `AnswersResponse` / `GraphNode` / `GraphEdge` / `GraphResponse` 类型（与后端 DTO 对齐）
- `api.analyze` / `api.getJob` / `api.getAnswers` / `api.getGraph` 方法
- 复用统一错误处理（`ApiError`：网络层/HTTP/后端 error_code 映射）

### 2. 状态机（`stores/search.ts`）
- `submit()`：POST analyze → 轮询 Job（1.2s 间隔，180s 超时）→ completed 后并行拉取 answers + graph
- status 覆盖 idle/submitting/pending/fetching/analyzing/building/completed/failed
- 选中节点 / 激活概念 / 选中回答状态供三栏联动

### 3. 左栏（SearchForm + AnswerList）
- 问题输入（maxLength 200，Enter 提交，busy 时禁用）+ Job 进度提示（role=status）
- 最多 10 条回答，按 VoteUpCount 降序；显示标题/作者/赞同数/内容摘要
- 原文链接 `target="_blank" rel="noopener noreferrer"`（URL 来自保存的 Answer）
- Concept 过滤（activeConcept 按文本包含过滤 + 清除按钮）

### 4. 中栏（GraphPanel，Sigma.js）
- 动态加载 graphology + sigma（jsdom/SSR 环境不渲染，浏览器才加载）
- 节点颜色按类型（QUERY slate / ANSWER blue / CLAIM emerald / CONCEPT amber），Answer 大小随赞同数对数缩放
- 确定性环形布局（无外部布局依赖，避免新增依赖）
- zoom/drag/hover/click 由 Sigma 内置；点击 ANSWER/CLAIM 安全打开原文，点击 CONCEPT 过滤左栏，点击空白取消选中
- 图例 + 空态占位

### 5. 右栏（ContextPanel）
- 禁用的 AI 面板骨架，按钮 disabled，明确显示「AI 问答将在 Stage 8 启用」
- 选中节点上下文预览：类型/名称/赞同数/作者/立场/摘要/置信度/出现次数
- 本阶段不调用 `/api/chat`，不展示伪 Citation

### 6. 错误态
- ErrorBanner：识别常见错误码（QUERY_NOT_FOUND/JOB_FAILED/SERVER_RESTART/NETWORK_ERROR）给出可行动提示，通用错误显示原始消息，重试按钮
- 空结果态（左栏"暂无回答"、中栏"图谱将在分析完成后显示"）
- 固定范围提示始终可见（MVP 契约，不藏在帮助页）

## 后端配套修复（Stage 6 开发中发现）
1. **`build_answers_response` MissingGreenlet bug**：`len(a.claims)` 触发 async lazy load 崩溃；改为单条聚合查询 claim 计数（消除 N+1 与 await 问题）。
2. **Settings env_file 路径**：`("../.env")` 从 apps/api 运行时解析到 apps/.env（不存在），根目录 .env 读不到导致 DATABASE_URL 回退 localhost；补 `"../../.env"`，API 运行时能正确连 Neon。
3. **db/session.py SSL**：asyncpg 不认 URL 里 `?ssl=require`；改 `connect_args={"ssl": ssl.create_default_context()}`；健康检查超时 2s→5s（Neon 冷启动 TLS 握手）。
4. **MockSearchProvider**：新增 `MOCK_SEARCH_FIXTURE` 环境变量覆盖默认 fixture；新增 `mock_demo_closed_loop.json`（5 条 Answer，content_id 对齐 ai_analysis fixture，产出 6 claims + 2 concepts 的完整演示闭环）。默认 fixture 不变，测试契约不受影响。

## 自动化验收结果（真实运行）

### 前端（apps/web）
| 命令 | 结果 |
|---|---|
| `vitest run` | **24 passed**（page 6 + components 18） |
| `eslint .` | 0 errors |
| `tsc --noEmit` | 0 errors |
| `next build` | 编译 + TS + 静态生成全过 |

覆盖：排序稳定、最多 10 条、noopener,noreferrer 安全链接、Concept 过滤、空态、错误态（已知码/通用）、固定提示、键盘可达（按钮 focus）、AI 面板禁用、节点详情提取、合成 fixture 三栏显示。

### 后端（apps/api）
| 命令 | 结果 |
|---|---|
| `pytest tests/ -q`（非 PG） | 224 passed, 4 skipped |
| `pytest test_zhihu_provider.py` | 11 passed |
| `pytest test_pg_integration.py + test_graph_api.py` | 全绿（首跑 2 个因 Neon 网络抖动失败，重跑通过） |

### 端到端（本地 API + web dev）
- `POST /api/queries/analyze` → Job `fetching→analyzing→building→completed` 跑通
- 演示 fixture 提交「考研与就业怎么选」：5 answers（512/256/128/96/64 降序）+ 6 claims + 2 concepts；图谱 14 节点 20 边（RETURNS_ANSWER 5 / MAKES_CLAIM 6 / REFERS_TO 7 / SIMILAR_TO 2）
- `GET /api/health`：`{"status":"ok","db":"connected"}`
- CORS 允许 `http://localhost:3000`
- web dev SSR 渲染三栏 + 固定提示

## 人工验收（待用户，Chrome 1440×900）
执行方案要求：提交问题 → 查看列表 → 拖拽图谱 → 选择节点 → 打开原文；页面无横向溢出；固定提示无需打开帮助页可见。当前开发机可跑：`apps/api` 起 API（`MOCK_SEARCH_FIXTURE=mock_demo_closed_loop.json`），`apps/web` 起 dev（`NEXT_PUBLIC_API_URL=http://localhost:8000`），浏览器打开 http://localhost:3000。

## 已修改文件
- `apps/web/lib/api.ts`（Stage 6 客户端 + 类型）
- `apps/web/stores/search.ts`（提交 + 轮询 + 图谱状态）
- `apps/web/components/SearchForm.tsx` / `AnswerList.tsx` / `GraphPanel.tsx` / `ContextPanel.tsx` / `ErrorBanner.tsx`（新）
- `apps/web/app/page.tsx`（三栏组装）
- `apps/web/tests/page.test.tsx` / `components.test.tsx`（新/重写）
- `apps/web/tests/setup.ts`（RTL cleanup）
- `apps/web/vitest.config.ts`（preserveSymlinks）
- `apps/api/app/services/query_service.py`（claim 计数聚合）
- `apps/api/app/core/config.py`（env_file ../../.env）
- `apps/api/app/db/session.py`（SSL + 5s 超时）
- `apps/api/app/services/mock_search_provider.py`（MOCK_SEARCH_FIXTURE）
- `database/fixtures/zhihu_search/mock_demo_closed_loop.json`（新）

## 已知限制与风险
1. **真实知乎 API 未验证**：演示用 mock 搜索 + mock AI；未发起真实搜索/LLM。
2. **真实语义 Embedding 未接入**：SIMILAR_TO 边基于 mock embedding（同文本才相似），演示中 2 条边为占位结果。
3. **人工浏览器验收未执行**（需 Chrome 1440×900）；自动化已覆盖组件与 API 闭环。
4. **Neon 网络抖动**：PG 测试偶发超时，重跑可过。
5. **公网部署未验证**：web 指向 Railway 生产 API 的配置未改动；本地演示需 NEXT_PUBLIC_API_URL 覆盖。

## MVP Freeze 前置
执行方案：人工验收通过后记录一个可回滚 commit/tag 候选，锁定 Stage 3–6 演示路径、三个预置问题和缓存数据。**人工验收通过后执行 `git tag mvp-freeze-candidate`**，未验收前不冻结。

## 下一阶段入口
- Stage 7（P1）：回答列表/图谱/上下文双向联动；仅剩时间时跳过直接进 Stage 9。
- Stage 8（P1）：Graph-enhanced RAG + 可点击 Citation（需 LLM 预算明确）。
- Stage 9：总验收、3 个预置问题、启动与故障排查文档。
