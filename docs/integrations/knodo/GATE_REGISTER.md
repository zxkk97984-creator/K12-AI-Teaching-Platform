# Knodo 与外部门禁登记

更新：2026-09-18  
原则：门禁只能由对应授权来源转 PASS；公开文档、本机已有 Key、fixture 和历史报告都不能代替授权证据。

| 门禁 | 当前状态 | 已有证据 | 缺失证据/负责人 |
|---|---|---|---|
| `G_API_CONTRACT` | BLOCKED | 公共文档快照、路由、部分字段和登录重定向 | 受权租户下完整脱敏 wire、续聊/SSE/取消/幂等/限额；平台执行者 |
| `G_LIVE_BUDGET` | BLOCKED | 无 | 调用目的、最大请求数、积分或费用上限；用户明确授权 |
| `G_AGENT_ISOLATION` | BLOCKED | 无 | 会话、文件、记忆、工具、运行身份和撤销的实测；团队技术验收 |
| `G_K12_TERMS` | BLOCKED | 隐私政策第10节明确不面向16岁以下未成年人 | 比赛租户及下游K12处理安排；用户/赛题组/平台 |
| `G_HUMAN_CONTENT_REVIEW` | BLOCKED | 无 | 四档示范课和正式资源的真实审校签字；真实审校者 |

## 本机事实

- 当前没有 `KNODO_PAT`、`KNODO_API_TOKEN`、`KNODO_BOT_ID`、`KNODO_WORKSPACE_ID` 环境变量。
- 存在其他服务的 `OPENAI_API_KEY` 不构成 Knodo 预算授权，本任务未读取其值、未调用模型。
- 没有登录绕权、浏览器 Cookie 提取或付费请求。

## 可以继续的工作

在以上门禁保持 BLOCKED 时，可以继续开发身份、课程、本地 schema、fixture 适配、UI、判分、runner 和离线回归；不能声称 E2E Knodo 已接通，不能向真实 K12 学生开放。
