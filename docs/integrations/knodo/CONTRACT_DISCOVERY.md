# Knodo 契约调查（T02）

核查时间：2026-09-18  
状态：公开文档已取证；真实租户与完整 wire 仍未验证  
结论：**不通过 `G_API_CONTRACT`，不进行付费或真实学生调用。**

## 1. 已取得的公开证据

| 来源 | 结果 | 快照 SHA-256 |
|---|---|---|
| https://knodo.vip/docs/getting-started/getting-started | HTTP 200 | `beb896db7998499c502d4b300e9d9cd4b7618eef396549a5fc43d763af20a48e` |
| https://knodo.vip/privacy | HTTP 200；第10节明确“服务不面向16岁以下未成年人” | `c7406c93b596dd6a9197866fc8899527bdfa92c6cb413b853cb1c6026db88234` |
| https://knodo.vip/llms.txt | HTTP 200 | `f8dab3cf5fc5ca9a8fde2cfdee47e892705e962559c196af46511ef59042bf91` |
| https://knodo.vip/llms-full.txt | HTTP 200；含 Bot Chat、提交式 Chat、SSE、会话状态和常用 API | `d18b76247807ac06e7098c19f50816e3655b5cafc2d6f39af4914491e63e1fe0` |
| https://knodo.vip/docs/api/simple-api | HTTP 307 → `/login?callbackUrl=...`，未登录；未保存登录正文 | 仅保存响应头 |

原始快照位于 `source-snapshots/`，清单在 `manifest.json`。所有内容来自未认证公共 GET，不含 PAT、Cookie、租户或真实学生数据。

## 2. 公开文档中可确认的形态

- 服务端/脚本使用 `Authorization: Bearer <PAT>`；PAT代表创建者本人，并沿用创建者当前业务权限。
- Bot Chat 公开路由：`POST /api/v1/bots/{botId}/chat/completions`。
- Bot Chat 公开请求字段：`messages`（必填）、`model`、`stream`、`conversationId`、`permissionMode`、`includeToolResults`。
- Bot Chat 公开响应字段：OpenAI Chat Completions 风格的对象、choices、usage 和 `conversationId`；`conversationId` 在公开示例中用于继续会话。
- `stream=true` 被描述为 OpenAI 兼容 SSE，但公开完整文本没有给出 Bot Chat 逐事件 schema。
- 相关通用 Chat 路由包括 submit、stream、messages、status，但它们是不同的调用方式，不能自动替代 Bot Chat 的续聊/取消语义。
- 站点授权前缀不开放 chat SSE 和 Bot Chat `stream=true`；若使用流式，公开文档建议独立站点后台用 PAT 调平台 API，这仍需要真实租户验证。

以上是“公开文档字段”，不是“本租户已验证 wire”。`knodo-wire-evidence.json` 中的 `tenant_verified` 为 false，真实请求、响应、SSE、取消、幂等和限额仍为 null/unknown。

## 3. 尚不能确认

- 比赛租户的真实平台域名、workspace ID、Bot ID、AgentOS 和实际 model ID。
- PAT 对目标 Bot Chat 的真实 scope、速率、额度、错误码和请求 ID 语义。
- `conversationId` 的生命周期、跨学生隔离、并发路由、重复请求、取消和恢复语义。
- Bot Chat 流式事件、工具结果、usage 是否稳定、是否计费及失败后的可恢复状态。
- Bot、Skill、知识包、会话、文件和运行身份的隔离性。
- 低龄学生适用性：公开政策与K12比赛诉求存在冲突，必须取得平台/赛方明确说明。
- 文件生成/下载契约和长期资源 URL；不能从任意 URL 下载。

## 4. 明确的禁止项

- 不从百宝箱复制 `question/user_id/business_data`。
- 不把 OpenAI 的 `messages/tools/response_format` 猜成 Knodo 官方合同。
- 不把本地 `k12.teaching.request.v1` 或 Designer JSON 当 HTTP 请求体。
- 不把 PAT 当学生身份，不把会话 ID 差异当数据隔离，不在日志打印 PAT/Cookie/密钥。
- 不因环境已配置任何 API Key 就调用 Knodo 或消耗额度。
- 不用 fixture 结果宣称真实平台通过。

## 5. 下一项真实联调所需输入

1. 受权比赛租户的脱敏平台域名、workspace ID、两个Bot的ID。
2. 仅后端保存的PAT，以及明确允许的请求次数/积分/费用上限。
3. 平台确认的运行时与模型 ID。
4. 一份脱敏的首次请求、续聊、SSE、取消/超时/429错误响应记录。
5. 平台/赛方对16岁以下适用、数据处理和人工审校的书面安排。

在上述输入齐备前，T10/T11/T13只能使用离线假适配器并保持真实链路为BLOCKED。
