# Stage 6 真实体验版接入执行记录

本文件记录 Stage 6 从 mock 演示切换到受保护真实体验版的实施边界。工作区为
`D:\AI\zhiye`，分支为 `feat/zhibian-mvp`；不修改 `main`，不提交或覆盖真实
Secret，不在未授权前执行线上 migration 或公网发布。

## 接入边界

- 知乎继续使用官方 HTTP 搜索接口，单次 `Count=10`，先过滤 Answer、按
  `ContentID` 去重，再按 `VoteUpCount` 降序。
- 文本使用 DeepSeek 官方兼容接口 `https://api.deepseek.com`，模型
  `deepseek-flash`，JSON 输出、禁用 thinking、单次最大 45 秒。
- 向量使用火山方舟普通按量接口
  `https://ark.cn-beijing.volces.com/api/v3`，模型
  `doubao-embedding-vision-251215`，单文本请求、2048 维、单次最大 20 秒。
- 不使用 Agent Plan `/api/plan/v3` 作为网站后端接口；不把模型密钥放入浏览器。
- production 使用体验码和服务端哈希校验；mock 模式保留离线 fixture 测试。
- 结果按 `legacy`、`mock`、`production` 隔离；真实分析失败可以保留搜索结果和
  有证据的部分主链，向量失败跳过语义相似边。
- 项目侧预算上限为 20 元，其中 18 元允许预占、2 元作为缓冲；不自动充值或
  开启超额付费。

## 执行顺序

1. 先写 Provider、鉴权、隔离和预算失败测试，再做最小实现。
2. 完成本地 API、专用测试 PostgreSQL、前端 lint/typecheck/unit/build 与
   Playwright E2E 验证。
3. 在获得具体授权后，才配置真实 Secret、执行线上 migration、部署 Railway
   和 Vercel，并用预算内问题完成一次浏览器验收。
4. 真实知乎、DeepSeek、Embedding、Neon 和公网结果分别记录；mock 测试不能
   代替真实验证，也不把数组向量存储描述为 pgvector 原生列验收。

## 当前停止点

Provider 和体验码的本地契约实现已开始，真实 Secret 尚未写入，尚未调用真实
第三方接口，尚未执行线上数据库结构变更或公网部署。后续交付必须列出候选
commit、migration、待配置变量、测试结果、预算余额和回退步骤。
