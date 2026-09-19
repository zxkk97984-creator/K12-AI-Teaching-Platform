# T16 修复报告（attempt 2，REPAIR）｜学生题 DTO 暴露 question id

- 派工：`.herdr-control/dispatches/a7b6070c-3b50-471d-ba4e-35f979734bdf.json|.md`（attempt 2，REPAIR）
- 起因：T17 attempt 1 BLOCKED（`.herdr-control/evidence/T17-blocker-repro.log`：question_key→422、DB uuid→200；A 已独立确认为 T16 缺陷）
- ACK：`.herdr-control/executor/acks/a7b6070c-….json`（先 ACK 后改）；测试锁 B 持有 → 提交时 RELEASED
- 状态：SUBMITTED（等 A 复核）；未写 `.rebuild-kit/progress.json`；未调用 Knodo

## 1. 变更（严格两文件）

| 文件 | 改动 | 说明 |
| --- | --- | --- |
| `backend/app/modules/assessment/quiz_dto.py` | `question_public()` 仅新增一行 `"id": str(question.id)` | 学生 DTO 现暴露作答/提示路由所需的 UUID；其余字段与顺序语义不变 |
| `backend/tests/test_quiz_sessions.py` | 新增 1 个回归用例 `test_dto_question_id_drives_answer_hint_and_rejects_others` | DTO id → 提示 200、作答 200、刷新后 id 稳定且释放反馈；他人同 session/question id → 404 |

before/after 哈希（同算法对照）：quiz_dto.py `0974ea01…` → `a77218e8…`；测试文件 `7d90327a…` → 见 manifest。**未改** router/models/迁移/前端/契约/`.rebuild-kit`。

## 2. 验收（R1–R4）

- **R1**：`"id": str(question.id)` 与 `question_key` 并存；作答前响应全文仍无 `correct_answer`/`explanation`（回归用例断言）；`row.id == UUID(DTO.id)` 与快照一致。
- **R2**：回归用例覆盖——用 DTO 的 `id` 请求提示 → 200；用 DTO 的 `id` 作答 → 200 且 `is_correct` 来自服务端；刷新后同 id 且带 `feedback`；另一学生同 session/question id → GET/作答/提示全部 **404**。
- **R3**：后端全套 **247 passed**（T16 基线 246 + 新增 1）；`ruff check`、`ruff format --check` 全绿；identity/content OpenAPI 导出与冻结文件 **字节一致**；`contracts/SHA256SUMS` 校验 OK。前端 34 / Playwright 14 为 T16 attempt 1 冻结证据，本单未触碰 `frontend/**`（dispatch 禁止），故未复跑。
- **R4**：变更仅上述两文件 + 本报告；`quiz_router.py`/models/迁移未改；`progress.json` 未被执行者写（sha256 与 ACK 记录一致）。

## 3. 命令与 exitcode（真实运行）

| # | 命令 | exit | 结果 |
| --- | --- | --- | --- |
| 1 | `pytest -q`（APP_ENV=test, 55434） | 0 | **247 passed** |
| 2 | `ruff check .`（backend） | 0 | 全绿 |
| 3 | `ruff format --check .`（backend） | 0 | 全绿 |
| 4 | identity OpenAPI 导出 + `diff -q` | 0 | IDENTICAL |
| 5 | content OpenAPI 导出 + `diff -q` | 0 | IDENTICAL |
| 6 | `sha256sum -c contracts/SHA256SUMS` | 0 | 7/7 OK |

证据：`.herdr-control/evidence/T16-repair2-backend.log`（命令、输出、exitcode）。

## 4. 失败与修复（本轮内）

1. 首次回归用例把「提示」放在「作答」之后：一题测验在首次作答即 COMPLETED，之后提示按设计返回 409。修复：用例改为**先提示后作答**（并保留该 409 语义不变，未改实现）。

## 5. 数据/服务类型

- 真实后端 + 真实测试 PG（55434）+ T10 fixture 出题（显式合成草稿，AUTO_VALIDATED）；判分为本地确定性逻辑
- 零外联、零付费；未调用 Knodo；未改开发库结构（仅测试库数据由 pytest fixture 重建）

## 6. 未验证 / NOT_RUN

- 前端 34 与 Playwright 14：本单禁止改 `frontend/**`，未复跑（引用 T16 attempt 1 冻结证据）；A 可在复核时按需重跑
- 真实 Knodo 出题质量、教学效果：仍属后续（门禁 BLOCKED）
- T17 练习 UI：待本修复 PASS 后由 A 重派 attempt 2

## 7. 回滚

- 删除 `quiz_dto.py` 中新增的 `"id"` 一行（其余字段不受影响）；删除新增回归用例。迁移/路由/契约均未动，无需回滚。
- 非 Git：哈希见 `.herdr-control/manifests/T16-repair2-after-executor.json` 与 `T16-repair2-executor-a7b6070c-….json`。

## 8. 下一可执行任务

A 复核本修复 → PASS 后重派 **T17 attempt 2**（练习 UI/交互/键盘等价/刷新恢复/换号清 cache/回同 lesson + 真后端+真 PG+真 Chrome 全链）。
