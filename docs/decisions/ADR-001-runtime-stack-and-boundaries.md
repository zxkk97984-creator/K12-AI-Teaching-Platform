# ADR-001：运行栈与本地/平台/runner职责

状态：ACCEPTED（设计冻结，尚未部署验证）  
日期：2026-09-18

## 决策

- 前端固定为 React + TypeScript + Vite。
- 后端固定为快速模块化的 FastAPI + Python 3.12；业务事实写入 PostgreSQL。
- Knodo 承担通用教学 Agent 运行和内容草稿生成；本地负责学生权限、课程版本、教学状态、答题判分、证据记忆、资源发布和审计。
- 代码执行只进入独立受限 runner；API 不挂 Docker socket，学生容器不接触宿主 `/home`、开发数据库或管理凭据。
- CareerMate 的 Next.js/SQLite/Prisma 和 K12 旧运行结构都不作为新架构。

## 原因

旧的 K12 已证明确定性判分、学习事件和 CodeLab 需求值得保留，但其启动、内容源和聊天链路不能作为新权威。CareerMate 提供的是平台/候选分层模式，不是技术栈。

## 后果

- 任何平台输出先验证 owner、revision、来源和允许动作，再交给本地业务服务。
- T04 只建立这个架构的最小可运行骨架，不把未验证的平台能力画成已接通。
