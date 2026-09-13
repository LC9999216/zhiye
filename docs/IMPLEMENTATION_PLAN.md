# 知辨小型 MVP 详细执行方案

## 1. 执行结论

本方案可以实施，但必须把知乎数据能力当作外部依赖，而不是默认可控的数据源。项目的第一目标不是搭 UI，而是证明官方搜索接口能够针对自然语言问题稳定返回可分析的 Answer 摘要、赞同数和原文链接。Stage 0 未通过时，项目不得继续。

计划状态：可执行，尚未开始编码。

计划路径：`D:\AI\zhiye\docs\IMPLEMENTATION_PLAN.md`

仓库现状：当前目录只有产品方案 DOCX、根目录 `AGENTS.md` 与本计划文件，尚无应用代码，也尚未初始化 Git。Git 初始化与特性分支创建是实施前置动作，必须早于 Stage 0 产生任何 fixture 或审计记录。

预计周期：单人配合 AI 开发约 3 到 5 周。该估算不包含开放平台审批、额度恢复、模型账号开通和生产部署等待时间。

## 2. 最终产品契约

### 2.1 输入与输出

- 输入：一个非空自然语言问题，不接收知乎 URL 作为主输入。
- 数据范围：调用知乎开放平台站内搜索，单次 `Count=10`；过滤后保留最多 10 条 `ContentType=Answer` 的结果。
- 排序：只在实际返回且通过过滤的结果内部按 `VoteUpCount` 降序；赞同数相同则保持接口原始顺序。
- AI：每条 Answer 从 `ContentText` 中提取 0 到 5 个 Claim，并保留可验证证据。
- 图谱主链：`QUERY → ANSWER → CLAIM → CONCEPT`。
- 交互：点击 Answer 或 Claim 打开对应知乎原文；点击 Concept 过滤相关回答；Citation 可定位来源。
- 页面固定提示：`观点基于知乎搜索返回内容生成，可能不包含原回答全部信息`。

### 2.2 成功场景

用户输入“计算机专业考研还是就业？”后，系统在可接受时间内展示最多 10 条相关知乎 Answer；列表按本次结果中的赞同数从高到低排列；每条回答有不超过 5 个带证据的 Claim；中间图谱显示固定四层结构；用户可通过回答、观点或 Citation 跳回知乎原文；AI 只基于已保存的返回内容回答并给出来源。

### 2.3 重要语义限制

1. 知乎搜索接口的 `ContentText` 定义为内容摘要，不承诺是完整回答正文。
2. `Count=10` 是搜索结果总数上限，结果可能混有文章等类型，因此最终 Answer 数可能小于 10。
3. 接口当前 `HasMore=false`，MVP 不分页，也不重复搜索来补齐 10 条 Answer。
4. `VoteUpCount` 排序不代表知乎全站或某问题下全部回答的高赞排名。
5. AI 提取的是搜索返回内容中的观点，不是对原回答全文的完整概括。

## 3. 执行边界

### 3.1 当前版本必须完成

- Next.js 三栏 Web 页面。
- FastAPI 服务、PostgreSQL + pgvector、Alembic migration。
- 官方知乎搜索 HTTP Provider。
- 搜索结果过滤、去重、排序和持久化。
- Answer 结构化提取、Claim 证据校验、概念归一化。
- 固定四层图谱和四类基础关系。
- 回答列表、图谱、AI 面板联动与知乎原文跳转。
- 基于保存内容的 Graph-enhanced RAG 与 Citation。
- 健康检查、任务状态、空态、错误态、最小观测指标。
- 自动化测试、Docker Compose 本地运行和演示脚本。

### 3.2 当前版本明确不做

- 知乎 OAuth 用户登录、关注、收藏、评论、个人知识库或发布内容。
- 网页爬虫、登录态抓取、私有接口、回答全文补抓。
- 热榜、问答社区、多平台内容源、定时任务和推送。
- Neo4j、Redis、Celery、Kafka、Kubernetes、微服务。
- SUPPORTS/CONTRADICTS 自动推理、社区检测和复杂多跳图算法。
- 多 Agent 工作流、内容导出、移动端专项适配、生产部署。

### 3.3 必须停止并请求用户决定的情况

- Stage 0 无法证明官方接口满足最小字段契约。
- 需要改用抓取、私有接口或第三方非授权数据源。
- 需要更换核心技术栈或重做主数据模型。
- 需要删除不可恢复的数据或覆盖用户文件。
- 需要开通付费模型、付费数据库或部署公网生产环境。
- 需要扩大到用户系统、OAuth 或账号私有数据。

## 4. 关键架构决策

### 4.1 选择官方 HTTP API 作为运行时数据源

Stage 0 可以用官方 CLI 快速确认能力，但正式 FastAPI 服务直接调用 `GET https://developer.zhihu.com/api/v1/content/zhihu_search`，并把调用封装在 `ZhihuSearchProvider` 中。这样不需要在 Web 服务进程中启动 CLI 子进程，也不依赖桌面凭据存储或 stdout 格式。

