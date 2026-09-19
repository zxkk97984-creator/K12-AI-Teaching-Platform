# Git 基线验收记录

## 冻结点

- 项目：`/home/zxk/Projects/K12`
- 冻结时间：2026-09-20（本地 Asia/Shanghai；以提交时间为准）
- 分支：`main`
- 远端：无；本轮不 push
- 基线性质：当前工作区快照，不代表所有功能或外部门禁通过

## 接管时的真实状态

- T00–T10、T12、T14–T22：`DONE`，沿用已有逐任务验收记录。
- T11、T13：`BLOCKED`，真实 Knodo 契约/预算门禁仍未满足。
- T23：`IN_PROGRESS`，dispatch `5484f19f-7430-4a8f-91ec-de44d7ace2e2`，attempt 1。
- T23 已收到执行者 ACK，但执行者窗格当前无前台 Agent/测试进程，未提交 T23 交付证据；不将其记为完成。
- 共享测试锁和 Herdr 控制记录保留在本地，不纳入 Git 动态状态。

## 验证依据

M4 阶段报告记录本地范围的后端 293 项、前端 98 项、浏览器 21 条、契约 38 项通过；
真实 Knodo、人工审校、未成年人适用和 Docker runner 等未验证项仍按原门禁记录。
这些历史结果作为接管依据，不被本次基线改写。

## 纳入范围

纳入源码、测试、迁移、课程/契约源、锁文件、启动脚本、脱敏计划和验收 Markdown。
排除依赖目录、构建产物、数据库/上传/缓存、快照、Herdr 动态控制记录、凭据、浏览器状态、
规划附件 DOCX 和二进制 ZIP。具体规则见根 `.gitignore` 与
`docs/operations/GOAL_GIT_POLICY.md`。

## 未验证与后续

- T23 尚未独立复核；其后 T24–T33 尚未完成。
- G_API_CONTRACT、G_LIVE_BUDGET、G_AGENT_ISOLATION、G_K12_TERMS、
  G_HUMAN_CONTENT_REVIEW 均保持 `BLOCKED`。
- 下一步从同一 T23 dispatch 恢复，不重派、不重做已完成任务。
