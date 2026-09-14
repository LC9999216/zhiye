# Stage 2 交付记录：ZhihuSearchProvider

## 目标

将知乎官方 HTTP 响应稳定映射为内部 DTO，并完成搜索结果的固定规范化流水线。

## 完成的任务

1. 实现 `ZhihuSearchProvider`：Bearer 鉴权、秒级 `X-Request-Timestamp`、受控 HTTPS endpoint、查询长度限制、超时、响应体上限和单进程并发限制。
2. 实现知乎响应 Schema、错误码映射、脱敏日志，以及连接超时和 HTTP 5xx 的单次重试。
3. 实现固定流水线：只保留 `ContentType == "Answer"`，按 `ContentID` 去重，按 `VoteUpCount` 降序排序，最多保留 10 条，并清洗 `ContentText` 高亮标签。
4. 实现 `MockSearchProvider`，使用合成 fixture 覆盖正常结果、空结果、鉴权失败、限流和未知错误。
5. 实现搜索服务层，保证业务层只依赖内部 DTO，不直接依赖知乎字段大小写。

## 测试结果

| 命令 | 结果 | 说明 |
|---|---|---|
| `pytest apps/api/tests` | 41 passed | Provider、Pipeline、错误映射和 Stage 1 health 测试 |
| `vitest run` | 3 passed | Stage 1 Web 基础页面测试 |
| `tsc --noEmit` | 0 errors | Web TypeScript 类型检查 |
| `git diff --check` | passed | 提交前空白检查 |

## 修改文件

- `apps/api/app/core/exceptions.py`
- `apps/api/app/schemas/zhihu.py`
- `apps/api/app/services/zhihu_provider.py`
- `apps/api/app/services/mock_search_provider.py`
- `apps/api/app/services/search_service.py`
- `apps/api/tests/test_zhihu_provider.py`
- `apps/api/tests/test_zhihu_pipeline.py`
- `database/fixtures/zhihu_search/` 下的错误与空结果 fixture
- `.gitignore`

## 已知限制

1. 本阶段测试使用脱敏合成 fixture，不在自动化测试中调用真实知乎 API。
2. PostgreSQL 集成测试尚未运行；数据库模型仍处于 Stage 1 的占位状态。
3. AI 提取、持久化、图谱 API 和前端搜索联动属于后续 Stage。

## 真实知乎 API 验证

Stage 0 已对 3 个自然语言问题执行 6 次真实 API 调用，验证通过 `Code=0` 以及 `ContentText`、`VoteUpCount`、`Url`、`ContentID` 字段契约。本阶段未重复进行真实接口调用。

## 下一阶段入口：Stage 3 — 数据库与分析 Job

实现 Query、Answer、Claim、Concept 等业务数据的持久化、幂等写入和迁移验证。
