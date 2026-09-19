# 旧功能迁移范围

旧K12基线：`696364ff54c99f711e1cddd7364c9ac4d5282943`。`REUSE`只表示精选资产或规则，不表示复制旧架构。

| 旧能力 | 处置 | 新落点 | 原因 | 责任任务 |
|---|---|---|---|---|
| 账号登录、档案、偏好、头像 | REBUILD | identity + settings | 保留需求，重建服务端会话、权限和四档学段模型 | T05 |
| 三档学段与年级派生 | REBUILD | stage policy + server validation | 旧实现把1–6合并；新实现四档并保留未知年级 | T01, T05 |
| 25本课程、章节、静态图解 | REUSE | curriculum source/published | 精选课程资产需带来源、许可证、修订和审校状态迁移，不复制整仓运行结构 | T01, T06 |
| 课程阅读与选中文本解释 | REBUILD | content + teaching | 保留需求，重新核对chapter/block所有者和版本边界 | T06, T08, T14 |
| 桌宠、拖拽、换装 | DEFER | optional presentation | 可选呈现，不计教学动画，不能阻塞核心教学闭环 | — |
| 教师人格切换 | REBUILD | teacher presentation policy | 展示语气可保留，但不能覆盖学段策略和安全规则 | T14 |
| 聊天历史与长对话 | REBUILD | conversation + knodo binding | 本地消息为权威，Knodo会话为远端绑定；答案不能进入Tutor共享历史 | T10, T12 |
| 出题、判分、提示、错题 | REBUILD | assessment + learning | 保留快照和确定性判分思想，重建题目所有权、答案隔离和提示状态 | T15, T16, T17, T18 |
| 阅读进度、显式完成、时长 | REBUILD | learning events | 完成活动与掌握证据分离，滚到底或耗时不等于掌握 | T14, T18 |
| 记忆、证据质疑、编辑、遗忘 | REBUILD | memory | 保留可追溯和用户控制，简化为证据投影与候选确认 | T18 |
| Episodes/agent.md导出 | DEFER | growth export | 成长时间线保留；Markdown导出不是R1核心，避免第二套记忆系统 | T18 |
| 推荐与唯一下一步 | REBUILD | recommendation | 由真实答题、提示、完成和偏好驱动，GET只读并给理由 | T19 |
| 自建Embedding/RAG与旧向量 | REMOVE | Knodo knowledge bundle + local context builder | 不迁移运行实现；课程上下文由版本化知识包和本地受控选择提供 | T06, T09 |
| PostgreSQL任务队列与Worker | REBUILD | jobs | 保留可靠机制，重建幂等、租约、重试、死信和心跳 | T12, T29 |
| 语音ASR/TTS | DEFER | voice adapter | 文本主链路先行；无真实验证时不显示为可用 | T27 |
| CodeLab、沙箱与可信判分 | REUSE | codelab + runner | 复用任务素材和确定性测试思想；运行与判分在隔离runner重验 | T23, T24, T25, T26 |
| 后台课程管理 | REBUILD | authoring + admin | 重建草稿、来源、发布、资源、Bot版本和审核日志 | T06, T22 |
| MinIO/Redis等基础设施声明 | REMOVE | none; introduce only with ADR/evidence | R1没有明确存储/缓存需求时不部署占位基础设施 | — |
| 旧迁移、旧数据库、未审题、缓存 | REMOVE | none | 不迁入新权威库；只按清单迁移可追溯课程和测试思想 | — |

## 明确不做

- 不把旧 Next.js/SQLite/Prisma 结构迁入新平台；技术栈固定为 React+TS+Vite、FastAPI/Python 3.12、PostgreSQL。
- 不自研第二套通用 Agent 执行循环、隐藏直连 LLM 主链路或自建向量 RAG。
- 不把旧库、旧迁移、未审题或缓存复制进新权威数据库。
- 不删除旧仓库中的记忆、语音、CodeLab 等能力；只按本表明确重建或延后。
