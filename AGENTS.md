# 知辨 MVP 仓库执行规则

## 1. 规则适用范围

本文件适用于仓库根目录及全部子目录。所有自动化 Agent、开发者和脚本在修改代码前都必须先读取本文件与 `docs/IMPLEMENTATION_PLAN.md`。

指令优先级为：用户当前明确要求 > 本文件 > 执行方案 > 代码注释。若发生冲突，停止实现并说明冲突，不得自行扩大需求。

## 2. 唯一产品目标

本仓库只实现一个小型 MVP：用户输入自然语言问题，系统调用知乎开放平台搜索能力，保留返回结果中的最多 10 条 `Answer`，在这些结果内部按 `VoteUpCount` 降序排列；AI 对每条返回内容提取 0 到 5 个有证据的 Claim，并生成 `QUERY → ANSWER → CLAIM → CONCEPT` 知识图谱。用户点击 Answer 或 Claim 时必须能够打开该回答的知乎原文。

页面必须持续显示以下原文提示，不得改写或隐藏：

> 观点基于知乎搜索返回内容生成，可能不包含原回答全部信息

## 3. 不可变的数据边界

1. 只使用知乎开放平台正式搜索 API 或官方 CLI 返回的数据；不得调用未公开私有接口，不得抓取登录态页面，不得绕过权限、频率限制或日额度。
2. 搜索请求 `Count=10`。接口可能同时返回 Answer、Article 等类型；过滤后 Answer 少于 10 条是合法结果，不得通过重复搜索、翻页或私有接口强行补满。
3. “按赞同数排序”只表示在本次接口实际返回并过滤后的 Answer 集合中排序，不得宣称是知乎全站、问题下全部回答或全量高赞排名。
4. `ContentText` 是搜索接口返回的内容摘要，不是受保证的回答全文。模型只能分析实际返回的 `ContentText`，不得补写、猜测或声称已读取未返回的原文。
5. 每条 Answer 生成 0 到 5 个 Claim。每个 Claim 必须保存来自对应 `ContentText` 的证据文本；无法找到证据时删除该 Claim，而不是编造证据。
6. Claim 和 Citation 必须继承对应 Answer 的 `ContentID` 与 `Url`，保证点击后可回到知乎原文。
7. 默认不采集评论、关注、收藏、用户画像、个人创作或其他账号数据。

## 4. MVP 范围

### 必须实现

- 自然语言问题输入与空值校验。
- 知乎搜索 Provider、Bearer 鉴权、秒级 `X-Request-Timestamp`、超时与错误映射。
- `ContentType == "Answer"` 过滤、按 `ContentID` 去重、最多 10 条、`VoteUpCount` 降序。
- Answer、Claim、Concept 与相似关系持久化；Graph API 从带外键的业务表派生边。
- 每条 Answer 的结构化 AI 提取、JSON Schema 校验和最多 2 次格式重试。
- 固定主链 `QUERY → ANSWER → CLAIM → CONCEPT`。
- 三栏界面、回答与图谱联动、原文跳转、固定范围提示。
- 基于已保存 Answer/Claim 的问答与可点击 Citation。
- 健康检查、错误态、空结果态、加载状态和最小端到端测试。

### 明确不做

- 用户系统、知乎 OAuth 登录、关注、收藏、私有知识库。
- 知乎热榜、评论分析、回答发布或任何写回知乎的功能。
- 抓取回答全文、绕过平台权限、批量爬虫。
- Neo4j、Redis、Celery、Kafka、微服务、多 Agent、定时任务和推送。
- 复杂的 SUPPORTS/CONTRADICTS 推理、社区发现和多跳图算法。
- Markdown、PDF、PPT 导出，移动端适配，多平台内容接入。
- 生产部署、付费资源开通和公网发布，除非用户另行明确授权。

新增功能只有在直接改善“从自然语言问题快速看懂知乎搜索返回观点结构”时才可进入当前 MVP；其他需求写入 Backlog，不得顺手实现。

## 5. 技术边界

