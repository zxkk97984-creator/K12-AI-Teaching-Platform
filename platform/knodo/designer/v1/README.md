# Designer 交付资产 v1

- `system-prompt.md`：Designer 系统提示词（本目录为维护入口）。
- `bot-profile.json`：角色、operation、绑定 Skill 与可接收/禁止接收清单。
- `examples/quiz-draft.sample.json`：来自冻结契约的题稿样例，只用于“答案不进入学生可见投影”的自动校验。

绑定 Skill：`k12-assessment-author`（QUIZ_DRAFT）、`k12-content-author`（LESSON_PACKAGE_DRAFT）。

Designer 的答案与解析属于服务端私有产物：本发布**不包含**任何答案素材（见 `bundles/designer-private/`）。
本目录记录本地资产版本；运行目标以 `/admin/ai` 的数据库配置为准。`QUIZ_DRAFT` 支持真实 Knodo；课程包业务任务 `LESSON_PACKAGE_DRAFT` 目前只开放 fixture，真实模式明确返回未开放状态，不能把协议或插件准备完成当作该流程已开放。

完整 Plugin 上传使用 `plugin-k12-assessment-author.zip`、`plugin-k12-content-author.zip`；根目录为 `SKILL.md` 的 `skill-*.zip` 只用于单独 Skill 上传。插件和系统提示词分别配置，内容管理仍由本地审核／发布接口完成。

学生可选择 1–20 道题。接入应用将题组拆为每批最多 5 题的 QUIZ_DRAFT 请求，单次请求与响应仍遵守现有协议。应用保存每个已校验批次、排除重复题目，全部完成后合并为私有题组；重试只补齐未成功批次。单次模型批量大小不代表学生题组的总题数上限。

每批出题的等待时间使用 `KNODO_DESIGNER_TIMEOUT_SECONDS`，默认 300 秒，可配置 30–600 秒。超时不自动再次调用；学生重试时继续尚未校验的批次。选择、判断与排序题分别使用协议规定的答案字段，三级提示必须恰好三条。
