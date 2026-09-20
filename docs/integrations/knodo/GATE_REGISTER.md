# Knodo 与外部门禁登记

更新：2026-09-18  
原则：门禁只能由对应授权来源转 PASS；公开文档、本机已有 Key、fixture 和历史报告都不能代替授权证据。

当前范围决策（用户确认）：本项目只面向成人参赛者，学生身份和课程数据均为合成数据，不使用真实
未成年人资料，也不投入真实教学场景。因此 `G_K12_TERMS` 不阻塞当前合成竞赛原型；它对任何
真实未成年人/正式 K12 发布仍保持 BLOCKED，不能被本范围决策伪装成平台或法律批准。

| 门禁 | 当前状态 | 已有证据 | 缺失证据/负责人 |
|---|---|---|---|
| `G_API_CONTRACT` | PASS（限定非流式 Bot Chat） | 官方 `llms-full.txt` 的 `/docs/api/simple-api` 段落确认 PAT、首轮/续聊请求字段和响应；`knodo-wire-evidence.json` 已固定映射 | 租户兼容性仍待真实冒烟；远端取消、幂等、完整 SSE 未纳入本实现且失败关闭 |
| `G_LIVE_BUDGET` | PASS | 用户授权 T11/T13 合计最多 20 次真实请求；`tenant-config.user-reported.json`；持久预算账本 | 禁止自动重试、充值、升级或超额继续 |
| `G_AGENT_ISOLATION` | BLOCKED | 无 | 会话、文件、记忆、工具、运行身份和撤销的实测；团队技术验收 |
| `G_K12_TERMS` | BLOCKED（当前原型 OUT_OF_SCOPE） | 用户范围决策：成人参赛者 + 合成学生数据；公开隐私政策第10节仍明确不面向16岁以下未成年人 | 若范围扩展到真实未成年人，需比赛租户及下游 K12 处理安排；当前原型不扩展 |
| `G_HUMAN_CONTENT_REVIEW` | BLOCKED | 无 | 四档示范课和正式资源的真实审校签字；真实审校者 |

## 本机事实

- 旧 PAT 已由用户撤销；新 PAT 由管理员账号创建并由用户报告已在本机安全环境配置，但当前 Codex 执行进程读取不到 `KNODO_PAT`。因无法邀请专用账号，管理员身份作为受控例外；只允许 AI / Chat 能力、短有效期并在 T11/T13 后撤销。
- Tutor/Designer 的 workspace、Bot、AgentOS 与模型已由真实 Bot Chat 响应核对；最终 Tutor 首轮、续聊和
  Designer 题稿均通过冻结 Schema，证据见 `live-smoke.redacted.json`。
- 持久预算账本当前为 13/20：6 次模型 POST（含 3 次保留的失败样例）与 7 次只读对账 GET；无自动重试、
  无登录绕权、无浏览器 Cookie 提取。

## 可以继续的工作

T11 的真实 mapper 冒烟已经完成。下一步是 T13：在专用测试 PostgreSQL 上运行持久绑定/双合成学生隔离
测试，再从本地页面走真实一课竖切。`G_AGENT_ISOLATION` 和正式内容人审仍未解除，不能向真实 K12
学生开放。