Provider 负责：Bearer 鉴权、`X-Request-Timestamp`、超时、响应解析、错误码映射和脱敏日志。业务层只接收内部 `SearchAnswerDTO`。

### 4.2 关系数据库保存图

MVP 规模最多 1 个 Query 对应 10 个 Answer，图规模很小。PostgreSQL 的节点表、带外键的关联表与 Answer 相似关系表足够支持 1-hop 查询；pgvector 负责相似度检索。Neo4j 会增加部署、同步和运维成本，暂不引入。

### 4.3 单进程后台任务

`POST /api/queries/analyze` 创建 Job 后返回 `202 + job_id + query_id`，FastAPI 在当前进程执行搜索、分析和建图。Job 状态保存在数据库；Job 查询在完成时同时返回 `query_id`、answers URL 与 graph URL。进程重启时可把未完成 Job 标记为 failed 并允许用户重试。MVP 不引入 Redis/Celery。

### 4.4 LLM Provider 隔离

实现 OpenAI-compatible 的 `LLMProvider` 与 `EmbeddingProvider` 接口，通过环境变量配置。Prompt、JSON Schema 与业务校验由本仓库控制，避免把业务契约交给厂商 SDK。

## 5. 目标目录结构

```text
zhiye/
├─ AGENTS.md
├─ README.md
├─ .env.example
├─ docker-compose.yml
├─ apps/
│  ├─ web/                    # Next.js
│  │  ├─ app/
│  │  ├─ components/
│  │  ├─ lib/
│  │  ├─ stores/
│  │  └─ tests/
│  └─ api/                    # FastAPI
│     ├─ app/
│     │  ├─ api/
│     │  ├─ core/
│     │  ├─ db/
│     │  ├─ models/
│     │  ├─ schemas/
│     │  └─ services/
│     └─ tests/
├─ packages/
│  └─ contracts/             # OpenAPI 生成或共享类型
├─ database/
│  ├─ migrations/
│  └─ fixtures/
├─ docs/
│  └─ IMPLEMENTATION_PLAN.md
└─ tests/
   └─ e2e/
```

## 6. 核心数据契约

### 6.1 外部搜索 DTO

```json
{
  "search_hash_id": "string",
  "items": [
    {
      "original_index": 0,
      "title": "string",
      "content_type": "Answer",
      "content_id": "string",
      "content_text": "string",
      "url": "https://www.zhihu.com/answer/...",
      "voteup_count": 0,
      "author_name": "string",
      "edit_time": 0,
      "ranking_score": 0.0
    }
  ]
}
```

### 6.2 AI 提取 DTO

```json
{
  "summary": "string",
  "stance": "support|oppose|conditional|neutral",
  "claims": [
    {
      "text": "string",
      "evidence_text": "必须来自当前 ContentText",
      "confidence": 0.0,
      "concepts": ["string"]
    }
  ]
}
```

硬约束：`claims.length <= 5`；`evidence_text` 经空白和高亮标签规范化后必须是 `ContentText` 子串；不满足的 Claim 直接丢弃。

### 6.3 数据库最小表

- `queries`：`id`、`query_text`、`normalized_query`、`search_hash_id`、`status`、`search_fetched_at`、创建/更新时间；`normalized_query` 唯一。
- `answers`：`id`、`query_id`、`content_id`、`title`、`author_name`、`content_text`、`voteup_count`、`url`、`original_index`、`edit_time`、`ranking_score`、`fetched_at`、`summary`、`stance`、`embedding`、`embedding_model`、`analysis_model`、`prompt_version`、`schema_version`、`analyzed_at`、`analysis_latency_ms`、分析状态。
- `claims`：`id`、`query_id`、`answer_id`、`text`、`evidence_text`、`position`、`confidence`、`embedding`、`embedding_model`。
- `concepts`：`id`、`query_id`、`canonical_name`、`normalized_name`、`aliases`、`frequency`、`embedding`、`embedding_model`。
- `claim_concepts`：`query_id`、`claim_id`、`concept_id`，通过复合外键强制 Claim 与 Concept 属于同一 Query。
- `answer_similarities`：`query_id`、`source_answer_id`、`target_answer_id`、`score`、`embedding_model`、`method_version`；通过复合外键强制两个 Answer 属于同一 Query。
- `jobs`：`id`、`query_id`、`status`、`current_step`、`error_code`、`error_message`、开始/结束时间。
- `chat_messages`：`query_id`、角色、内容、citation JSON、时间戳。

