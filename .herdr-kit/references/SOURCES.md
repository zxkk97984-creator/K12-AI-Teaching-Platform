# 依据、版本与边界

## 用户资料

K12_Knodo_从零重建执行包.zip：原34项核心＋4可选TASKS、卡片、9份plans；references内为只读副本，不可覆盖用户进度。
K12_T06-T33_后续任务Prompt完整包.zip：28项后续核心＋4可选，COMMON_RULES和任务详细步骤/反例。逐任务brief的实施步骤与原反例来自这些文件，监督重点和角色职责为本次新增。
K12_任务与阶段审核_通用Prompt模板.zip：既有独立审核/修复/继续规则，本次只把进度写入转为监督者、批次内派发转为监督者，不降低验收标准。
T05完成信息：用户粘贴的执行报告，不是本次重新读取本机代码或执行测试。
旧PROJECT_HANDOFF.md：历史代码审计，区分实现/验证/服务类型；不能将旧JWT、旧数据库、旧测试数量或旧架构复写进T05新工程。

## Herdr官方文档（2026-09-18在线核查）

H1 https://herdr.dev/docs/agent-automation/ ：一个Agent可使用终端/Agent控制面；prompt/wait与具体业务任务并无严格一一关联。
H2 https://herdr.dev/docs/cli-reference/ ：只使用已列命令形态，目标来自真实发现，等待须设边界。现场版本与help优先。
H3 https://herdr.dev/docs/agent-skill/ ：自带Skill、HERDR_ENV前提。
H4 https://herdr.dev/docs/agents/ ：状态检测可能有未知/误识别，不把状态颜色作为质量结论。

本包未下载/运行Herdr，也未对用户现有CLI钩子作变更。没有假装已经建立两Agent的真实控制通道。只提供待本机验证的操作步骤和角色配置。

## 本次新增的设计

角色单写者、dispatch/ACK/submission/review/decision/apply、阶段批次、最多两轮定向修复、协作测试锁和源码哈希清单是本次工作流设计，不是Herdr原生保证。辅助脚本只读/计算材料，不是自治任务执行器，不自动调用API或改progress。
