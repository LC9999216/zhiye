# Stage 6 真实体验版补验

## 当前状态

本地真实 Provider、体验码保护、数据模式隔离、持久化预算预占、部分失败警告
和 15 分钟任务/轮询上限已实现。真实 Secret 尚未写入，未调用真实知乎、DeepSeek
或火山接口，未执行线上 migration 和公网发布。

预算检查在搜索完成后执行；预算不足、计价缺失或无法证明上界安全时，Job 进入
`completed_partial`，保留已保存的知乎回答和基础图谱供浏览，并显示可行动的预算错误。

## 接入配置

- DeepSeek：`https://api.deepseek.com` / `deepseek-flash` / JSON mode / thinking disabled。
- 火山方舟：`https://ark.cn-beijing.volces.com/api/v3` /
  `doubao-embedding-vision-251215` / 2048 维。
- Agent Plan `/api/plan/v3` 不作为网站后端调用端点。
- production 会在知乎搜索完成后根据实际回答数、摘要长度、最大重试次数和配置的模型单价计算保守单次上界；单价未配置或上界不能在 18 元预占额度内证明安全时，拒绝发起模型调用。`BUDGET_RESERVATION_CNY` 仅保留为旧配置兼容项，不参与运行时计算。

## 本地验证

- API pytest：全套通过；依赖专用 PostgreSQL 的测试按现有仓库配置跳过，不能视为 Neon 验收。
- Alembic 离线 SQL：`0001_core → 0002_composite_fk → 0003_claim_concepts_json → 0004_real_api_controls` 生成成功。
- Web lint、typecheck、Vitest 和 Next build 通过。
- Chrome 公网验收、真实接口验证、公网部署验证尚未完成。
- 可重复浏览器入口：`python scripts/stage6_browser_e2e.py`；需要先启动 Web/API，
  production 另设 `STAGE6_INVITE_CODE`。当前未在本地运行，因为本机没有可用的
  PostgreSQL/真实 Provider 配置。

## 发布前停止点

必须先核对线上 commit 和 migration 版本、准备可验证数据库备份，再单独获得
真实 Secret 写入、线上 migration 和公网发布授权。回退时先关闭真实任务入口，
不自动降级数据库或删除真实结果。当前数组向量列仍保留，pgvector 原生列验收
仍是独立差距。
