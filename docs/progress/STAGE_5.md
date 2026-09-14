# Stage 5 — 知识图谱构建与 Graph API

## 状态
- [x] 已完成（开发验证）
- 分支：`feat/zhibian-mvp`
- 前置：Stage 4 门禁收口（PG 集成、真实样本、生产 Provider 门禁）已通过

## 目标
在 Stage 4 的结构化抽取之上，构建 `QUERY → ANSWER → CLAIM → CONCEPT` 知识图谱：
- 概念确定性规范化 + 别名合并（Query 内作用域）
- Concept 物化与 `claim_concepts` 关联（REFERS_TO 权威事实源）
- Answer 相似度（SIMILAR_TO，度数 ≤2，同 Query 内）
- Graph API 从业务外键派生节点/边
- Job 状态机闭环：fetch → analyze → build → completed

## 任务与完成情况

### 1. Schema：claims.concepts_json（migration 0003）
- 新增 `claims.concepts_json`（TEXT，存 JSON 数组字符串，如 `["考研","就业"]`）
- ORM `Claim.concepts_json` 同步；`analysis_service` 持久化每条 Claim 的原始概念名
- migration `0003_claim_concepts_json`（down_revision=`0002_composite_fk`），已应用到 Neon

### 2. 概念确定性规范化
- `app/services/concept_normalizer.py`：
  - `normalize_concept_name`：NFKC → 空白折叠 → casefold → trim（幂等）
  - `CONCEPT_METHOD_VERSION = "concept-normalize-v1"`
  - `CONCEPT_ALIASES` 别名表：跨语言缩写/同义（AI↔人工智能、LLM↔大语言模型、OS↔操作系统、CS↔计算机科学 等），`alias_group()` 提供确定性合并
- `app/services/concept_merger.py`：版本化阈值 `CONCEPT_SIMILARITY_THRESHOLD=0.88`、`CONCEPT_METHOD_VERSION="concept-cosine-v1"`

### 3. 图构建逻辑
- `app/services/graph_builder.py`：
  - `cosine_similarity`、`normalise_answer_pair`、`_add_edge_with_degree_limit`
  - `build_concepts`：读取 claims.concepts_json → 物化 `concepts` + `claim_concepts`（REFERS_TO）→ 别名合并 + embedding 余弦合并（阈值门控）
  - `build_answer_similarities`：同 Query Answer embedding 余弦 ≥0.82 → 候选按（相似度降序，id 升序）→ 两端当前无向度数 <2 才加边 → `(min,max)` 规范化存一次，记录 `embedding_model` + `method_version="answer-cosine-v1"`
  - 幂等：重复构建不重复插入（concepts 复用、claim_concepts 去重、similarity 不重复）

### 4. Graph API
- `app/services/graph_service.py`：`build_graph_response` 从 `answers.query_id`/`claims.answer_id`/`claim_concepts`/`answer_similarities` 派生节点/边
- `GET /api/queries/{id}/graph` 路由；`GraphNode`/`GraphEdge`/`GraphResponse` schema
- 节点类型仅 `QUERY/ANSWER/CLAIM/CONCEPT`；边类型仅 `RETURNS_ANSWER/MAKES_CLAIM/REFERS_TO/SIMILAR_TO`；主链完整
- ANSWER/CLAIM 节点携带知乎原文 URL（来源跳转）

### 5. Job 状态机闭环
- `app/services/job_processor.py`：`process_job` 编排 fetch → analyze → build → completed|failed
- `app/services/search_service.py`：`SearchPipeline.fetch_and_store`（provider 搜索 → 管线 → 持久化 Answer，按 (query_id, content_id) 幂等重建）
- `POST /api/queries/analyze` 通过 FastAPI `BackgroundTasks` 在单进程内执行 Job（符合 AGENTS.md「单进程后台任务 + 数据库 Job 状态」，不引入外部队列）
- 单条 Answer 分析失败不阻塞其他 Answer；Job 最终态记录 error_code/error_message

### 6. 人工标注集 + 阈值调优
- `database/fixtures/graph/annotation_pairs.json`：**30 个概念对**（18 similar + 12 not）+ **25 个 Answer 对**（15 similar + 10 not）
- `tests/test_graph_annotations.py`：验证误连 ≤5%、漏连 ≤20%
  - 概念：别名表 + 字符重叠（Jaccard），阈值 0.10–0.20 均达标
  - Answer：Jaccard，阈值 0.10–0.15 达标（0/0 于 0.10）
