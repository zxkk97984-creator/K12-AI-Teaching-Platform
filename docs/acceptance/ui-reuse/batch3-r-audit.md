# Batch 3 — 手册第 10 章 R01–R30 核对记录

核对对象：当前 `frontend/src` 实际代码（不是手册示例）。凡「不适用」都写明理由，
不制造无意义改动。手册原文即声明这些是静态审查发现，「风险」不等于已复现。

## 本次修复

| R | 判定 | 证据 | 处理 |
|---|---|---|---|
| R12 | 部分适用 | `ConversationContent.tsx` 的 `maxLength={8000}` 是硬编码；本项目没有显示计数，故「计数与 maxLength 冲突」不成立 | 提升为 `maxLength` prop，默认 8000（§10.5 要求由宿主传入） |
| R13 | 适用（已补测试） | `useEffect([draft])` 已覆盖基本情形 | 新增「外部清空后重算高度」回归测试 |
| R14 | 已正确，补测试锁定 | `controller.ts` 仅在成功后清空草稿，失败分支保留 | 新增「失败保留草稿且仍可重发」回归测试 |
| R21 | 适用 | 读取路径有 `Number.isFinite`，但拖拽路径 `clampDock(d.origin.x + dx, …)` 未重新校验 | `clampDock` 内统一兜底到默认位；新增非有限值测试 |
| R28 | 适用 | composer 已有 IME 门控；`OnboardingPage.tsx` 的兴趣自由文本输入框无门控，中文选字回车会误提交 | 补 composition 门控 + 回归测试 |
| R30 | 适用 | `SessionActions` 与 `AppLayout` 历史操作均无防重；后者失败产生未处理 rejection | 两处加 busy 锁；AppLayout 改为可见错误提示 |
| R09 | 部分适用 | 两处历史操作**并非** hover-only（常显），但字号 10px 触摸目标过小 | 仅 `@media (pointer: coarse)` 放大到 32px 高 |

## 经核对不适用（不制造工作）

| R | 理由 |
|---|---|
| R01 / R03 / R04 | 本项目无 Tailwind、无 tailwind-merge、无 globals.css 叠加 |
| R02 | 全局 `user-select:none` 未引入；正文可选择复制 |
| R05–R08 | 未移植 SurfaceCard / ConfirmDialog |
| R15 | 无 GSAP，CSS transition 与 JS transform 无所有权冲突；B02 已按 §7.2 分层 |
| R16 | 无 GSAP tween；`useSpriteFrame` 清理 interval，`Companion` 移除全部监听 |
| R17 / R18 | 未移植 MemoryProposal / QuickActions（选型书明确排除） |
| R19 | 未实现 CountUp |
| R20 | 无雷达图 |
| R24–R26 | 未选 Live2D；工程明确排除 |
| R27 | 无结构化卡片挂载副作用；`MessageView` 仅渲染 Markdown，无挂载期请求 |
| R22 | 已由 B02 `particles.ts` 的 dt 归一化处理（见 batch2） |
| R23 | 已由 B02 处理：隐藏标签页取消 rAF，而非帧内提前返回 |

## R29 · 以原生控件规避（记录在案，勿回退）

`Companion.tsx` 的「学习伙伴」用原生 `<select>`，而非原项目的 radio 组。
原生 select 自带方向键、Home/End、type-ahead 与 `label` 关联命名，因此 R29
所述「radio 缺方向键与 roving tabindex」在此不成立。**不要改回 radio。**

## 已知差异（保留，非缺陷）

Companion 的持久化命名空间 `k12:companion:${userId}:…` 由本项目自有，未改为
手册 §10.5 建议的宿主注入 `positionStore`。这是本项目自己的存储约定，
与 `AGENTS.md` 的数据归属要求一致，记录为有意保留的差异。
