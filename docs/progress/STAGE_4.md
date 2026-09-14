# Stage 4 交付记录：AI 结构化提取

## 目标

对每条 Answer 的 `ContentText` 生成受约束的结构化观点：summary、stance、0–5 个带证据的 Claim、Claim Concepts 与 evidence_text；JSON Schema 校验 + 最多 2 次格式重试；代码层截断 Claim 数与证据子串校验；持久化追溯字段与 embedding。

## 完成的任务

### 1. AI 提取 Schema（`app/schemas/ai.py`）

- `RawExtractionDTO`：LLM 原始输出结构（summary、stance、claims[]）。
- `RawClaimDTO`：单条 Claim（text、evidence_text、confidence、concepts）。
- `ValidatedClaimDTO`：通过校验的 Claim，含 1-based `position`（ge=1, le=5）。
- `ClaimExtractionDTO`：最终结果，`claims` 硬上限 5（validator 截断）。
- `AnalysisFailureDTO`：单条 Answer 失败记录（error_code、message、attempts）。
- `StanceValue`：`support|oppose|conditional|neutral` 固定枚举。
- `MAX_CLAIMS_PER_ANSWER = 5`。

### 2. Prompt 模板（`app/services/prompts.py`）

- `build_analysis_prompt(content_id, content_text)`：指令 + `ANSWER_ID:` 标记行 + ContentText。
- `PROMPT_VERSION = "stage4-v1"`、`SCHEMA_VERSION = "ai-extraction-v1"`（持久化到 Answer）。

### 3. LLM Provider 隔离（`app/services/llm_provider.py`）

- `LLMProvider` Protocol：`async complete(prompt) -> str`。
- `MockLLMProvider`：从 `database/fixtures/ai_analysis/{content_id}.json` 读取确定性输出；未知 id 返回空分析（graceful）。
- `get_llm_provider()`：mock 模式 → Mock；production → NotImplementedError（真实 provider 后续接入）。

### 4. Embedding Provider 隔离（`app/services/embedding_provider.py`）

- `EmbeddingProvider` Protocol：`async embed_texts(texts) -> list[list[float]]`。
- `MockEmbeddingProvider`：SHA-256 种子确定性向量（同文本同向量，供 Stage 5 相似度）。
- `get_embedding_provider()`：mock → Mock。

### 5. ClaimExtractor（`app/services/claim_extractor.py`）

- `extract_json_object()`：解析 JSON，容忍 markdown code fence 与前后缀文字（提取最外层 `{}`）。
- `normalize_evidence()`：NFKC → 剥 `<em>` → 折叠空白。
- `evidence_is_substring()`：规范化后 evidence 是 ContentText 子串。
- `validate_and_cap()`：截断 ≤5，证据校验，重排 position。
- `extract_claims()`：调用 provider（最多 3 次 = 1 + 2 重试），失败抛 `ClaimExtractionError`（带 attempts）。
- 捕获 JSONDecodeError / ValidationError / ValueError / TypeError / TimeoutError / OSError。

### 6. AnalysisService（`app/services/analysis_service.py`）

- `analyze_answer()`：提取 → 生成 embedding → 事务替换该 Answer 的 Claim → 更新追溯字段。
- 追溯字段：`analysis_model`、`prompt_version`、`schema_version`、`analyzed_at`、`analysis_latency_ms`、`embedding`、`embedding_model`。
- 单条失败返回 `AnalysisFailureDTO`，不阻塞其他 Answer。
- `analyze_query_answers()`：批量分析，返回 (analysed, failures)。

### 7. ORM 补充

- `Answer`：补 `embedding`、`embedding_model` 列（与 migration 0001_core 的 `ARRAY(Float)` 匹配）。
- `Claim`：补 `embedding` 列。

### 8. 合成 Fixtures（36 个）

`database/fixtures/ai_analysis/`，由 `apps/api/database/fixtures/generate_ai_fixtures.py` 生成：

| 场景 | fixture 数 |
|---|---|
| 基础单/双 Claim | 7 |
| 三 Claim、五 Claim | 2 |
| 长文本（中间取证据） | 2 |
| 空 Claim | 2 |
| 恶意指令 | 2 |
| 脏 JSON（code fence / 前缀文字） | 2 |
| 空白/退化内容 | 2 |
| 不同 stance（support/oppose/conditional/neutral） | 4 |
| confidence 边界（0.2 / 1.0） | 2 |
| 概念多样性 | 2 |
| 高亮标签 | 1 |
| 额外长/边界场景 | 8 |

## 测试结果

| 文件 | 测试数 | 说明 |
|---|---|---|
| `test_ai_extraction.py` | 28 | JSON 解析、Schema、截断、证据、重试、超时、空数组、prompt |
| `test_ai_fixtures.py` | 40 | 30+ fixture 全量 Schema + 证据定位、脏 JSON、无第 6 Claim |
| `test_analysis_service.py` | 10 | provider 行为、embedding 确定性、happy/failure 路径 |
| `test_models.py` | +2 | embedding 列存在性 |

**全套件：130 passed, 5 skipped**（5 skipped = 需 PostgreSQL 的 DB 集成测试）。

