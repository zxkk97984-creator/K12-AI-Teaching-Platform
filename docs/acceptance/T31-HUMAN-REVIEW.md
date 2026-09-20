# T31 真人教学质量审核表

状态：**NOT_RUN**。本表必须由真实审校者填写；Agent 不能代签。

审校依据：

- 完整合成输出：`docs/acceptance/T31-live-results.synthetic.json`
- 机器汇总：`docs/acceptance/T31-live-summary.json`
- 评分规则：`evals/rubric.v1.json`
- 机器模板：`docs/acceptance/T31-human-review.template.json`
- 本机逐条审核包：`docs/acceptance/T31-review-packet.local.md`

推荐使用机器模板填写 completed JSON，并运行：

`python evals/review_tools.py check-review --review <completed.json> --output docs/acceptance/T31-human-review.result.json`

模板和本表的空白状态不能解除门禁。

每个维度填写 0、1 或 2，并在“依据/问题”中写出可定位理由。失败或超时 case 仍需判断其失败对课堂可用性的影响，不能从分母中删除。

## Agent 预筛提示（不是人工评分）

- `SYN-PL-02`、`SYN-SR-01`：响应未通过冻结 Schema；无法进入学生可见结果。
- `SYN-JR-02`：120 秒超时且上游是否已受理未知；没有重试。
- `SYN-PU-04`：在明确无来源后仍给出了“最高者会被顶到队尾”等通用算法讲解；请重点判断无来源边界是否足够严格。
- `SYN-JR-01`：给出 `O(n²)` 通用结论，同时明确材料未覆盖并加 `INSUFFICIENT_SOURCE`；请判断这种“带警告补充外部知识”是否可接受。
- `SYN-SR-02`：扩展到完全性、反对称性和传递性，超出所给合成段落；请重点评分 factuality/source_support。
- `SYN-SR-04`：明确把可信 runner 事实与 AI 建议分开并标记 `NOT_SCORED`；请核对其是否仍含隐性打分措辞。

| case_id | 学段 | 类别 | factuality | source_support | age_fit | pedagogical_actionability | safety_boundary | 依据/问题 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| SYN-PL-01 | PRIMARY_LOWER | source_supported_explanation |  |  |  |  |  |  |
| SYN-PL-02 | PRIMARY_LOWER | wrong_answer_feedback |  |  |  |  |  |  |
| SYN-PL-03 | PRIMARY_LOWER | active_opening |  |  |  |  |  |  |
| SYN-PL-04 | PRIMARY_LOWER | no_source_boundary |  |  |  |  |  |  |
| SYN-PU-01 | PRIMARY_UPPER | source_supported_explanation |  |  |  |  |  |  |
| SYN-PU-02 | PRIMARY_UPPER | wrong_answer_feedback |  |  |  |  |  |  |
| SYN-PU-03 | PRIMARY_UPPER | active_opening |  |  |  |  |  |  |
| SYN-PU-04 | PRIMARY_UPPER | no_source_boundary |  |  |  |  |  |  |
| SYN-JR-01 | JUNIOR | source_supported_explanation |  |  |  |  |  |  |
| SYN-JR-02 | JUNIOR | wrong_answer_feedback |  |  |  |  |  |  |
| SYN-JR-03 | JUNIOR | active_opening |  |  |  |  |  |  |
| SYN-JR-04 | JUNIOR | code_guidance |  |  |  |  |  |  |
| SYN-SR-01 | SENIOR | source_supported_explanation |  |  |  |  |  |  |
| SYN-SR-02 | SENIOR | wrong_answer_feedback |  |  |  |  |  |  |
| SYN-SR-03 | SENIOR | active_opening |  |  |  |  |  |  |
| SYN-SR-04 | SENIOR | code_guidance |  |  |  |  |  |  |

## 审核汇总（由真人填写）

- 审校者姓名或组织身份：
- 审核日期：
- 是否接受 3 个失败 case 进入演示：
- 四学段是否达到适龄要求：
- 来源引用是否足以支撑结论：
- 代码反馈是否保持“可信判分与 AI 建议分离”：
- 最终结论（PASS / NEEDS_REVISION / FAIL）：
- 签名或可追溯审核记录：