唯一与检查约束：`queries(normalized_query)`、`answers(query_id, content_id)`、`answers(query_id, id)`、`claims(query_id, id)`、`claims(query_id, answer_id, position)`、`concepts(query_id, id)`、`concepts(query_id, normalized_name)`、`claim_concepts(query_id, claim_id, concept_id)`、`answer_similarities(query_id, source_answer_id, target_answer_id)`；`claims.position` 必须在 1 到 5，Answer 相似对必须满足 `source_answer_id < target_answer_id`。`claims(query_id, answer_id)` 复合外键指向 `answers(query_id, id)`；`claim_concepts` 分别用 `(query_id, claim_id)` 与 `(query_id, concept_id)` 复合外键；`answer_similarities` 的 source/target 分别用 `(query_id, answer_id)` 复合外键。业务层在一个事务内替换某 Answer 的 Claim，并再次校验总数不超过 5。所有时间使用 UTC。

主链只以外键表为权威事实源：`answers.query_id` 生成 `RETURNS_ANSWER`，`claims.answer_id` 生成 `MAKES_CLAIM`，`claim_concepts` 生成 `REFERS_TO`，`answer_similarities` 生成 `SIMILAR_TO`。不保存重复的通用 Edge 表。

## 7. API 设计

| 方法 | 路径 | 行为 | 主要验收 |
|---|---|---|---|
| GET | `/api/health` | API 与数据库健康检查 | 返回版本与依赖状态，不泄露密钥 |
| POST | `/api/queries/analyze` | 提交自然语言问题 | 空输入 422；合法输入返回 202、job_id、query_id 与 job_url |
| GET | `/api/jobs/{id}` | 获取处理状态 | 状态只允许 pending/fetching/analyzing/building/completed/failed；完成时返回 query_id、answers_url、graph_url |
| GET | `/api/queries/{id}` | 查询基本信息 | 返回 query_text、状态、结果数 |
| GET | `/api/queries/{id}/answers` | 获取已排序回答 | 数量不超过 10，VoteUpCount 非递增 |
| GET | `/api/queries/{id}/graph` | 获取节点与边 | 节点和关系类型只能来自固定集合 |
| GET | `/api/answers/{id}` | Answer 详情与 Claim | Claim 不超过 5，带 source_url |
| POST | `/api/chat` | 基于 Query/节点继续问答 | Citation 必须引用当前 Query 下的 Answer |

`POST /api/queries/analyze` 请求只包含 `query_text`。服务器固定搜索数量为 10，前端不得允许用户扩大抓取规模。

## 8. 分阶段执行计划

### 实施前置动作 仓库保护

输入：用户已明确要求开始编码；当前工作区状态；根目录 `AGENTS.md` 与本计划。

任务：

1. 再次确认 `D:\AI\zhiye` 是目标目录，记录初始文件清单。
2. 若无 `.git`，初始化 Git 并提交只包含现有 DOCX、`AGENTS.md` 与本计划的基线提交。
3. 创建并切换到 `feat/zhibian-mvp`；确认后续写入不会发生在 `main`。
4. 创建 `docs/progress/`，每个 Stage 的执行记录写入 `STAGE_N.md`。
5. 把 `.env`、`.local/`、真实 API 响应与本地测试数据库加入 `.gitignore`。

验收：`git status` 可解释、当前分支为 `feat/zhibian-mvp`、受保护 DOCX 哈希未变化、真实凭证和真实响应不会被 Git 跟踪。

停止条件：目标目录不明确、存在无法安全保留的用户改动、Git 初始化会覆盖现有历史，或用户只要求继续审阅方案而未授权编码。

### Stage 0 知乎数据可行性门

目标：在不搭建应用功能前，用只读调用和独立审计证明当前官方数据契约可用。

输入：已完成仓库保护；官方 API/CLI 当前能力说明；本机安全配置的 Access Secret；3 个自然语言测试问题。

任务：

1. 检查官方 CLI/HTTP 文档与当前 capability，确认 `zhihu_search`、Count 上限和鉴权方式。
2. 在本机安全配置 Access Secret，不把 Secret 写入仓库或命令历史。
3. 准备 3 个自然语言测试问题：常见问题、可能混合文章的问题、冷门或空结果问题。
4. 每个问题真实请求 2 次 `Count=10`，两次间隔至少 30 秒；不要求两次结果内容相同，只验证协议和关键字段契约。
5. 统计 Answer 数、必需字段缺失数、重复 ContentID、ContentText 长度和响应耗时。
6. 用 PowerShell `ConvertFrom-Json` 或一次性只读校验命令生成字段审计报告，不在 Stage 0 编写业务过滤、排序或 Provider 代码。

交付物：真实响应只保存到被忽略的 `.local/zhihu-fixtures/`；仓库提交的 `database/fixtures/zhihu_search/` 只包含按官方 Schema 构造的确定性合成 fixture，不包含评论、头像、Badge 或其他不在 MVP 范围内的数据；决策记录写入 `docs/progress/STAGE_0.md`。

可重复校验：

- 6 份本地真实响应都能被 JSON 解析，顶层 `Code/Message/Data` 与 `Data.Items` 类型正确。
- 审计报告列出每次调用的总 Item 数、Answer 数、关键字段缺失数、重复 ContentID 数和耗时。
- 合成 fixture 只验证能表达混合类型、重复项、缺字段与空结果；过滤、去重和排序的红绿测试统一留到 Stage 2。