- 仓库采用单体 monorepo：`apps/web`、`apps/api`、`packages`、`database`。
- Web：Next.js + TypeScript + Tailwind CSS + Sigma.js + Graphology + Zustand。
- API：FastAPI + Pydantic + SQLAlchemy/Alembic。
- 数据库：PostgreSQL + pgvector；图关系保存在关系表，不引入图数据库。
- 后台分析：MVP 使用单进程后台任务与数据库 Job 状态，不引入外部任务队列。
- 知乎接入：正式运行路径使用官方 HTTP API，并隐藏在 `ZhihuSearchProvider` 后；CLI 只允许用于 Stage 0 探测或本地诊断，业务代码不得解析 CLI stdout。
- LLM 与 Embedding 必须通过 Provider 接口隔离，使用环境变量配置模型、Base URL 和密钥，业务层不得绑定单一厂商 SDK。
- 依赖必须锁定版本并提交锁文件。未经用户确认不得更换核心技术栈。

## 6. 固定业务契约

### 搜索归一化顺序

1. 校验并规范化 `query_text`。
2. 请求知乎搜索 API，`Count=10`。
3. 只保留 `ContentType == "Answer"`。
4. 按 `ContentID` 去重，保留第一次出现的结果。
5. 按 `VoteUpCount DESC` 排序；赞同数相同时保持接口原始顺序。
6. 截断为最多 10 条。
7. 清洗 `ContentText` 中的高亮标签并保存原始返回快照所需字段。

任何改动上述顺序的实现都必须先修改执行方案并获得用户确认。

### 图谱契约

- 节点类型只能是 `QUERY`、`ANSWER`、`CLAIM`、`CONCEPT`。
- MVP 关系只能是 `RETURNS_ANSWER`、`MAKES_CLAIM`、`REFERS_TO`、`SIMILAR_TO`。
- 必须存在主链：`QUERY -RETURNS_ANSWER-> ANSWER -MAKES_CLAIM-> CLAIM -REFERS_TO-> CONCEPT`。
- 不允许生成脱离 Answer 来源的 Claim，不允许生成脱离 Claim 的 Concept。
- `answers.query_id`、`claims.answer_id`、`claim_concepts` 是主链权威事实源；Graph API 必须从这些外键关系派生边，不得另存一套重复的通用 Edge。
- `SIMILAR_TO` 只保存在带 Answer 复合外键的 `answer_similarities` 表中，只允许同一 Query 内连边；相似对按较小/较大 Answer ID 规范化后仅保存一次，并记录 embedding 模型与算法版本。
- Concept 只在单个 Query 内归一化，唯一键为 `(query_id, normalized_name)`；删除 Query 时可安全级联其派生数据。

### AI 提取契约

- 顶层输出字段固定为 `summary`、`stance`、`claims`；每个 Claim 内含 `text`、`evidence_text`、`confidence`、`concepts`。
- `claims` 长度为 0 到 5；`stance` 只允许 `support|oppose|conditional|neutral`。
- 每个 Claim 必须有来自当前 Answer `ContentText` 的证据；证据必须能做规范化子串匹配。
- JSON Schema 验证失败最多重试 2 次；仍失败则标记该 Answer 分析失败，不能阻塞其他 Answer。
- 模型输出是派生数据，必须保存 `model`、`prompt_version` 与时间戳，以便复现。

## 7. 阶段门禁

严格按照 `docs/IMPLEMENTATION_PLAN.md` 的实施前置动作和 Stage 0 到 Stage 9 执行。

1. 开始某 Stage 前先读取该阶段的输入、任务、验收标准和停止条件。
2. 一次只实现当前 Stage 所需内容，不提前实现后续功能。
3. Stage 0 的可重复契约审计，或 Stage 1 到 Stage 9 的自动化测试与人工验收未通过，不得进入下一 Stage。
4. 如果用户明确要求“一次执行完整方案”，可在每个 Stage 通过后自动进入下一 Stage；遇到停止条件必须停下报告。
5. 每个 Stage 结束必须更新 `docs/progress/STAGE_N.md`，列出修改文件、测试命令、结果、已知限制和下一阶段入口。

