# Knodo 收尾清单

这是用户/平台操作清单，不是“已经真实接通”的声明。当前范围固定为成人参赛者 + 合成学生数据。

## 已完成

- Tutor Workspace：`cmu93gg8q00xia0ns0cm1ugq8`
- Tutor Bot：`c15bd075-cf3b-422f-9655-b88a3c259769`
- Designer Workspace：`cmu93fuj000x5a0nsgzvf1iq7`
- Designer Bot：`23caf7d4-d416-45f8-b1d1-6086b59a1ae5`
- 两个 Bot 的 AgentOS/模型显示配置：`Claude Code` / `GLM-5.1`（用户报告，待 API 实测返回核对）
- 官方 Bot Chat 首轮/续聊契约已实现；PAT 只从后端环境变量读取。
- T11/T13 合计真实请求上限 20；禁止自动重试、充值、升级或超额继续。
- 旧 PAT 已撤销；新 PAT 已由用户报告存入本机安全环境。
- PAT 由管理员账号创建，因为当前组织没有邀请专用测试账号的权限；这是受控例外，不代表最小业务权限。

完整非秘密配置在：
`/home/zxk/Projects/K12/docs/integrations/knodo/tenant-config.user-reported.json`。

## T11 真实冒烟结果

T11 已 DONE：Tutor 首轮、同一会话续聊和 Designer 题稿均通过冻结 Schema；实际模型
`knodo/GLM-5.1`、运行时 `CLAUDE_CODE`。超时与字段错误均已保留并完成只读对账。

管理员 PAT 只应勾选 `AI / Chat 调用`。不要为冒烟增加组织管理、知识库写入、插件写入、任务写入或
会话历史与元数据管理能力；若当前密钥包含这些多余能力，应撤销并重新创建一个短有效期密钥。

输出文件（无需自行寻找）：

- `/home/zxk/Projects/K12/docs/integrations/knodo/live-smoke.redacted.json`
- `/home/zxk/Projects/K12/storage/private/knodo-request-budget.json`（本机私有、Git 忽略）
- `/home/zxk/Projects/K12/docs/acceptance/T11.md`

持久预算账本当前 13/20，剩余 7 次。不要手工删除或修改预算账本来恢复次数。

## 接下来依次做

1. 审查 `live-smoke.redacted.json`，确认无 PAT、Cookie、完整私人正文或真实学生数据。
2. 将租户实测的 Bot/workspace/runtime/model/续聊结果写回 T11 证据；不能只凭 HTTP 200。
3. T13 用同一合成课程跑真实一课闭环，验证已实现的后端 `conversationId` 持久绑定；两个合成学生
   必须保持隔离。
4. T13 后运行相关真实回归，再执行 T31 固定四学段评测；所有真实调用继续使用同一个 20 次账本。
5. 根据真实结果补 T32 参赛文档，最后做 T33 放行复核。

## 仍未解除的门禁

- `G_AGENT_ISOLATION`：仍需两个合成学生的会话、文件、记忆、工具和执行身份隔离实测。
- `G_HUMAN_CONTENT_REVIEW`：正式公开课程仍需真实人员审校；Agent 不能代签。
- `G_K12_TERMS`：当前成人参赛者 + 合成数据原型不受其阻塞；若扩展到真实未成年人，必须重新处理。

在 T11/T13 真实证据完成前，项目仍是合成本地竞赛原型，不得宣称真实 Knodo 教学闭环已放行。
