# Herdr现场接线：先识别现有窗格，再协作

## 1. 本次核查结论和限制

截至2026-09-18，官方文档支持从一个Agent通过Herdr的agent/pane CLI查看另一Agent、提交Prompt、等待状态并读取输出。[H1][H2] 但在线文档不证明你本机安装的是同版本。本包不调用你电脑的Herdr，没有验证你目前两个模型的状态检测。

官方自带Skill可通过 `herdr --skill` 获取；使用控制命令前应确认实际环境有 `HERDR_ENV=1`。[H3] 不要手动export这个值来假装处于Herdr。

## 2. 用户先做

在Herdr里复用两个现有窗格，分别进入 `/home/zxk/Projects/K12`，运行你已配置可用的编码CLI。A是监督者，B是执行者；模型可相同，CLI名称以现场为准。不要未经许可换供应商、开新账户、启用yolo或关闭CLI的权限确认。

你原先已有执行者窗格时只登记它，不再agent start一个相同执行者。需要新增窗格仅在确认缺失且得到当前操作授权时创建；本次推荐由用户手动打开两个窗格，减少版本差异。

## 3. A在Herdr内部执行只读能力探测

```bash
cd /home/zxk/Projects/K12
test "${HERDR_ENV:-}" = 1
herdr --version
herdr --help
herdr --skill
herdr agent --help
herdr agent list
herdr pane list
```

如果子命令不支持，记录真实帮助输出，不照网上旧版本猜语法，不升级/重启服务器。只读输出中如有私人路径或token须脱敏保存；不要把全部环境变量打印出来。先核对两个pane的实际当前工作目录和运行进程，避免向Shell或另一个项目发送Prompt。

当前官方文档的示例接口包括agent get/prompt/read/wait；target使用本机返回的真实pane ID或唯一Agent别名。不要硬编码1-1、w1:p2。若B的CLI未被正确识别，优先读取pane可见状态并确认身份；不假报done。必要时停用自动投递，用户在B粘贴同一派工通知，文件协议照常有效。

## 4. 名称、模型与等待

建议角色标签 `k12-supervisor` / `k12-executor`，但不是强制重命名现有“claude执行者”等窗格。机器可调用的Agent别名与中文pane标题不是同一概念。A应记录真实可用target，重启/替换进程后重新发现，不能沿用已指向他人进程的旧别名。[H1][H2]

DeepSeek Harness/自定义CLI不在本机支持列表时，普通终端承载不等于Agent状态/会话恢复已经支持。只依据真实帮助、官方Skill和现场通信试验确认，不臆造herdr agent start --kind deepseek。

## 5. 消息只送指针，不送全量代码与密钥

先写完整派工JSON和Markdown，验证hash，再向B发送一条短通知。当前官方CLI形态参考如下，使用前核对本机help；TARGET须替换为现场登记值：

```bash
herdr agent prompt TARGET '派工已写入.herdr-control/dispatches/<真实dispatch_id>.json；请核对当前控制记录与本dispatch_id，只执行这一单。'
herdr agent wait TARGET --until idle --until done --until blocked --timeout 120000
herdr agent read TARGET --source visible --lines 60
```

这些命令不是本包已经执行过的结果。不要向还在工作的B重复发送完整任务，不对权限确认框自动按Enter。通知没有ACK时先读回执与状态，不能重新生成新dispatch或反复重投。

官方说明 `agent prompt --wait` 不逐任务关联：B已经在工作时，旧回合结束可能满足等待；wait状态还可能是blocked或unknown。[H1] 因此必须同时核对dispatch_id、attempt、源码hash、回执和真实验收。窗口的done不能标任务DONE。

## 6. 完成回调避免自唤醒循环

A派发后可在同一个前台工具会话有限时等待，间隔读取提交文件；等待耗尽后落盘并结束本轮，不承诺自动后台监督。B提交后可向A发一条“dispatch已提交”通知，**仅在A当前可接收新输入且不存在该dispatch审核回执时**发送一次；A仍在处理/等待时只写回执，不再打断A。

通信无法可靠识别忙闲时，关闭自动回调，由A短时等待或用户发送恢复Prompt。不得安装未验证的无限轮询、自续费或自动批准钩子。

## 7. 合作启动握手

B先读Executor Prompt，只写`.herdr-control/executor/READY-<time>.json`并返回就绪；A随后读Supervisor Prompt并写自己的就绪记录，完成双向一次无业务副作用的echo（或文件ACK）验证，再派T06。若T06已经在旧会话执行，先等其安全交接/暂停并接管，不重复启动。

默认只控制这两个确认过的窗格；不创建第三个编码Agent、不关闭用户窗格、不全局停止Herdr。特殊OS钩子错误只作为通信阻塞记录；不因为Linux遇到Windows脚本就擅自重写全局CLI设置。

## 8. 资料

[H1] https://herdr.dev/docs/agent-automation/
[H2] https://herdr.dev/docs/cli-reference/
[H3] https://herdr.dev/docs/agent-skill/
[H4] https://herdr.dev/docs/agents/

仅描述这些官方资料支持的能力；本地版本与本地实测是最终操作依据。不使用搜索到的同名fork命令混搭。