Stage 0 是硬门禁。若官方接口无法稳定返回 `ContentText`、`VoteUpCount`、`Url`、`ContentID`，或凭证/额度不可用，立即停止；不得用网页抓取或私有 API 替代。

## 8. 编码与修改规则

- 先写失败测试，再做最小实现，再重构；测试必须覆盖本次行为。
- 只修改当前需求相关文件，不顺手重构、改格式或添加“以后可能用到”的抽象。
- 不猜测 API 响应、DOM、字段名称或错误码；以当前官方文档、真实 fixture 和运行结果为准。
- 外部响应先映射为内部 DTO，路由、数据库和 UI 不得直接依赖知乎字段大小写。
- 后端必须使用类型标注；前端不得使用无说明的 `any`。
- 数据库 Schema 变更必须使用 Alembic migration，不得只改 ORM。
- 所有时间保存为 UTC，所有数据库主键和唯一约束必须明确。
- 禁止静默吞错；用户可见错误必须可行动，日志不得泄露密钥或完整敏感响应。
- 删除真实或用户数据、改核心 Schema、换核心技术栈、部署生产环境或开启付费服务前必须停下请求用户确认。专用测试数据库中的可再生 fixture 数据可由测试自动清理。

## 9. 安全与隐私规则

- `ZHIHU_ACCESS_SECRET`、LLM API Key 和数据库密码只能放在本机环境变量或未提交的 `.env`；仓库只提交 `.env.example`。
- 不在代码、测试、fixture、日志、截图、异常信息或提交历史中写入真实 Secret。
- 输入只接受自然语言字符串，不接受用户提供 URL 作为服务器抓取目标。
- 原文跳转只使用官方响应返回并校验过的 `https://www.zhihu.com/answer/` URL。
- 清洗 `ContentText`，不得把外部 HTML 直接注入页面；前端默认按纯文本渲染。
- 对查询长度、请求超时、并发数和请求体大小设置上限。
- 遇到 `20001` 鉴权失败或 `30001` 频率/额度限制时停止重试并返回明确状态。

## 10. 测试与验收纪律

从 Stage 1 开始，每个实现行为至少在适合的层级测试一次；Stage 0 只做真实响应的可重复契约审计，不提前实现业务逻辑：

- 单元测试：过滤、去重、排序、Claim 上限、证据校验、图边生成、错误映射。
- 契约测试：使用脱敏 fixture 验证知乎响应到 DTO 的映射，不在 CI 调用真实知乎 API。
- 集成测试：API + PostgreSQL，验证幂等写入、Job 状态和图数据。
- 前端测试：排序展示、空态、错误态、固定提示、点击联动与安全跳转。
- 端到端测试：自然语言问题到回答列表、图谱、AI Citation 和原文跳转的完整闭环。

完成前必须运行仓库已定义的 lint、typecheck、unit、integration 和 e2e 命令。不得以“应该通过”代替真实运行结果，不得把模拟测试通过描述为真实接口或生产环境可用。

## 11. Git 与受保护文件

- 当前目录初始状态可能没有 `.git`。开始实施后的第一项动作是初始化 Git（若仍缺失）并创建 `feat/zhibian-mvp` 分支；必须在 Stage 0 写入 fixture、测试或审计记录之前完成，不得直接在 `main` 上实现。
- 禁止使用 `git reset --hard`、强制推送或覆盖用户未提交改动。
- `Zhibian_MVP_Architecture_and_Execution_Plan_v0.2.docx` 是只读产品依据，未经用户明确要求不得修改、移动、重命名或删除。
- `AGENTS.md` 和 `docs/IMPLEMENTATION_PLAN.md` 是执行依据；只在范围、验收标准或已验证事实变化时修改，并说明原因。

## 12. 完成报告格式

每次交付必须说明：

1. 实际完成的 Stage 与用户可见结果。
2. 修改的文件和数据库 migration。
3. 实际运行的测试命令及通过/失败数量。
4. 真实知乎 API 是否验证；若没有，必须明确写“未进行真实接口验证”。
5. 剩余风险、未验证项和下一步。

不得把局部测试通过等同于 MVP 已上线，也不得隐瞒因凭证、额度、网络或第三方接口导致的未验证状态。