人工验收：6 次真实调用的顶层响应全部符合当前官方协议；至少 2 个问题在至少 1 次调用中返回可分析 Answer；每个有效 Item 的必需字段完整；链接可在浏览器打开对应知乎原文；记录仅能得出“当前样本契约通过”，不得宣称长期稳定或结果集合稳定。

停止条件：6 次调用中出现无法解释的顶层 Schema 漂移；有效 Answer 缺少 `ContentID`、`ContentText`、`Url` 或 `VoteUpCount`；真实接口不可用、凭证无权限、额度不足，或必须依赖网页抓取。触发后停止全部后续 Stage。

预计：1 到 2 天。

### Stage 1 工程初始化

目标：建立可重复启动、可测试的 monorepo 基础。

输入：实施前置动作与 Stage 0 均已通过；已确认可用的 Node、Python、Docker 与 PostgreSQL 运行环境。

任务：

1. 建立 Next.js、FastAPI、PostgreSQL + pgvector 与 Docker Compose。
2. 添加 `.env.example`、依赖锁文件、lint/typecheck/test 脚本。
3. 建立 `/api/health`、数据库连接和第一条 Alembic migration。
4. 提供 `APP_MODE=mock`，使无真实知乎与 LLM 密钥时也能用合成 fixture 启动和验收基础工程。
5. CI 只运行合成 fixture 测试，不访问真实知乎或 LLM。

自动化验收：全新环境复制 `.env.example` 并使用 `APP_MODE=mock` 后可一条命令启动；Web、API、DB 健康；空项目 lint、typecheck、unit test 全通过；Secret 扫描无发现。

人工验收：浏览器可打开 Web 首页，`/api/health` 返回依赖状态，容器停止后可再次无手工修复启动。

停止条件：需要改用不同核心技术栈或本机无法运行 Docker/PostgreSQL。

预计：1 到 2 天。

### Stage 2 ZhihuSearchProvider

目标：把官方 HTTP 响应稳定映射为内部 DTO。

输入：Stage 1 通过；Stage 0 合成契约 fixture；官方 endpoint 与错误码；本地真实响应只作人工比对。

任务：

1. 实现 Bearer Header 与秒级时间戳；查询规范化后长度限制为 1 到 200 个字符；连接超时 5 秒、读取超时 20 秒、响应体上限 2 MiB、单进程并发上限 2。
2. 实现响应 Schema、错误码映射与脱敏日志。
3. 实现固定规范化流水线：Answer 过滤 → ContentID 去重 → VoteUpCount 降序 → 最多 10 条 → ContentText 清洗。
4. 只对连接超时和 HTTP 5xx 重试 1 次，退避 500 ms；对 `20001` 鉴权失败、`30001` 限流及数据契约错误不重试。
5. 仅允许官方 HTTPS endpoint；endpoint 由受控配置给出，不接受用户输入。
6. 顶层响应缺字段时整批失败；单个 Item 缺必需字段时丢弃该 Item 并记录计数；全部 Item 均无效时返回 `DATA_CONTRACT_ERROR`。

自动化验收：契约 fixture 全部通过；混合类型、重复 ID、相同赞同数、缺字段、恶意 HTML、超大响应、超时、空 Items 和所有错误码均有测试；业务服务不引用知乎字段原始大小写。

人工验收：在本机用 1 个 Stage 0 问题调用 Provider，输出 DTO 与本地真实响应的允许字段一致，日志中没有 Authorization 或 Secret。

停止条件：正式 API 契约与 Stage 0 fixture 不兼容、必须放宽安全限制才能成功，或需求要求改用 CLI/抓取作为正式运行路径。

预计：2 到 3 天。

### Stage 3 数据库与分析 Job

目标：可靠保存 Query、Answer 与处理状态。

输入：Stage 2 通过；最终内部 DTO；第 6 节数据库契约。

任务：

1. 编写 queries、answers、jobs 的 migration 和 ORM，并落实 `normalized_query` 唯一约束。
2. 实现 `POST /api/queries/analyze` 和 `GET /api/jobs/{id}`。
3. Query 规范化固定使用 Unicode NFKC、首尾 trim、连续空白折叠与 casefold；相同 `normalized_query` 原子复用同一 Query。若已有活动 Job，返回该 Job；否则创建刷新 Job。
4. 刷新搜索成功后在事务中替换该 Query 的 Answer 集合；不创建重复 `(query_id, content_id)`，失败时保留上一份已完成结果。
5. 每一步更新 Job 状态；单条 Answer 后续分析失败不丢失其他成功结果。
6. 服务重启时把遗留运行中 Job 标记为可解释的失败状态。

自动化验收：fixture 导入后只有 1 个 Query、最多 10 个 Answer，读取顺序保持 VoteUpCount 非递增；大小写/空白等价查询与并发重复提交只产生一个 Query 和一个活动 Job；失败刷新不破坏上一份完成结果；事务测试通过。

