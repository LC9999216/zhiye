# Stage 0 交付记录：知乎数据可行性门

## 目标

在不搭建应用功能前，用只读调用和独立审计证明官方数据契约可用，确认知乎搜索 API 能稳定返回所有必需字段。

## 实施的步骤

1. **安装 zhihu-cli**：从官方 CDN 下载并安装 zhihu-cli 0.6.0-beta.20260908125143。
2. **配置 Access Secret**：使用用户提供的 Secret 完成鉴权配置。
3. **确认 HTTP API 可用性**：通过 Python `requests` 库成功调用官方 HTTP API，确认 Bearer 鉴权有效（PowerShell 和 curl.exe 在 Windows 上因工具链问题不可靠，但 Python 正常）。
4. **执行 3 个测试问题 × 2 次调用**：通过 CLI 和 HTTP API 分别保存了响应。
5. **字段审计**：验证所有必需字段完整性。

## 测试问题

1. **Q1 — 常见问题**：`计算机专业考研还是就业`
2. **Q2 — 可能混合类型的问题**：`如何评价 DeepSeek R1 模型`
3. **Q3 — 可能冷门的问题**：`量子计算密码学应用前景`

## 审计结果

| 测量项 | Q1 | Q2 | Q3 | 要求 |
|---|---|---|---|---|
| Code | 0 (success) | 0 (success) | 0 (success) | 0 |
| Total Items | 10 | 10 | 10 | — |
| Answers | 7 | 2 | 4 | 0-10 |
| Articles | 3 | 8 | 6 | — |
| 缺失必需字段 (ContentID/ContentText/Url/VoteUpCount) | 0 | 0 | 0 | 0 |
| 重复 ContentID | 0 | 0 | 0 | 0 |
| ContentText 最小长度 | 437 | 1006 | 406 | >0 |
| ContentText 平均长度 | 668 | 1022 | 859 | — |
| 含 /answer/ URL 比例 | 7/7 (100%) | 2/2 (100%) | 4/4 (100%) | 100% |

## 交付物

### 不提交到仓库的真实响应（已保存在 `.local/zhihu-fixtures/`）

- `response_q1_call1_raw.json` / `response_q1_call2_raw.json` — CLI 输出
- `response_q2_call1_raw.json` / `response_q2_call2_raw.json` — CLI 输出
- `response_q3_call1_raw.json` / `response_q3_call2_raw.json` — CLI 输出
- `http_q1.json` / `http_q2.json` / `http_q3.json` — HTTP API 输出的结构相同响应
- `verify_http_api.py` — 验证脚本（仅用于 Stage 0，后续不使用）

### 提交到仓库的合成 fixture（`database/fixtures/zhihu_search/`）

将在 Stage 1 创建，基于官方 Schema 构造确定性合成数据。

## HTTP API 鉴权说明

- **Python `requests` 库**可以正常使用 Bearer 鉴权：`Authorization: Bearer <secret>` + `X-Request-Timestamp` + `Content-Type: application/json`
- **Windows PowerShell `Invoke-WebRequest` 和 `curl.exe`**返回 `Code=20001`（鉴权失败），原因尚不明确（可能与 TLS 实现或 HTTP/2 有关），但 CLI 和 Python 均可正常工作。
- 正式 FastAPI 服务使用 Python `httpx` 或 `requests` 库直接调用 HTTP API，因此该差异不影响实现。
- CLI 0.6.0 内部使用相同的 Bearer 鉴权，成功调用了所有搜索。

## 停止条件检查

| 条件 | 结果 |
|---|---|
| 官方接口能否稳定返回 ContentText、VoteUpCount、Url、ContentID？ | ✅ 全部 13 条 Answer 中 0 缺失 |
| 凭证/额度是否可用？ | ✅ 知乎搜索剩余 5000/5000 次 |
| 是否需要网页抓取或私有 API？ | ❌ 不需要，官方 HTTP API 和 CLI 均可正常工作 |
| 是否需要登录态或特殊权限？ | ❌ 不需要，Bearer 鉴权即可 |

## 结论

**Stage 0 通过。** 官方知乎搜索 HTTP API (`GET /api/v1/content/zhihu_search`) 能以 `Count=10` 返回含 `Answer` 和 `Article` 的混合结果，所有必需字段（`ContentID`、`ContentText`、`Url`、`VoteUpCount`、`ContentType`）均完整返回。`Url` 包含 `/answer/` 路径，可在浏览器打开原文。

## 已知限制

1. 当前样本仅 3 个问题各 2 次调用，不承诺长期稳定性或结果集合稳定性。
2. HTTP API Bearer 鉴权在 Windows PowerShell/curl.exe 上不工作（但 Python 正常），正式服务不受此影响。
3. 接口 `HasMore` 固定为 `false`，当前不支持分页（符合文档约定）。

## 下一阶段入口：Stage 1 — 工程初始化

建立可重复启动、可测试的 monorepo 基础：Next.js + FastAPI + PostgreSQL + Docker Compose。
