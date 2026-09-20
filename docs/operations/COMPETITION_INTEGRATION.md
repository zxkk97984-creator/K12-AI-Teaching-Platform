# 参赛集成与发布状态

## 本地启动顺序

1. scripts/doctor.sh：只检查工具、端口、Docker 和可选 runner health，不杀进程。
2. scripts/bootstrap.sh：唯一迁移/内容/CodeLab/可选 demo 初始化入口；重复运行只 REUSE。
3. BOOTSTRAP_DEPLOY=1 scripts/bootstrap.sh：本地 Compose API/worker/web/PG。
4. scripts/codelab-runner-server.sh：仅在明确允许真实 Docker CodeLab 时启动；绑定 loopback 和控制 token。
5. /health/live 只表示进程；/health/ready 返回 DB、runner、storage 状态。

## 平台接入待办

真实接入顺序固定为：T11 契约/适配 → T13 一节真实课 → 相关安全回归 → T31 真实评测 →
补齐 T32 → T33 最终放行。当前 G_API_CONTRACT 和 G_LIVE_BUDGET 均 BLOCKED，因此
不配置/不调用 Knodo；已有其他服务的 key 也不构成授权。

需要平台/用户提供并由相应责任人核验：登录后完整 Bot wire、续聊/SSE/取消/幂等/usage、
目标 Bot/Skill/bundle 标识、调用目的与最大请求数、租户隔离/撤销、K12 条款，以及四档内容
真实审校记录。当前竞赛原型明确只使用成人参赛者和合成学生数据，K12/未成年人条款不阻塞该
范围；若范围扩展，代码 Agent 不代签这些事项。

## 发布分层

| 层 | 可说 | 不能说 |
| --- | --- | --- |
| 本地离线 | 新项目可启动、PG/worker/runner/浏览器/资源/CodeLab 测试证据 | 真实平台质量、学习效果 |
| 合成参赛原型 | 可按演示脚本复现五类 R1 本地功能 | 真实 Knodo、真实 K12 学生开放 |
| 真实技术验证 | 仅在门禁、预算、租户和合成数据获授权后登记 | 正式教学审校或学生研究 |
| 正式发布 | 需 T33、G_HUMAN_CONTENT_REVIEW、G_K12_TERMS、G_AGENT_ISOLATION | 任何未登记证据 |
