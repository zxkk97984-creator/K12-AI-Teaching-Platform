# T23 代码任务迁移记录

## 输入基线

只读来源是 `/home/zxk/Projects/K12-Learning-platform`，固定 commit
`696364ff54c99f711e1cddd7364c9ac4d5282943`。本记录没有修改、启动、迁移或
测试旧仓库。旧任务 JSON 的完整文件 hash、参考实现 hash 和旧测试组 hash
已登记在每个 `curriculum/code-tasks/*-r1.json` 的 `source` 字段。

旧目录中的三题是：

| 新任务 | 旧任务 | 章节绑定 | 旧字段核对 |
| --- | --- | --- | --- |
| `temperature-converter@r1` | `temperature-converter.json` | `python-first-steps/ch05-r1`，JUNIOR；变量/条件/循环/随机数 | starter、reference_solution、3 个 test_groups；无 rubric 字段 |
| `list-summary@r1` | `list-summary.json` | `python-first-steps/ch05-r1`，JUNIOR；变量/条件/循环 | starter、reference_solution、3 个 test_groups；无 rubric 字段 |
| `binary-search@r1` | `binary-search.json` | `algorithm-everyday/ch03-r1`，SENIOR；二分查找/复杂度/排序 | starter、reference_solution、3 个 test_groups；无 rubric 字段 |

旧 JSON 的参考实现没有复制进学生任务定义。旧 `scoring.py` 中的 F60/R10
确定性维度被转成 `k12.codelab.rubric.v1`；旧 A/Q 模型评价只作为未来
辅导参考，不能改变当前确定性正确性。

## 新契约与边界

- `runner/contracts/code-task.schema.json` 固定 `function-json.v1`：输入是受限
  JSON 对象，输出是 JSON 值；输入、输出大小和超时上限是任务元数据的一部分。
- `runner/contracts/grading-result.schema.json` 的可信分数范围是 F/R 合计 70，
  不生成没有确定性测试依据的 100 分制权威分数。
- `public_task_view()` 只返回 starter、公开样例、IO 合同、公开测试组摘要和
  章节绑定；没有 reference solution、pytest/test_groups 源码、隐藏输入或
  隐藏期望值。
- `backend/app/modules/codelab/trusted.py` 是当前可信侧 oracle 与隐藏用例清单。
  `hidden_cases_sha256` 用于防止任务 manifest 与可信侧漂移；T24 再定义隔离
  runner 如何接收不可信提交。
- 学生 stdout、`reported_passed`、伪造的 pytest 统计都不进入
  `grade_observations()` 的判定。结构化 `actual_output` 与可信 oracle 逐案比较。

## 迁移/版本规则

`codelab_task_revisions` 以 `(task_id, revision)` 唯一约束保存不可变任务版本。
重复导入相同 hash 返回 REUSE；同一 revision 内容变化抛出冲突，必须新建 revision。
任务当前保持 `DRAFT`/`UNREVIEWED`，不因技术校验自动获得人工审校或正式学生可见
状态。`is_test_fixture` 是独立字段；本批 legacy 任务为 `false`，测试可以创建
明确标记的 synthetic fixture，但两者不会在定义层混淆。

`scripts/bootstrap.sh` 在迁移完成后调用
`python -m app.modules.codelab.importer --catalog-root ../curriculum/code-tasks`。
调用是幂等的，避免“脚本存在但启动未导入”。

## 旧 pytest 路径的限制

旧任务把 Python 测试源码作为字符串并在同一进程/执行上下文中统计通过数。学生
代码可能影响导入、插件、收集和 stdout；只读挂载也不能证明隐藏测试不可读。因此
本轮不迁移 pytest 源码或旧宿主执行器，也不宣称已经解决反作弊问题。T24 负责
隔离执行、资源限制和 runner 重启边界；T25 负责真实运行结果与辅导结果的分离。
