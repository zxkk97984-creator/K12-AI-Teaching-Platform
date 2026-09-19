# ADR-002：两类 Knodo Bot，不建立第二套 Agent 循环

状态：ACCEPTED  
日期：2026-09-18

## 决策

只定义两个角色：

| Bot | 操作 | 职责 |
|---|---|---|
| Tutor | `TEACH_TURN`、`CODE_FEEDBACK` | 基于本轮授权上下文给教学建议和代码反馈 |
| Designer | `QUIZ_DRAFT`、`LESSON_PACKAGE_DRAFT` | 生成题稿/课程包草稿，不写正式业务数据 |

- 不依赖 Knodo 原生多 Agent、百宝箱工作流格式或自定义可视化编排。
- 本地不实现第二套通用 Agent 执行循环、不建立自研向量 RAG、不保留隐藏直连 LLM 主链路。
- 平台提示词、Skill 和课程导出包将版本化到 `platform/knodo/`。
- 平台会话、文件、记忆、工具和运行身份是待隔离的外部资源，不能因会话 ID 不同就宣称隔离。

## 原因

业务需要的是可验证的教学运行底座，不是把每个模型/工具编排都搬进本仓。拥有一个平台网关和明确的本地业务服务比维护两套 Agent 状态机安全。

## 后果

真实 Knodo 适配必须通过 `G_API_CONTRACT` 和 `G_AGENT_ISOLATION`；在此之前只有诚实 fixture，不得让 fixture 出现在正式学生流。