`claim_extractor.py` 100% 分支覆盖；`schemas/ai.py` 100%。

## 阶段门禁检查

| 验收标准 | 状态 |
|---|---|
| 30 个合成 Answer fixture 通过 Schema | ✅ 36 个 fixture，全量通过 |
| 任何 Answer 不保存第 6 个 Claim | ✅ 代码截断 + DTO validator + DB CHECK |
| position 数据库约束拒绝 0 和 6 | ✅ DTO ge=1/le=5 + DB ck_claim_position_range |
| 每条已保存 Claim 证据可定位 | ✅ evidence_is_substring 全量校验 |
| 模型返回脏 JSON 有测试 | ✅ code fence / 前缀文字 |
| 空数组有测试 | ✅ a-empty-* + test_empty_array_output |
| 超时有测试 | ✅ TimeoutError × 3 → ClaimExtractionError |
| 部分失败有测试 | ✅ analyze_answer 返回 AnalysisFailureDTO 不阻塞 |
| 追溯字段保存 | ✅ analysis_model/prompt_version/schema_version/analyzed_at/latency_ms |

## 修改文件

### 新建
- `apps/api/app/schemas/ai.py` — AI 提取 DTO
- `apps/api/app/services/prompts.py` — Prompt 模板与版本
- `apps/api/app/services/llm_provider.py` — LLM Provider 协议 + Mock
- `apps/api/app/services/embedding_provider.py` — Embedding Provider 协议 + Mock
- `apps/api/app/services/claim_extractor.py` — 提取管线
- `apps/api/app/services/analysis_service.py` — 分析编排 + 持久化
- `apps/api/database/fixtures/generate_ai_fixtures.py` — fixture 生成器
- `database/fixtures/ai_analysis/*.json` — 36 个合成 fixture
- `apps/api/tests/test_ai_extraction.py` — 提取单元测试
- `apps/api/tests/test_ai_fixtures.py` — fixture 集成测试
- `apps/api/tests/test_analysis_service.py` — provider/持久化测试

### 修改
- `apps/api/app/models/answer.py` — 补 embedding/embedding_model
- `apps/api/app/models/claim.py` — 补 embedding
- `apps/api/app/schemas/__init__.py` — 导出 AI schema
- `apps/api/app/services/__init__.py` — 导出 provider 工厂
- `apps/api/tests/test_models.py` — embedding 列测试

## Migration

无新增 migration——Stage 3 的 `0001_core` 已含 `answers.embedding`、`claims.embedding`（`ARRAY(Float)`）与分析追溯字段。ORM 补充的列与 migration 完全匹配。

## 真实 LLM 验证

未进行真实 LLM 接口验证。本阶段全部使用 `MockLLMProvider`（确定性合成 fixture）。真实 OpenAI-compatible provider 尚未实现（`get_llm_provider()` 在 production 模式抛出 NotImplementedError）。

## 已知限制

1. **真实 LLM 未接入**：production 模式下 `get_llm_provider()` 抛 NotImplementedError；当前 MVP 用 mock 确定性输出。
2. **DB 集成测试跳过**：5 项需 PostgreSQL（事务替换、position 约束、复合外键）；CI/Neon 上启用。
3. **Mock embedding 无语义**：SHA-256 种子向量仅供 Stage 5 相似度逻辑测试，不代表真实语义相似。
4. **Job 编排未接入**：`analyze_query_answers` 已就绪，但尚未挂到 Job 状态机（fetching→analyzing→completed）；计划在 Stage 5/6 完成端到端。

## Stage 4 门禁收口（本会话追加）

在进入 Stage 5 前完成了 Stage 4 的三道门禁（执行方案 6.2）：

1. **PostgreSQL 门禁**：`tests/test_pg_integration.py`（9 项）在 Neon 直连下全部通过——查询幂等、Job 生命周期、Claim 事务替换、position 约束（0/6 拒绝）、复合外键拒绝跨 Query 写入。迁移 `0002_composite_fk` 补齐 `answers.embedding_model` + 5 个复合外键 + 3 个 `(query_id,id)` 唯一约束。
2. **真实样本门禁**：8 个手注真实答案 fixture（`database/fixtures/ai_analysis/<content_id>.json`，证据串逐一校验为真实 ContentText 子串）；真实样本覆盖率 8/13=61.5% ≥60%（脚本化校验 + `test_real_sample_valid_claim_coverage_above_60_percent` 自动化）。
3. **生产 Provider 门禁**：`TestProductionProviderGate`（4 项）验证 production 模式下 LLM/Embedding Provider 抛 `NotImplementedError`，mock 模式返回 mock 实例。

**本会话修复**：analysis_service 在删除旧 Claim 与插入新 Claim 之间补 `await session.flush()`，修复同事务内 `uq_claim_position` 唯一约束冲突（Claim 替换测试由此通过）。

## 下一阶段入口

**Stage 5** — 概念归一化与图谱构建（concepts/claim_concepts/answer_similarities 逻辑 + `/api/queries/{id}/graph`）。已完成，见 `STAGE_5.md`。
