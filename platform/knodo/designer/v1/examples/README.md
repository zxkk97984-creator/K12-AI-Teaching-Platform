# 题稿样例（仅用于契约与答案分离校验）

- `quiz-draft.sample.json`：来自冻结契约的合成示例（`contracts/examples/quiz-draft.json`，逐字节一致）。
- 它包含 `correct_answer` 与 `explanation` 这类**服务端私有字段**，只用于验证：
  1. 样例仍然满足冻结 schema（由 `contracts/test_contracts.py` 校验，`./k12 check` 每次运行）；
  2. 由后端生成的“学生可见投影”（题干/选项/分层提示/来源）中不含 `correct_answer`、`explanation`
     或解析全文（`scripts/package-knodo.py verify` 自动断言）。
- 本样例是合成内容，不含真实学生数据；它**不进入** Tutor 包与课堂知识包（`bundles-classroom.zip` 只含
  `bundles/classroom/**`）。
