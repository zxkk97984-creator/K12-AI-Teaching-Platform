# K12 后续任务 Prompt 完整包

**接续T05，不重新规划项目。** 包含T06—T33共28项核心任务和O01—O04共4项可选增强，每项一份可直接复制的完整TXT。原任务编号、依赖、验收和门禁保持，不替换原执行包。

## 1. 放在哪里

将ZIP内容解压到：

```text
/home/zxk/Projects/K12/.continuation-prompts/
```

ZIP没有额外根目录。解压后应存在`.continuation-prompts/START_HERE.txt`和`prompts/T06.txt`。不要解压覆盖`.rebuild-kit/`，尤其不能覆盖已更新的progress.json。

```bash
mkdir -p /home/zxk/Projects/K12/.continuation-prompts
unzip -n '/你的下载路径/K12_T06-T33_后续任务Prompt完整包.zip' \
  -d /home/zxk/Projects/K12/.continuation-prompts
cd /home/zxk/Projects/K12
python3 .continuation-prompts/tools/validate_package.py
```

`-n`不覆盖已有同名文件；若验证发现旧版本混入或文件变化，先保留并核对，不清空项目或重写原校验清单。

## 2. 怎么发送

首次发送`START_HERE.txt`全文。它会让Agent读取当前实际进度并从T06开始；后续已推进则按现场继续，不重做T00—T05。

每次也可直接发送对应TXT，例如`prompts/T06.txt`。所有后续Prompt已经提供，不必再次来索取下一条。每轮一个任务，每任务实测与检查点；不要把合订本一次性喂给模型或让它跳过验收连写全部功能。

## 3. 查看下一可执行任务

```bash
python3 .continuation-prompts/tools/prompt_helper.py next
python3 .continuation-prompts/tools/prompt_helper.py show T06
python3 .continuation-prompts/tools/prompt_helper.py status
```

工具只打印，不执行开发、不改progress、不联网、不调用数据库/Knodo。`next`读取原`.rebuild-kit/TASKS.json`与`progress.json`并核对是否与本包任务语义一致，选有证据且依赖/门禁满足的一项。它不自动重试自身仍BLOCKED的任务；收到新证据后由Agent核对再恢复该项。

`show`只是查看全文，不证明可执行；原卡依赖和门禁仍要核对。可选O任务只可显式`show O01`等，并由用户明确选做，不进入默认next。

## 4. 当前状态怎样使用

`CURRENT_CHECKPOINT.md`来自用户T05摘要，是历史参考，不是独立代码审查，也不是新的progress。沿用sl_session、sl_csrf、Argon2id、nullable grade、base_revision和真实OpenAPI类型生成；不重新做登录、不擅自更改开发/测试端口、根.env和Git状态。

五个真实性门禁仍按实际证据逐项管理。新Prompt既不批准付费额度，也不签署内容审核，更不自动允许真实未成年人数据或公网注册。

## 5. 目录

```text
START_HERE.txt                    首次/恢复续作总Prompt
COMMON_RULES.md                   每项共用约束
CURRENT_CHECKPOINT.md             用户报告的T05状态，只作参考
TASK_OVERVIEW.md                  原任务依赖/门禁一览
PROMPT_INDEX.json                 本包Prompt映射，不是项目任务进度
全部任务Prompt_合订本.md          阅读版，不建议整份交给模型
prompts/T06.txt ... T33.txt        28项核心任务
optional/O01.txt ... O04.txt       4项可选增强
helpers/                          继续一项、只读验收、单项修复、恢复、门禁证据
references/                       原任务表/原卡/原QA逐字参考
tools/prompt_helper.py            只读选择/打印
tools/validate_package.py         离线包一致性验证
tests/                           仅辅助工具测试
```

## 6. 哪些不是交付内容

没有替换任何项目源码、TASKS.json或progress.json；没有实际T05本地复测；没有新Bot部署、真实Knodo调用或新教学模型验收。本包的检查结果只验证Prompt与原任务表对齐、文件完整和辅助脚本行为，不证明新应用任何功能完成。

T09资产生成、T27诚实语音边界、T32待测标记报告按各自原卡验收，不能扩大为真实平台已上线。T11/T13/T31/T33所需证据仍保留；T30离线去重不证明上游实际无收费。

所有“本次续作补充”是对已有任务的执行拆解和反例，不是新赛事规则。若与本地合法更新的ADR/契约冲突，先记录差异并对齐，不能静默生成第二套协议。
