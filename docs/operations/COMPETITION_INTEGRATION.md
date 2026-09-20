# 参赛集成与发布状态

## 本地启动顺序

1. scripts/doctor.sh：只检查工具、端口、Docker 和可选 runner health，不杀进程。
2. scripts/bootstrap.sh：唯一迁移/内容/CodeLab/可选 demo 初始化入口；重复运行只 REUSE。
3. BOOTSTRAP_DEPLOY=1 scripts/bootstrap.sh：本地 Compose API/worker/web/PG。
4. scripts/codelab-runner-server.sh：仅在明确允许真实 Docker CodeLab 时启动；绑定 loopback 和控制 token。
5. /health/live 只表示进程；/health/ready 返回 DB、runner、storage 状态。

## 平台接入状态

真实接入顺序固定为：T11 契约/适配 → T13 一节真实课 → 相关安全回归 → T31 真实评测 →
补齐 T32 → T33 最终放行。T11、T13 与 T31 合成 live 已完成；G_API_CONTRACT/G_LIVE_BUDGET
对已测路径 PASS。默认启动仍不配置 Knodo，避免日常开发产生真实调用。

仍需相应责任人核验：未文档化的 SSE/取消/幂等/usage、目标 Skill/bundle 挂载版本、租户
文件/记忆/工具/执行身份隔离、撤销，以及四档内容真实审校记录。当前竞赛原型明确只使用成人参赛者和合成学生数据，K12/未成年人条款不阻塞该
范围；若范围扩展，代码 Agent 不代签这些事项。

## 发布分层

| 层 | 可说 | 不能说 |
| --- | --- | --- |
| 本地离线 | 新项目可启动、PG/worker/runner/浏览器/资源/CodeLab 测试证据 | 真实平台质量、学习效果 |
| 合成参赛原型 | 可按演示脚本复现五类 R1，并展示 T11/T13/T31 真实 Knodo 合成证据 | 真实 K12 学生开放、正式教学质量 |
| 真实技术验证 | 已登记限定 Bot Chat、浏览器竖切和 16-case 结果 | 正式教学审校或学生研究 |
| 正式发布 | 需 T33、G_HUMAN_CONTENT_REVIEW、G_K12_TERMS、G_AGENT_ISOLATION | 任何未登记证据 |
