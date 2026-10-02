# Knodo《常用 API》简要说明

更新日期：2026-09-30。文档页访问是否需登录取决于当前会话；本文依据 [Knodo 官方完整文档](https://knodo.vip/llms-full.txt) 中的[常用 API](https://knodo.vip/docs/api/simple-api)及实际 HTTP 适配整理。`source-snapshots` 保存的是早期调查证据，不是当前配置快照。

## 1. 文档讲了什么

文档说明四种 API 调用身份与凭证：Knodo 网页 Cookie、独立站点授权 Cookie、后台/脚本 PAT，以及
工作空间 Agent 的内置令牌；并列出工作空间、知识文件、插件、任务、Chat/Bot Chat、会话历史等常用
接口。对本项目最重要的是 PAT 认证、Bot Chat 首轮/续聊和工作空间会话查询。

## 2. 适合什么场景

- 服务端后台、自动化脚本、CI/CD、第三方集成：使用 PAT 调 Knodo 平台域名下的 `/api/v1/...`。
- 已登录的 Knodo 页面：使用登录 Cookie 和相对路径。
- 独立站点前端代表访问者：使用站点授权前缀和 `knodo_site_access`，不能与 PAT 混用。
- 工作空间 Chat 内 Agent：使用平台注入的地址、令牌和 workspace ID。

本项目属于第一类：K12 后端持有 PAT，浏览器和学生侧永远不接触 PAT。

## 3. 关键操作步骤

1. 在个人设置创建 PAT，选择完成任务所需的能力分类并设置有效期。
2. 后端请求头使用 `Authorization: Bearer <PAT>`，请求地址使用 Knodo 平台域名。
3. 调用 `POST /api/v1/bots/{botId}/chat/completions`，首轮发送 `messages`；续聊追加上轮返回的
   `conversationId`。
4. 非流式响应从 `choices[0].message.content` 读取正文，并记录 `conversationId`、`model`、
   `finish_reason` 和官方返回的 usage。
5. 需要核对会话所属 workspace 时，再读取对应 workspace 的会话消息或状态接口。
6. 本项目在 `/admin/ai` 保存服务端目标与路由，不接受学生指定的 Bot 或工作空间；创建本地会话时固定教师快照，目标／提示词版本变化时重建远端会话。

## 4. 使用注意事项

- PAT 代表创建者本人，不提升权限；还会检查令牌能力分类和创建者当前业务权限。
- 当前 PAT 不再依靠历史资源范围收窄访问，因此优先使用专用低权限账号和最小能力分类。若组织不允许
  邀请专用账号，只能使用管理员 PAT 时，按实际所需配置调用和只读核验能力，设置有效期；凭据轮换时同步更新运行配置并重启，撤销正在使用的 PAT 会中断服务。
- PAT 只放服务端环境变量；不要提交、打印、截图或发给浏览器。
- Bot Chat 的 `model` 只是兼容字段，实际使用 Bot 配置模型；本项目不发送该字段。
- 官方默认 `permissionMode` 为 `bypassPermissions`，本项目显式发送较保守的 `default`。
- 教学调用支持 SSE；记忆整理使用非流式调用。最终结果都严格解析单个 JSON 对象，
  教学返回不接受 Markdown 包裹，记忆解析允许原始 JSON 或一个完整的 JSON 代码块，仍不接受前后说明、多对象、截断输出或 `finish_reason != stop`。
- 官方未说明 Bot Chat 的远端取消和幂等语义；本项目不自动重试，超时/读失败按“可能已受理”处理。
- 429 只表示限流，不能自行解释为余额不足；费用只采用平台账单，不按字符数估算。
- 记忆 worker 可有限重试明确的 429；上游是否受理不明的超时保持待重试状态，不反复自动调用。失败不会阻止已经保存的教学回复。

共享课堂／教研空间的 `memoryEnabled` 与 `memoryPluginEnabled` 均需明确为 `false`，还需解除跨学生共享的 `knodo-mem` Skill。平台学生账号的个人记忆由本地服务隔离，不能用 PAT 所属 Knodo 用户的原生记忆代替。

## 5. 原生受控检索调查（2026-10-02）

本次重新读取[官方完整文档](https://knodo.vip/llms-full.txt)的记忆系统与常用 API 章节，
下载正文 SHA-256 为 `e94644524095f7355a278e763b5059137a2217280cbccf6d242cf00c958afd7e`。
官方列出 `/api/v1/memories`、多种 scope、来源／版本／owner 查看与删除 observation；
管理页面禁止直接新增和编辑，新增及修正来自 runtime、flush、反馈或审批。
这些说明没有给出可直接实施的记忆写入／检索请求响应 schema，也没有证明同一 PAT 下的 K12 学生隔离。

学生隔离、受控写入、候选先回本地、账号与本地 ID／版本映射、更正遗忘同步、真实接口与失败回退，
六项均待隔离空间与正式契约核验；资源尚未分配不代表能力不支持。
因此当前继续采用 Knodo 提取、本地管理、关键词与分类召回，未启用原生适配器或共享空间记忆。
本地更正／遗忘后的未知新表述需学生确认；不可核对来源、版本或有效期的旧摘要不再注入。
