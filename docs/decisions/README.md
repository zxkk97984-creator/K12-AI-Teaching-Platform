# 架构决策索引

- `ADR-001-runtime-stack-and-boundaries.md`：React/Vite、FastAPI/Python 3.12、PostgreSQL，以及本地/平台/runner职责。
- `ADR-002-bots-and-no-second-agent-loop.md`：Tutor/Designer两类Bot，不建第二套循环、RAG或隐藏直连LLM。
- `ADR-003-ownership-revision-and-action-validation.md`：owner、revision、幂等、来源和允许动作。
- `ADR-004-buffered-structured-delivery.md`：R1完整结构校验后交付，不把JSON碎片显示给学生。
- `ADR-005-knowledge-and-data-authority.md`：课程、答案、成绩、权限和发布状态的本地权威。

这些ADR是设计冻结，不代表服务、Bot、数据库或真实Knodo联调已部署。契约副本及验证器见 `contracts/`。
