# 复用结果验收（按 prompts/04_REVIEW_AND_ACCEPT.md）

核对范围：选型任务书（`selected/` 三份）、实际 diff、`AGENTS.md`、手册第 10/11 章。
原源码版本 `6456871e2ee089ed0af6e8c70da174e2ed95977a`。
**不是**按正常态截图验收；下列每项都附实测命令与真实输出。

## 实际执行的命令与结果

| 命令 | 真实结果 |
|---|---|
| `npm run typecheck --prefix frontend` | EXIT 0 |
| `npm test --prefix frontend` | **134 passed / 19 files** |
| `npm run build --prefix frontend` | EXIT 0（947 kB chunk 警告，未消除也未掩盖） |
| `npx playwright test --config playwright.ui.config.ts` | **15 passed** |
| `npm test` 等见 `batch0..3-*.log` | 逐条留档 |

## 选择范围核对

三份选型书全部落地：C03/C04/C05、P03、B02+M01。
**未选模块确认未引入**（`grep` 非测试源码）：

| 排除项 | 命中 |
|---|---|
| Live2D / kurisu / PIXI / GSAP / Tailwind / clsx / lucide-react | 0（仅一处注释说明「不用 GSAP」） |
| `frontend/package.json` 依赖变化 | **0**（未新增任何依赖） |
| B01 完整背景 / C02 / C06 / C10 / M07 / M08 | 未引入 |

## 逐项验收

| 轴 | 证据 | 结果 |
|---|---|---|
| 状态/权限 | `AppLayout.tsx:160` 非管理员渲染「仅管理员可访问」；e2e「student cannot mount admin functionality」 | 通过 |
| 空/错/忙态 | `ConversationContent` 8 处 `role=alert/status`；空态文案不填假数据 | 通过 |
| 失败恢复 | R14 回归测试：turn 被拒后草稿保留且仍可发送 | 通过 |
| 防重复 | R30：会话操作与侧栏历史均有 busy 锁，双击只发一次 | 通过 |
| 中文 IME | 输入框与 onboarding 兴趣字段均有 `isComposing \|\| keyCode===229` | 通过 |
| 键盘焦点 | Companion Escape 关闭并归还焦点（e2e 断言）；浮层 `aria-modal=false` | 通过 |
| 移动断点 | e2e 覆盖 390/820/1280/1920，断言 `scrollWidth <= innerWidth` | 通过 |
| Portal 主题 | 本项目未使用 Portal；B02 挂载点变量作用域已用 computed style 核对 | 不适用 |
| 长 Markdown | `MessageView` 用 react-markdown，`skipHtml`，无 raw HTML 执行 | 通过 |
| reduced-motion | e2e 仿真：canvas 消失、光斑保持 opacity 1、`data-paused=true` | 通过 |
| 清理 | B02 取消 rAF + 移除 4 类监听；StrictMode 重复挂载不累积循环（单测） | 通过 |
| 接口副作用 | B02/particles 内 `fetch\|EventSource\|XHR` 命中 **0** | 通过 |
| 精灵素材参数 | 8 列 / 192×208 / 220ms，与手册一致；6 只宠物 gridRows 逐只校验 | 通过 |

## 手册点名的「重点检查」逐条

| 项 | 判定 |
|---|---|
| SurfaceCard description-only（R05） | **不适用** —— 未移植 SurfaceCard（src 非测试命中 0） |
| ConfirmDialog 重复打开（R06–R08） | **不适用** —— 未移植 ConfirmDialog（命中 0） |
| 候选失败是否仍可重试（R17/R18） | **不适用** —— C09/QuickActions 未选（选型书明确排除） |
| CountUp 目标值（R19） | **不适用** —— 未实现 CountUp（命中 0） |
| 雷达图（R20） | **不适用** —— 无雷达图（命中 0） |
| radio 键盘（R29） | **以原生控件满足** —— `QuizCard.tsx:103` 单选共用 `name`、无 `tabindex` 覆盖，浏览器提供方向键与单 Tab 停靠；新增回归测试锁定。Companion 用原生 `<select>`，同样满足 |
| 精灵素材参数 | **通过** —— 见上表 |
| Live2D ready 失败/暂停（R24–R26） | **不适用** —— 未选 P04 |
| 侧栏触摸操作入口（R09） | **通过** —— 两处操作并非 hover-only（常显），并补 `@media (pointer: coarse)` 放大到 32px 触摸目标 |

## 结论

### 阻塞问题
无。

### 重要问题
无未修项。本轮修复的 5 项（R09/R12/R21/R28/R30）与锁定的 2 项（R13/R14）
均已在 `batch3-r-audit.md` 列明并附测试。

### 可选优化（未做，留待决定）
1. `frontend` 主 chunk 947 kB，构建有体积警告。B02 未新增依赖故未加剧，
   但未做 code-splitting —— 手册 §10.8 禁止为「迁移看起来成功」而掩盖它。
2. 手册 §10.5 建议 Companion 的 `positionStore` 由宿主注入；本项目沿用
   自己的 `k12:companion:${userId}:…` 命名空间，属有意保留的差异。
3. `frontend/dist/` 与 `public/k12-learning-background.png` 疑似陈旧产物，未清理。

### 未执行（不写成通过）
- `animation.spec.ts`、`practice.spec.ts` 等既有 e2e 需要 `E2E_T21_*` 等凭据与
  真实后端，本环境未配置，**未运行**。仅 `ui-reuse.spec.ts` 15 条为实测通过。
- 未运行原 CareerMate 仓库的任何构建/测试（手册本身即声明未运行）。
