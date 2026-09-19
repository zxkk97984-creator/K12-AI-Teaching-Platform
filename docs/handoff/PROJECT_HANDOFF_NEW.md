# K12 新项目技术交接

## 当前基线

- 目标目录：/home/zxk/Projects/K12
- 当前本地 Git 分支：main；无远端、无 push、无历史重写。
- 最近提交：eab362a（T32 草稿交付与最终状态更新；实现检查点 5821daa）；前序本地 readiness 提交 778315c，T32/T33 文档提交 dcb55a2，T31 提交 dec81d8，T30 提交 ff0a926，T29 提交 0a40876。
- 本轮唯一源码/测试/进度/Git 写入者：当前单 Agent；旧 Herdr/A-B/旧仓库只读。
- 发布范围：synthetic_competition_prototype_until_authorized。

## 已验证

- FastAPI/React/Vite/PostgreSQL 独立启动；T29 bootstrap 两次幂等，Compose API/worker/web/PG readiness。
- T23–T26 CodeLab：不可变任务、真实 Docker runner、可信判分/fixture feedback、CodeMirror、owner/CSRF/
  draft/run/feedback/export/delete。
- T27 语音能力明确 unavailable/文本 fallback；T28 安全与窄范围 CODELAB_ONLY 隐私回归。
- T30：333 backend、101 frontend、既有 21 browser passed + 1 explicit animation skip；本轮合成动画控制器 targeted rerun 1 passed、5 real Docker.
- T31：16-case offline synthetic evaluation set and rubric，live gate fail-closed；T32 草稿交付已完成。

## 本地入口

    ./scripts/doctor.sh
    ./scripts/bootstrap.sh
    BOOTSTRAP_DEPLOY=1 ./scripts/bootstrap.sh
    ./scripts/verify.sh
    ./scripts/runner-live-test.sh

配置只从安全环境注入，不复制或打印 .env。runner 用 loopback control plane；没有授权时让
CodeLab 显示 UNAVAILABLE。真实 Knodo 不启动。

## 当前阻塞

1. T30 合成动画控制器已通过 targeted rerun；正式 senior 内容仍需真实 human-approved chapter，不能用 fixture 替代。
2. T31 真实 Knodo wire、Bot/Skill/bundle、usage、预算、成本、人工教学评价均未运行；T32 草稿已交付但不能替代这些证据。
3. G_API_CONTRACT、G_LIVE_BUDGET、G_AGENT_ISOLATION、G_K12_TERMS、G_HUMAN_CONTENT_REVIEW 均 BLOCKED。
4. T33 不能签署正式发布、真实 K12 开放或学习效果。

## 恢复顺序

先读取 AGENTS.md、progress.json、当前 T32/T33 报告和本文件；确认没有其它写入者。再运行
git status、doctor、bootstrap（不删除卷）。如继续平台工作，先由用户/平台负责人补齐
T11/T13 契约、预算、隔离和条款，再运行 verify-live；不把 Key 存入仓库或报告。
