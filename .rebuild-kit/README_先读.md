# 霜铃 K12 × Knodo 从零重建执行包

版本2.0｜2026-09-18｜目标：`/home/zxk/Projects/K12`

本包是**研究结论、可执行任务计划、平台配置素材与离线契约样例**，不是已经开发好的K12应用，也不是已经上线的Knodo Bot。新版范围是独立重建，上一轮“旧系统添加可选聊天分支”的范围不再执行。

## 一、怎样放到你的电脑

将ZIP解压到新项目里的`.rebuild-kit/`。ZIP根目录就是README、plans、tasks等，不多套一层目录。示意命令：

```bash
mkdir -p /home/zxk/Projects/K12/.rebuild-kit
# 将下一行ZIP路径替换为实际下载位置；-n防止覆盖已存在同名文件。
unzip -n '/你的下载路径/K12_Knodo_从零重建执行包.zip' \
  -d /home/zxk/Projects/K12/.rebuild-kit
cd /home/zxk/Projects/K12
python3 .rebuild-kit/tools/validate_kit.py
```

若目标已有代码，这不授权清空或覆盖。先让Agent检查旧内容与realpath。不要直接覆盖项目AGENTS.md；本包AGENTS.template由Agent阅读并按已有规则有选择采用。

## 二、直接发哪份Prompt

第一轮：`prompts/00_MASTER_PROMPT.txt`。它要求先核对两个旧项目和赛题，再定界和创建新骨架；不是立刻批量生成整个应用。
继续下一轮：`prompts/01_CONTINUE_PROMPT.txt`。只读验收：`prompts/02_REVIEW_PROMPT.txt`。
平台配置：`prompts/03_PLATFORM_SETUP_PROMPT.txt`。补齐官方API证据：`prompts/04_API_EVIDENCE_PROMPT.txt`。

你使用的编码模型只负责执行任务。它的模型昵称不自动成为Knodo可用模型ID；平台模型在真实账号与运行引擎内选择。

## 三、包内结构

| 路径 | 用途 |
|---|---|
| `plans/00–08` | 总计划、产品、架构、平台操作、契约、迁移、测试、执行规则与来源 |
| `tasks/T00–T33` | 34个核心任务，每项前置/步骤/允许文件/验收/禁止/交付 |
| `tasks/O01–O04` | 可选绘本、MCP、全量课程、原生流式优化 |
| `TASKS.json` / `progress.json` | 依赖图、门禁与跨轮真实进度；初始全部NOT_STARTED |
| `platform/prompts/` | Tutor与Designer两类Bot系统提示词 |
| `platform/skills/` / `platform/*-skill.zip` | 三个Skill源文件与上传包；不是整Bot自动导入包 |
| `contracts/` / `examples/` | 本地业务JSON Schema与明确合成样例；官方wire待取证 |
| `tools/` | 任务提示打印器、结构检查与离线契约示例校验器 |
| `references/` | 原赛题、旧交接、旧手册、来源索引；旧范围不能覆盖新请求 |
| `evidence/` | **本执行包自身**的检查记录，不是项目验收 |

## 四、每轮只加载必要上下文

```bash
python3 .rebuild-kit/tools/task_prompt.py next
python3 .rebuild-kit/tools/task_prompt.py show T14
python3 .rebuild-kit/tools/task_prompt.py status
```

工具只打印，不执行项目、不调用平台、不自动标DONE/PASS。若当前任务受真实API/预算门禁阻塞，选择可离线推进的下一任务。完成任务后Agent自己根据实际证据更新progress。

`G_API_CONTRACT`等门禁不是“全部都先解决才可以写代码”。没有平台凭据时骨架、课程、schema、fixture、状态、判分、UI与安全测试可继续；但不能因此宣称真实Knodo接通。真实学生适用与人工内容审校由对应人员提供依据。

## 五、可运行的离线检查

只查结构使用标准库即可。校验JSON Schema需要jsonschema，建议用专用虚拟环境，不改旧项目环境：

```bash
python3 -m venv .rebuild-kit/.validation-venv
.rebuild-kit/.validation-venv/bin/python -m pip install \
  -r .rebuild-kit/requirements-validation.txt
.rebuild-kit/.validation-venv/bin/python -m unittest discover \
  -s .rebuild-kit/tools -p 'test_*.py' -v
```

这段安装在你的机器执行，可能联网获取公开依赖，不涉及模型计费；无需运行它也可先读计划。校验器只验证结构和部分交叉约束，不是生产鉴权、内容正确性或Knodo兼容证明。新应用实现后必须补数据库权限/版本/原子性/HTML安全/真实来源语义等测试。

## 六、不要误用

不要把示例synthetic ID作为实际课程/学生ID，不要把wire模板直接curl，不要把Skill ZIP说成线上已创建助手。不要上传真实学生数据/密钥/旧仓库.env到平台，不要默认允许付费。只读GitHub核对不等于本机代码已同步，也不等于旧系统当前库的测试结果。

本包专门保留真实API、工具隔离、未成年人适用和人工审校门禁。参赛报告应清楚区分“代码实现”“fixture通过”“真实平台通过”“人工审校”和“真实学生开放”。