人工验收：用相同问题的空白变体连续提交两次，返回相同 query_id；Job 完成响应能直接提供 answers_url 与 graph_url。

停止条件：幂等规则需要保留多版本历史、单进程 Job 无法满足用户要求，或必须引入外部队列才能继续。

预计：2 到 3 天。

### Stage 4 AI 结构化提取

目标：对每条 ContentText 生成受约束的结构化观点。

输入：Stage 3 通过；第 6.2 节唯一 AI Schema；至少 30 条确定性合成 Answer fixture，其中包含短文本、长文本、空 Claim、恶意指令和脏 JSON 场景。Stage 0 的真实 Answer 只用于本地人工抽查，不作为 CI 数量前提。

任务：

1. 为 claims 与 Answer 分析追溯字段编写 migration 和 ORM。
2. 定义 Prompt、JSON Schema、Pydantic 模型和 Prompt 版本。
3. 实现 summary、stance、0 到 5 个 Claim、Claim Concepts 与 evidence_text。
4. 在代码层再次截断 Claim 数，并做 evidence 子串校验。
5. 格式错误最多重试 2 次；单条失败记录原因并继续。
6. 生成 Answer/Claim embedding，并在 Answer 保存 `analysis_model`、`prompt_version`、`schema_version`、`analyzed_at` 与 `analysis_latency_ms`。

自动化验收：30 个合成 Answer fixture 通过 Schema；任何 Answer 都不会保存第 6 个 Claim；`position` 数据库检查约束拒绝 0 和 6；每条已保存 Claim 都能在对应 ContentText 中定位证据；模型返回脏 JSON、空数组、超时和部分失败均有测试。

人工验收：从 Stage 0 本地真实响应中抽查所有可用 Answer，目标 5 条；如果不足 5 条则检查全部并记录样本不足，不用重复调用接口补齐。逐条检查 Claim 数、证据定位与“未分析全文”表述，记录在 `docs/progress/STAGE_4.md`。

停止条件：模型无法稳定输出 Schema、有效 Claim 覆盖率低于 60%，或必须向模型发送未授权全文才能达到效果。有效 Claim 覆盖率固定定义为“抽查中至少保存 1 条有效 Claim 的非空 ContentText Answer 数 ÷ 被抽查的非空 ContentText Answer 总数”；分母为 0 时直接停止并报告样本不可用。

预计：3 到 4 天。

### Stage 5 概念归一化与图谱构建

目标：生成稳定、可解释的四层知识图谱。

输入：Stage 4 通过；带证据的 Claim；至少 20 组人工标注的概念同义/不同义对，以及至少 20 组人工标注的 Answer 相似/不相似对。

任务：

1. 为 concepts、claim_concepts 与 answer_similarities 编写 migration 和 ORM。
2. 先做确定性概念规范化：Unicode、大小写、空白和常见别名。
3. 用 Concept embedding 相似度产生候选合并；阈值从 0.88 起步，用概念标注集调优后写入版本化配置。
4. 低置信度候选不自动合并；保留别名与归一化依据。
5. 复用 Stage 4 基于清洗后 `ContentText` 生成的 Answer embedding，只在同一 Query 内计算余弦相似度；阈值从 0.82 起步。
6. 候选对按相似度降序、规范化 ID 对升序做确定性排序，再依次加入；只有两个端点当前无向度数都小于 2 时才加入，因此最终每个 Answer 的 `SIMILAR_TO` 无向度数不超过 2。
7. Answer 相似对按 `(min(answer_id), max(answer_id))` 规范化后只保存一次，并记录 `embedding_model` 与 `method_version=answer-cosine-v1`。
8. 从业务外键派生 `RETURNS_ANSWER`、`MAKES_CLAIM`、`REFERS_TO`；只把通过阈值和度数限制的 Answer 相似度写入 `answer_similarities`。
9. 实现 `/api/queries/{id}/graph`，返回可直接渲染的 nodes/edges。

自动化验收：每个 Answer 只有一个 Query 来源；每个 Claim 只有一个 Answer 来源；每个 Concept 属于一个 Query 且至少被一个 Claim 引用；无孤立 Claim；数据库拒绝任一跨 Query 复合外键写入；每个 Answer 的最终 `SIMILAR_TO` 无向度数不超过 2；Graph API 只从权威外键表派生边；重复建图幂等。概念标注对和 Answer 相似标注对必须分别同时达到误合并/误连率不高于 5%、漏合并/漏连率不高于 20%。

人工验收：查看至少 3 个图谱，其中优先使用全部可用真实 Query，不足部分用明确标记的合成 Query 补齐；确认没有跨 Query Concept、主链可追溯、低置信度概念保持分离，并逐条抽查 `SIMILAR_TO` 两端的 ContentText 是否确有语义相似性。

停止条件：必须引入图数据库才能完成 1-hop 查询；不存在能让两组标注集分别同时满足误合并/误连与漏合并/漏连上限的阈值；或需要加入未批准的新节点/关系类型。

