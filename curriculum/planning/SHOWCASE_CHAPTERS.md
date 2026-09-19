# 四档示范章冻结表

这些是R1制作候选，不等于已经人工审校或上线。`NEW_SOURCE_REQUIRED` 表示必须生成新内容、来源记录和真实审校；旧章节只保留来源引用。

| 学段 | 年级 | 章节 | 来源状态 | 必须展示 |
|---|---:|---|---|---|
| PRIMARY_LOWER | 1–3 | `new-primary-lower-ai-observation-v1/ch01` 机器会看猫吗？从例子里学 | NEW_SOURCE_REQUIRED | 用生活观察和一次只做一个判断的方式区分“听指令”与“从例子学习” |
| PRIMARY_UPPER | 4–6 | `new-primary-upper-sorting-v1/ch01` 排队有妙招：比较与排序 | NEW_SOURCE_REQUIRED | 用相邻比较卡片理解排序步骤，掌握可预测、可回退的算法过程 |
| JUNIOR | 7–9 | `python-first-steps/ch05` 小项目：猜数字游戏 | EXISTING_REUSED_PENDING_REVIEW | 综合变量、条件、循环，完成可运行项目并依据真实错误调试 |
| SENIOR | 10–12 | `algorithm-everyday/ch03` 查找的智慧：二分的力量 | EXISTING_REUSED_PENDING_REVIEW | 识别二分前提、维护搜索区间并解释对数级效率；配套排序/查找动画与实验 |

## 动画绑定

| 模板 | 学段 | 章节 | 任务 |
|---|---|---|---|
| ADJACENT_SORT | PRIMARY_UPPER | `new-primary-upper-sorting-v1/ch01` | T21 |
| BINARY_SEARCH | SENIOR | `algorithm-everyday/ch03` | T21 |

## 审校门禁

G_HUMAN_CONTENT_REVIEW remains BLOCKED until named human reviewers sign actual records.

- 四项 `review_status` 在真实人员签字前均视为未通过。
- 动态题稿、模板题和人工题库必须在UI与数据中分源标识。
- `PRIMARY_LOWER` 的一、二年级样例必须实际检查阅读负担、图片许可、操作方式和安全表达。