- 诚实说明：真实语义 Embedding 未接入（mock-only），生产阈值（0.88/0.82）为占位，接入真实 Embedding 后需用标注集重调

## 真实 fixture 暴露的契约修正
- 真实 Stage-0 响应 `RankingScore` 可达 ~1.9（>1.0），原 DTO `le=1.0` 约束错误
- `schemas/zhihu.py`：仅保留 `ge=0`，更新对应测试（接受 >1、拒绝负数）

## 验收测试结果（真实运行）

### 单元 / 逻辑测试
| 命令 | 结果 |
|---|---|
| `pytest tests/test_graph_builder.py -q` | 8 passed, 1 skipped |
| `pytest tests/test_graph_annotations.py -q` | 7 passed |
| `pytest tests/test_concept_normalizer.py -q` | 16 passed |
| `pytest tests/test_analysis_service.py -q` | 12 passed |
| `pytest tests/test_ai_fixtures.py -q` | 44 passed |
| `pytest tests/test_zhihu_provider.py -q` | 通过（含修正后的 ranking_score 测试） |
| `pytest tests/ -q`（非 PG 子集，不含 test_pg_integration/test_graph_api） | 224 passed, 4 skipped |

### PG 集成测试（Neon，TEST_DATABASE_URL/DATABASE_URL 直连）
| 命令 | 结果 |
|---|---|
| `pytest tests/test_pg_integration.py::TestGraphBuilding -v` | 4 passed |
| `pytest tests/test_pg_integration.py::TestJobProcessing -v` | 1 passed |
| `pytest tests/test_graph_api.py -v` | 2 passed |
| `pytest tests/test_pg_integration.py tests/test_graph_api.py -q` | 全绿（首跑因 Neon 网络抖动 2 个失败，重跑通过） |

### 静态检查
| 命令 | 结果 |
|---|---|
| `python -m compileall -q app tests` | exit 0 |
| import 冒烟（app.main + 新 services） | 全部 OK |

## Migration
- `0003_claim_concepts_json`：新增 `claims.concepts_json`
- 已应用至 Neon（`alembic_version = 0003_claim_concepts_json`）

## 已修改文件
- `apps/api/app/services/graph_builder.py`（新）
- `apps/api/app/services/graph_service.py`（新）
- `apps/api/app/services/job_processor.py`（新）
- `apps/api/app/services/concept_normalizer.py`（新）
- `apps/api/app/services/concept_merger.py`（新）
- `apps/api/app/services/search_service.py`（新增 fetch_and_store）
- `apps/api/app/services/analysis_service.py`（持久化 concepts_json）
- `apps/api/app/models/claim.py`（concepts_json 列）
- `apps/api/app/models/concept.py`（embedding 列）
- `apps/api/app/schemas/api.py`（GraphResponse 等）
- `apps/api/app/schemas/zhihu.py`（ranking_score 放宽）
- `apps/api/app/api/queries.py`（graph 路由 + BackgroundTasks）
- `apps/api/database/migrations/versions/0002_composite_fk.py`（新，Stage 4 收口）
- `apps/api/database/migrations/versions/0003_claim_concepts_json.py`（新）
- `apps/api/tests/test_graph_builder.py` / `test_graph_annotations.py` / `test_graph_api.py`（新）
- `apps/api/tests/test_pg_integration.py` / `test_concept_normalizer.py`（新）
- `apps/api/tests/test_zhihu_provider.py`（ranking_score 修正）
- `database/fixtures/graph/annotation_pairs.json`（新）
- `database/fixtures/ai_analysis/*.json`（8 个真实答案 fixture，Stage 4 收口）

## 已知限制与风险
1. **真实语义 Embedding 未接入**：相似度阈值（0.88/0.82）基于占位；接入真实 Embedding Provider 后必须用标注集重调并更新验证测试。
2. **真实 LLM 未集成**：mock-only；生产模式 LLM/Embedding Provider 抛 `NotImplementedError`（门禁，符合预期）。
3. **真实知乎 API 未验证**：本 Stage 仅复用 Stage-0 真实响应 fixture；未发起真实搜索。
4. **Neon 网络抖动**：直连偶发 `WinError 121` 超时，重跑可过（非代码缺陷）。
5. **公网部署未验证**。

## 下一阶段入口
- Stage 6：三栏 UI（回答列表 / 图谱 / 只读上下文）接 Graph API；P0 门通过后 MVP Freeze。
- 接入真实 Embedding 后：用 `annotation_pairs.json` 重调 `CONCEPT_SIMILARITY_THRESHOLD` / `ANSWER_SIMILARITY_THRESHOLD`。
