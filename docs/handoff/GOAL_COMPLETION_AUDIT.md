# Goal completion audit

审计日期：2026-09-20

本文件按本轮 Goal 的实际范围逐项核对权威证据。它不是发布批准，也不把缺失证据视为通过。

## 1. 单 Agent、目录与 Git 边界

| 要求 | 状态 | 权威证据 |
| --- | --- | --- |
| 固定目录 `/home/zxk/Projects/K12` | PASS | `AGENTS.md`、实际 `realpath` |
| 单 Agent 写入，不启动 Herdr/A/B | PASS | `AGENTS.md`、历史锁为 `RELEASED`、无其他 K12 写入进程 |
| 本地 Git，不添加远端、不 push、不改写历史 | PASS | `git remote -v` 为空；本地提交 `5bb5653`、`6ed898e` |
| 不提交 PAT/Cookie/真实学生数据 | PASS（本轮 diff） | staged/diff 秘密扫描；T11/T13 脱敏证据；私有预算账本被 Git 忽略 |
| 仅成人参赛者与合成学生数据 | PASS（声明范围） | `release_scope`、T11/T13 报告、`G_K12_TERMS.scope_note` |

## 2. 核心任务完成度

`.rebuild-kit/progress.json` 中 38 个必需任务仅 T31、T33 未完成；O01—O04 为未经用户点名的可选项，不属于本轮执行范围。

| 任务/要求 | 状态 | 结论 |
| --- | --- | --- |
| T11 真实 Knodo 契约与两类 Bot 冒烟 | DONE | Tutor 首轮/续聊与 Designer 题稿通过冻结契约。 |
| T13 真实持久化与浏览器闭环 | DONE | Chrome → FastAPI → Knodo → PostgreSQL → Chrome；A 两轮续聊、B 独立会话、无来源拒答、预算证据齐全。 |
| T31 教学质量与成本验收 | BLOCKED | 16 条离线集已验证；T11/T13 可复用真实样例存在，但 T31 专用调用未获授权，人工 rubric 未执行，可信 usage/成本缺失。 |
| T32 参赛文档草稿 | DONE | 报告、演示和集成文档存在并明确标注未验证项。 |
| T33 最终重复验收与放行 | BLOCKED | 本地重复验收与交接已完成；受 T31 和真实人工内容审校阻塞，不能签署正式发布。 |

## 3. 门禁审计

| 门禁 | 状态 | 证据强度与剩余缺口 |
| --- | --- | --- |
| G_API_CONTRACT | PASS | 官方限定 Bot Chat 契约 + T11/T13 真实租户证据；未文档化能力仍失败关闭。 |
| G_LIVE_BUDGET | PASS（T11/T13） | 上限 20，当前 16/20；不得自动重置或挪给 T31。 |
| G_AGENT_ISOLATION | BLOCKED / PARTIAL | A/B owner/session/conversation 隔离已证明；平台文件、自动记忆、工具与执行身份未证明。 |
| G_K12_TERMS | OUT_OF_SCOPE_FOR_CURRENT_RELEASE | 仅成人参赛者 + 合成数据；若改为真实未成年人必须重新打开。 |
| G_HUMAN_CONTENT_REVIEW | BLOCKED | 没有真实审校者签署；Agent 不能代签。 |

## 4. 当前验证基线

- 后端：371 passed，1 skipped（未配置真实 CodeLab runner bridge）。
- T13 PostgreSQL focused：4 passed；首次 3 failed/1 passed 的测试替身来源错误已保留并修复。
- 前端：101 passed；typecheck 与 production build PASS。
- T13 live browser：三次真实 Tutor run 均成功；最终只读重开 1 passed；默认无 `T13_LIVE=1` 时明确 skip。
- Knodo evidence validator、38-task kit validator、Ruff、JSON 解析与 diff 检查 PASS。
- T24 真实 Docker runner 5 passed、T30 浏览器与 Compose 证据沿用未受本轮测试/文档变更影响。
- CareerMate 只读 source-audit 的外部漂移失败仍保留；未重置或改写旧参考仓。

## 5. 目标完成判定

当前不能把整个 Goal 标记为完成，因为 T31 与 T33 是必需任务且仍缺少：

1. 用户明确授权的 T31 调用目的与请求上限；现有剩余 4 次只属于 T11/T13。
2. 版本化 T31 评测集的真实平台执行结果。
3. 真实人员完成的科学性、适龄性、引用支持与练习有效性 rubric。
4. T31 完成后的 T33 用户最终验收与放行决定。

在上述外部条件出现前，安全停止点是：**可运行的本地合成竞赛原型 + 已验证的真实 Knodo 合成链路；不宣称正式教学质量、真实学生开放或平台完整隔离。**