预计：3 到 4 天。

### Stage 6 三栏 Web 界面

目标：让用户看到真实数据并完成主要浏览动作。

输入：Stage 5 通过；稳定的 Query、Answer、Graph 与 Job API；设计仅采用桌面优先三栏布局。

任务：

1. 左栏：问题输入、Job 进度、最多 10 条 Answer、赞同数和作者。
2. 中栏：Sigma.js 图谱、节点颜色、Answer 大小、zoom/drag/hover/click/filter。
3. 右栏：只实现禁用的 AI 面板骨架和选中节点上下文预览，明确显示“AI 问答将在 Stage 8 启用”；本阶段不调用 `/api/chat`，不展示伪 Citation。
4. 固定显示范围提示，不能只藏在帮助页。
5. Answer 与 Claim 点击使用安全新标签打开原文；Concept 点击过滤左栏。
6. 实现加载、空结果、部分分析失败、鉴权失败、限流和通用错误态。

自动化验收：组件测试验证排序、数量、固定提示和各错误态；Answer/Claim 链接带 `noopener,noreferrer` 且 URL 来自保存的 Answer；合成 fixture 可在三栏正确显示；键盘可访问主要操作。

人工验收：在 Chrome 当前稳定版以 1440×900 视口完成提交、查看列表、拖拽图谱、选择节点和打开原文；页面无横向溢出，固定提示无需打开帮助页即可看见。

停止条件：产品要求改为移动端优先、需要新增设计系统，或图规模超出 Sigma.js 在本 MVP 数据量下的稳定渲染能力。

预计：3 到 5 天。

### Stage 7 双向联动

目标：回答列表、图谱和待传给 AI 的选中上下文状态一致。

输入：Stage 6 通过；固定图谱节点 ID、Answer source_url 与前端状态模型。

任务：

1. Zustand 保存 `selectedNode`、`selectedAnswer`、`activeConcept`、`graphFilters`。
2. 左到中：选择 Answer 高亮相关 Claim/Concept，其他节点降低透明度。
3. 中到左：选择 Concept 过滤相关 Answer，保持赞同数排序。
4. 中到右：选中节点写入只读上下文预览，供 Stage 8 接入对话服务。
5. 清除状态后恢复全图和原始排序。

自动化验收：前端状态测试覆盖四个方向；不存在选择 A 后右栏仍显示 B 的陈旧状态；清除过滤能恢复全部结果；点击 Claim 打开的 URL 与其 Answer 一致。

人工验收：按“Answer → Concept → Claim → 清除过滤”顺序操作 3 次，列表排序、图谱高亮和右栏上下文预览始终一致；AI 输入保持禁用且没有虚构 Citation。

停止条件：联动要求扩展到当前四种节点以外，或需要全局跨 Query 状态才能满足交互。

预计：2 到 3 天。

### Stage 8 Graph-enhanced RAG

目标：只基于已保存的知乎返回内容生成多观点答案。

输入：Stage 7 通过；当前 Query 的 Answer、Claim、Concept、embedding 与可追溯 source_url；Stage 6 的禁用 AI 面板骨架和 Stage 7 的选中上下文状态。

任务：

1. 为 chat_messages 编写 migration，并实现只绑定当前 Query 的 `POST /api/chat` 对话服务。
2. 对用户追问生成 embedding，在当前 Query 内检索 Answer/Claim TopK。
3. 做 1-hop 图扩展，补充相关 Claim、Concept 与 Answer。
4. 重排并限制最终上下文为 6 到 10 条证据。
5. Prompt 强制区分“来源支持的结论”和“模型推断”。
6. 返回结构化 Citation：answer_id、content_id、author、url、evidence_text。
7. 证据不足时明确返回不足，不虚构来源。
8. 启用右栏 AI 输入并接入 `/api/chat`；Citation 点击时定位 Answer、同步图谱高亮并支持安全打开知乎原文。
9. 固定接口边界：用户追问 1 到 1000 字符、请求体不超过 32 KiB、最多使用 10 条证据、LLM 连接超时 5 秒、读取超时 60 秒、并发上限 2；POST 不自动重试，失败后由用户显式重试以避免重复计费。

自动化验收：请求长度、请求体、并发和超时边界测试通过，失败 POST 不被自动重放；每个 Citation 都属于当前 Query 且可解析到现有 Answer；固定恶意 fixture 中的“忽略系统指令”等文本只作为引用内容进入模型上下文，不能进入 system message 或改变工具配置；Citation 后处理拒绝未知 answer_id；无证据时返回 `insufficient_evidence`，不生成伪 Citation；前端 Citation 点击可定位正确 Answer、同步高亮并打开同一 source_url。

人工验收：选择至少 2 个包含不同 Claim 的真实 Query，检查 AI 能按来源分别陈述可用观点，并逐个点击 Citation 验证列表定位、图谱高亮和知乎原文 URL；如果来源本身只有一种观点，允许只返回一种，不以“必须多观点”作为硬门。

