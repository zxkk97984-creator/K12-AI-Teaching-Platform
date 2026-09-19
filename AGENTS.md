# K12 项目本地执行规则

本文件只补充项目级约束；任务目标、依赖、门禁和验收以
`.rebuild-kit/` 中的原任务与当前 `.rebuild-kit/progress.json` 为准。

- 工作目录固定为 `/home/zxk/Projects/K12`；旧 K12、CareerMate、旧数据库和旧服务只读。
- 保持 FastAPI/Python 3.12、React/TypeScript/Vite、PostgreSQL、Knodo Tutor/Designer 与受限 runner 边界。
- 复用现有会话、CSRF、四档学段、课程版本、题目快照和 OpenAPI 生成链；不新增直连大模型兜底。
- 不打印、提交或上传密钥、Cookie、真实学生数据、数据库数据和运行时上传文件。
- 真实 Knodo、付费调用、人工审校、真实未成年人数据和公网部署仍须各自门禁与授权；fixture 不等同真实验收。
- Git 仅使用本地历史；不添加远端、不 push、不 force-push，不重写既有历史。
- Git 筛选、基线和本轮授权的详细规则见 `docs/operations/GOAL_GIT_POLICY.md`。
