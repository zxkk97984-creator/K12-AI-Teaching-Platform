# Designer 交付资产 v1

- `system-prompt.md`：Designer 系统提示词（本目录为维护入口）。
- `bot-profile.json`：角色、operation、绑定 Skill 与可接收/禁止接收清单。
- `examples/quiz-draft.sample.json`：来自冻结契约的题稿样例，只用于“答案不进入学生可见投影”的自动校验。

绑定 Skill：`k12-assessment-author`（QUIZ_DRAFT）、`k12-content-author`（LESSON_PACKAGE_DRAFT）。

Designer 的答案与解析属于服务端私有产物：本发布**不包含**任何答案素材（见 `bundles/designer-private/`）。
本目录记录本地资产版本；运行目标以 `/admin/ai` 的数据库配置为准。`QUIZ_DRAFT` 支持真实 Knodo；课程包业务任务 `LESSON_PACKAGE_DRAFT` 目前只开放 fixture，真实模式明确返回未开放状态，不能把协议或插件准备完成当作该流程已开放。

完整 Plugin 上传使用 `plugin-k12-assessment-author.zip`、`plugin-k12-content-author.zip`；根目录为 `SKILL.md` 的 `skill-*.zip` 只用于单独 Skill 上传。插件和系统提示词分别配置，内容管理仍由本地审核／发布接口完成。
