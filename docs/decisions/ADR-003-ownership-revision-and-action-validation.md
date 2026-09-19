# ADR-003：owner、revision、幂等与允许动作

状态：ACCEPTED  
日期：2026-09-18

## 决策

- 每个学生可见资源和业务对象都有本地稳定 owner ID；平台调用者、PAT创建者和学生身份不能混用。
- 任何会改变持久状态的请求都必须带幂等键；涉及课程、题目、资源、学习状态的写入必须带 `base_revision`。
- 平台输出中的来源引用只能指向本轮 `knowledge_context` 的三元组 `(source_id, revision, locator)`。
- 平台输出中的动作只能是本地允许集合中的 `OFFER_QUIZ/OPEN_RESOURCE/OPEN_ANIMATION/OPEN_CODE_TASK`，且目标必须已发布、适龄、属于当前章节。
- 过期 owner、revision、章节或 run 的结果统一标记 `STALE`，不得覆盖新状态。
- 验收动作必须重新检查 owner、revision、课程版本、状态和过期时间，不只相信候选创建时的校验。

## 原因

AI输出只是建议；模型不能赋予自己权限、修改成绩、跳过版本、执行任意 JS/Shell/SQL或直接发布内容。

## 后果

本地 API 需要统一错误信封和冲突语义：未授权、revision 冲突、幂等冲突、stale、非法输出分别可观察。