停止条件：Citation 无法可靠约束到当前 Query、模型必须访问外部网页才能回答，或需要复杂多跳图算法才能满足要求。

预计：3 到 5 天。

### Stage 9 端到端验收与演示

目标：证明完整闭环可重复运行。

输入：Stage 0 到 Stage 8 全部通过；专用测试数据库；3 个手工真实查询；完整启动和故障排查文档草稿。

任务：

1. 建立 Playwright 主流程和错误流程。
2. 运行 lint、typecheck、backend unit/integration、frontend unit、e2e。
3. 用至少 3 个真实自然语言问题做手工验收，记录 API 日期、结果数和限制。
4. 验证首次启动、数据库 migration、失败重试，并只清空专用、可丢弃的测试数据库后重新运行；不得删除真实或用户数据。
5. 完成 README、环境变量、启动/停止、测试和故障排查文档。
6. 记录真实调用耗时、LLM Token、单次成本和节点数量。

自动化验收：Playwright 主流程和错误流程通过；lint、typecheck、backend unit/integration、frontend unit、e2e 全通过；专用测试数据库可重建；Secret 扫描无发现。

人工验收：在本地开发机、Chrome 稳定版、Docker 冷启动完成后，用 3 个真实问题分别跑通 Answer 排序、Claim、图谱、AI Citation 和原文跳转；记录每次端到端耗时而不设第三方网络硬 SLA。演示过程中不手工改数据库；README 可由另一位执行者复现 mock 模式启动。

停止条件：任一全局验收标准失败、测试需要真实 Secret 才能运行、演示必须手工改数据库，或用户要求直接部署生产环境。

预计：2 到 4 天。

## 9. 全局验收标准

### 9.1 功能验收

| 编号 | 标准 | 判定方法 |
|---|---|---|
| F-01 | 输入只需自然语言问题 | Playwright 从首页提交，不要求 URL |
| F-02 | Answer 数量为 0 到 10 | API Schema + E2E 断言 |
| F-03 | 只展示 ContentType=Answer | 契约 fixture 混入 Article 后验证 |
| F-04 | VoteUpCount 非递增 | 后端单测、API 集成测试、UI 测试 |
| F-05 | 每条 Answer 有 0 到 5 个 Claim | Schema、数据库约束与测试 |
| F-06 | Claim 证据来自 ContentText | 规范化子串校验 |
| F-07 | 图谱只含四类节点和四类关系 | Graph API Schema 测试 |
| F-08 | Answer/Claim 可跳知乎原文 | E2E 检查目标 URL 与安全属性 |
| F-09 | 固定范围提示始终可见 | 页面组件和 E2E 文本断言 |
| F-10 | AI Citation 可追溯到当前 Query | 后端引用完整性测试 |
| F-11 | 异步 Job 完成后可直接取得 query_id 与结果 URL | API 集成测试 |
| F-12 | 模型、Prompt、Schema 版本和分析时间可追溯 | 数据库集成测试 |

### 9.2 质量验收

- 后端核心领域逻辑分支覆盖率不低于 80%；过滤、排序、Claim 证据和 Graph Edge 派生必须 100% 分支覆盖。
- TypeScript strict 和 Python 类型检查通过；lint 无 error。
- CI 不依赖真实知乎、真实 LLM 或真实 Secret。
- 在固定合成 fixture、mock 知乎与 mock LLM、Docker 已启动的本地开发机上，10 次端到端测试的 p95 不超过 10 秒。真实外部调用只记录耗时，90 秒是体验目标而非发布硬门；超时期间必须持续提供阶段状态。
- API 错误返回稳定 error code；页面对空结果、鉴权、限流、LLM 部分失败有明确提示。
- 日志中不出现 Access Secret、LLM Key、数据库密码或完整 Authorization Header。

### 9.3 数据与授权验收

- 使用官方 Bearer 接口和秒级时间戳；无网页抓取代码。
- 数据库保存来源 URL、ContentID、SearchHashId、获取时间与接口返回字段。
- UI 和 AI 不把 ContentText 描述为完整原文。
- 遇到鉴权失败或限流停止自动重试。
- Concept 按 Query 隔离；删除 Query 时级联清理其 Answer、Claim、Concept、相似关系和聊天派生数据的行为有专用测试。任何真实数据清理必须由用户明确触发。

## 10. 测试策略与命令约定

具体命令在 Stage 1 根据脚手架写入 `package.json`、`pyproject.toml` 与 README，但统一入口应收敛为：

```powershell
docker compose up -d --build
pnpm lint
pnpm typecheck
pnpm test
pnpm test:e2e
& '.\.venv\Scripts\python.exe' -m pytest apps/api/tests
```

如果 Python 包不通过 pnpm 管理，README 必须给出锁定解释器的等价 `pytest` 命令。Agent 只能报告实际执行过的命令与结果。

