# 单 Agent 接管说明

## 范围

本说明记录 2026-09-20 单 Agent 继续 K12 重建的模式变更。当前 Agent 是唯一允许修改本项目源码、测试、进度、交接文档和本地 Git 的写入者。

旧 Herdr 控制文件、派工单、A/B 角色和 ACK 保留为历史恢复材料；本轮不启动 Herdr、不创建第二编码 Agent、不等待旧角色回执，也不把历史回执当作本轮验收。

## 安全接管证据

- 目标 realpath：`/home/zxk/Projects/K12`。
- 接管前 Git：`main`，HEAD 为 `ecb3038`，工作区无普通未提交改动，无远端写入。
- 2026-09-20 00:50（Asia/Shanghai）检查到 Herdr 服务进程仍在，但其工作目录为 `/home/zxk/Projects`；三个关联终端仅处于等待输入状态，没有子命令、测试、迁移或代码执行进程。
- `.herdr-control/` 最近动态写入停在 00:05 左右；`shared-test.lock` 原持有人为 `EXECUTOR_B`，对应已无执行器进程。
- 原锁文件未删除。依据文件内 release rule，保留原 holder、dispatch、purpose 和历史时间，并将陈旧锁安全转移为 `RELEASED`，释放给本轮单 Agent。

## 工作规则

本轮只使用本地历史，不添加远端、不 push、不重写既有历史；旧 K12、CareerMate、旧数据库和旧服务保持只读。真实 Knodo、付费调用、人工审校、真实未成年人数据和公网部署仍各自需要门禁与授权。

每个任务都要经过实现、正反例测试、同一 Agent 的第二遍针对性复核、必要修复、验收报告和真实 progress 登记。第二遍复核是自我复核，不称为独立评审。
