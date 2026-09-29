# Designer 交付资产 v1

- `system-prompt.md`：Designer 系统提示词（本目录为维护入口）。
- `bot-profile.json`：角色、operation、绑定 Skill 与可接收/禁止接收清单。
- `examples/quiz-draft.sample.json`：来自冻结契约的题稿样例，只用于“答案不进入学生可见投影”的自动校验。

绑定 Skill：`k12-assessment-author`（QUIZ_DRAFT）、`k12-content-author`（LESSON_PACKAGE_DRAFT）。

Designer 的答案与解析属于服务端私有产物：本发布**不包含**任何答案素材（见 `bundles/designer-private/`）。
本目录记录本地资产版本；运行目标以本机运行配置为准。
