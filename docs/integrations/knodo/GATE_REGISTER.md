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

- 旧 PAT 已由用户撤销；新 PAT 由用户报告已在本机安全环境配置，但当前 Codex 执行进程读取不到 `KNODO_PAT`。
- Tutor/Designer 的 workspace、Bot、AgentOS 与模型显示名已记录在 `tenant-config.user-reported.json`，状态仍是 `USER_REPORTED_NOT_LIVE_VERIFIED`。
- 截至本次更新没有登录绕权、浏览器 Cookie 提取或真实 Knodo 请求；预算账本尚未产生计数。

## 可以继续的工作

可以继续离线验证真实 mapper。只有新 PAT 对执行进程可见后，才运行
`scripts/knodo-live-smoke.py --live` 的五请求上限序列；失败不自动重试。真实冒烟前不能声称 E2E
Knodo 已接通，也不能向真实 K12 学生开放。