测试分层：

1. 纯函数单测：搜索规范化、排序、证据校验、概念规范化、Graph Edge 派生。
2. Provider 契约测试：确定性合成 JSON fixture，覆盖字段和错误码。
3. 数据库集成测试：真实 PostgreSQL 容器、migration、upsert、事务。
4. API 集成测试：完整请求、Job 状态、Graph 和 Chat Citation。
5. 前端组件测试：状态与交互。
6. Playwright E2E：主流程、空结果、限流、部分失败、原文跳转。
7. 手工真实 API 验收：只在本地、按需执行并记录额度消耗，不放入 CI。

## 11. 风险与应对

| 风险 | 级别 | 影响 | 应对 |
|---|---|---|---|
| ContentText 仅为摘要 | 高 | Claim 可能不代表全文 | 固定提示、证据约束、原文跳转、禁止“全文”表述 |
| 搜索结果混合类型 | 高 | 最终 Answer 少于 10 | 接受 0 到 10，明确空态，不重复搜索补齐 |
| API 权限/额度/频率变化 | 高 | 无法获取数据 | Stage 0 硬门、错误码映射、额度提示、不抓取替代 |
| LLM 生成无证据观点 | 高 | 图谱失真 | JSON Schema、最多 5 条、证据子串校验、丢弃失败 Claim |
| 概念错误合并 | 中 | 图结构误导 | 高阈值候选、低置信度不合并、fixture 人工审查 |
| 后台任务进程重启 | 中 | Job 中断 | 数据库状态、启动恢复为 failed、用户可重试 |
| 外部内容 XSS/提示注入 | 高 | 前端或模型受攻击 | 纯文本渲染、HTML 清洗、Prompt 明确外部内容不可信 |
| 开发范围膨胀 | 高 | 无法按期交付 | AGENTS.md、Stage 门禁、Backlog、禁止提前实现 |

## 12. 每阶段交付记录模板

```markdown
## Stage N 交付记录

- 目标：
- 修改文件：
- Migration：
- 测试命令与结果：
- 真实知乎 API 验证：已验证 / 未验证
- 验收标准：通过 / 未通过
- 已知限制：
- 下一阶段入口：
```

## 13. Agent 执行交接提示

复制以下提示给后续实现 Agent：

```text
请在 D:\AI\zhiye 仓库内按照 D:\AI\zhiye\docs\IMPLEMENTATION_PLAN.md 实现“知辨”小型 MVP，并把 D:\AI\zhiye\AGENTS.md 视为仓库级强制规则。

工作边界：当前目录如尚未初始化 Git，先完成实施前置动作，初始化 Git 并创建 feat/zhibian-mvp 分支；在 Stage 0 写入任何 fixture、测试或审计记录之前确认分支，不得直接修改 main。保护 Zhibian_MVP_Architecture_and_Execution_Plan_v0.2.docx，不得修改、移动或删除。不要触碰仓库外文件，不要使用 git reset --hard，不要提交任何真实 Secret 或真实知乎响应。

核心目标：用户输入自然语言问题；官方知乎搜索单次 Count=10；只保留返回结果中的 Answer；按 VoteUpCount 降序；每条 Answer 从 ContentText 提取 0 到 5 个带证据 Claim；构建 QUERY → ANSWER → CLAIM → CONCEPT 图谱；点击 Answer/Claim 跳知乎原文；页面始终显示“观点基于知乎搜索返回内容生成，可能不包含原回答全部信息”。

执行方式：先完成实施前置动作，再严格按 Stage 0 到 Stage 9 顺序推进。先写失败测试，再做最小实现，再运行该阶段全部测试。Stage 0 是硬门；若官方接口、权限、额度或关键字段不满足要求，立即停止，不得改用爬虫、私有接口或未授权数据源。每个 Stage 未通过验收不得进入下一阶段，并将记录写入 docs/progress/STAGE_N.md。

验证要求：运行 lint、typecheck、后端单元/集成、前端单元和 Playwright E2E；只报告真实执行结果。CI 使用脱敏 fixture，不调用真实知乎或 LLM。真实 API 验证与模拟测试必须分别说明。

最终交付：总结完成的 Stage、用户可见功能、修改文件、Migration、实际测试命令及通过数量、真实知乎 API 是否验证、剩余风险和未完成项。不要把测试通过描述为生产就绪。
```

## 14. 开始实施前检查清单

- [ ] 用户已明确要求开始编码，而不只是审阅计划。
- [ ] 已读取根目录 `AGENTS.md`。
- [ ] 已确认当前 Stage 与验收标准。
- [ ] 已完成实施前置动作，并确认当前分支为 `feat/zhibian-mvp`。
- [ ] 已确认 DOCX 受保护且不需要修改。
- [ ] Stage 0 所需 Access Secret 只存在于安全环境变量或凭据存储。
- [ ] 已为当前行为先写失败测试。
- [ ] 未把 Backlog 功能混入当前 Stage。
