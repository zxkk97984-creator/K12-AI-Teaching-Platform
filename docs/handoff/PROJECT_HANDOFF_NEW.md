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
- T11/T13：真实 Tutor/Designer 冒烟与浏览器课堂竖切完成；持久预算 16/20。
- T31：16-case offline synthetic evaluation set and rubric 完成；专用 live 执行和人工 rubric 未获授权/未运行；T32 草稿交付已完成。

## 本地入口

    ./scripts/doctor.sh
    ./scripts/bootstrap.sh
    BOOTSTRAP_DEPLOY=1 ./scripts/bootstrap.sh
    ./scripts/verify.sh
    ./scripts/runner-live-test.sh

配置只从安全环境注入，不复制或打印 .env。runner 用 loopback control plane；没有授权时让
CodeLab 显示 UNAVAILABLE。真实 Knodo 默认不启动；T11/T13 验收进程结束后 PAT 不保留在仓库。

## 当前阻塞

1. T30 合成动画控制器已通过 targeted rerun；正式 senior 内容仍需真实 human-approved chapter，不能用 fixture 替代。
2. T11/T13 真实 Knodo 已完成；T31 专用评测、可信 usage/成本与人工教学评价未运行，T32 草稿不能替代这些证据。
3. G_API_CONTRACT、G_LIVE_BUDGET 已对 T11/T13 路径 PASS；G_AGENT_ISOLATION、G_HUMAN_CONTENT_REVIEW 仍 BLOCKED；G_K12_TERMS 对当前成人参赛者 + 合成数据范围 OUT_OF_SCOPE。
4. T33 不能签署正式发布、真实 K12 开放或学习效果。

## 恢复顺序

先读取 AGENTS.md、progress.json、当前 T32/T33 报告和本文件；确认没有其它写入者。再运行
git status、doctor、bootstrap（不删除卷）。如继续 T31，先由用户明确授权 T31 请求额度并安排真实审校者；不把 Key 存入仓库或报告。
