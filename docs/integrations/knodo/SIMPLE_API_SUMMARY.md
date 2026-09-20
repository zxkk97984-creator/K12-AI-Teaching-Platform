# Knodo《常用 API》简要说明

核查日期：2026-09-20。直接访问 `https://knodo.vip/docs/api/simple-api` 会跳转登录页，因此本文依据
Knodo 官方 `https://knodo.vip/llms-full.txt` 中标注“来源：`/docs/api/simple-api`”的完整段落整理。

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

## 4. 使用注意事项

- PAT 代表创建者本人，不提升权限；还会检查令牌能力分类和创建者当前业务权限。
- 当前 PAT 不再依靠历史资源范围收窄访问，因此优先使用专用低权限账号和最小能力分类。若组织不允许
  邀请专用账号，只能使用管理员 PAT 时，应仅启用 `AI / Chat 调用`、设置短有效期，并在测试后立即撤销。
- PAT 只放服务端环境变量；不要提交、打印、截图或发给浏览器。
- Bot Chat 的 `model` 只是兼容字段，实际使用 Bot 配置模型；本项目不发送该字段。
- 官方默认 `permissionMode` 为 `bypassPermissions`，本项目显式发送较保守的 `default`。
- 本项目使用 `stream=false`，严格解析单个 JSON 对象；任何前后说明文字、Markdown 代码块、截断输出
  或 `finish_reason != stop` 都判失败。
- 官方未说明 Bot Chat 的远端取消和幂等语义；本项目不自动重试，超时/读失败按“可能已受理”处理。
- 429 只表示限流，不能自行解释为余额不足；费用只采用平台账单，不按字符数估算。
