# 保留 / 复用 / 适配 / 新增 / 不迁移 映射表

依据：`prompts/01_IMPLEMENT_SELECTED.md` 第 4 步要求「输出映射表，列出真实文件与原因」。
每一行都来自本项目实际代码，未预填臆测路径。

| 目标文件/区块 | 当前业务 | 参考模块 | 决策 | 依据 |
|---|---|---|---|---|
| `app/layout/design-system.css` | 111 个 `--sl-*` token、app shell、侧栏、顶栏 | F01/F02 | **复用** | 已落地；token 与手册 §2.4 语义一致，类名走本项目自有前缀（手册 `examples/README.md` 要求先建映射） |
| `app/layout/AppLayout.tsx` | 导航 + 历史（搜索/归档/改名）+ 权限守卫 | L02/L03 | **复用** | 保留本项目权限与路由；R30 加 busy 锁，R09 加粗指针触摸目标 |
| `features/conversation/ConversationContent.tsx` | 线程 + 输入框 | **C03/C04**（显式选中） | **适配** | IME 门控保留；R12 `maxLength` 提升为 prop |
| `features/conversation/MessageView.tsx` | Markdown 渲染 | **C05** | **复用** | react-markdown + `skipHtml`，无 raw HTML 执行 |
| `features/conversation/controller.ts` | 外部 store 控制器 | C03/C04 适配层 | **适配** | R14 行为已正确（失败保留草稿），补测试锁定 |
| `features/companion/**` | 精灵桌宠、拖拽、浮层 | **P03**（显式选中） | **复用** | 常量与手册一致（8 列/192×208/220ms）；不依赖 GSAP/PIXI |
| `features/companion/lib/geometry.ts` | 停靠/浮层几何 | P01/P03 | **适配** | R21 补 `Number.isFinite` 兜底 |
| `features/companion/components/Companion.tsx` | 宠物选择 | P03 | **复用** | R29 以原生 `<select>` 满足，勿回退成 radio |
| `public/k12-learning-background.*` | 本项目自有静态底图 | — | **保留** | 非手册素材；欢迎态让位给 B02 避免双层叠加 |
| `features/background/**` | 不存在 | **B02**（显式选中） | **新增** | CSS 关键帧 + Canvas 2D，无 GSAP；只挂登录/欢迎页 |
| `shared/motion/motion-safe.ts` | 两处各自手写 | **M01** | **新增** | 统一极性语言，B02 依赖它 |
| C02 / C06 / C10 / M07 / M08 | — | — | **不迁移** | 选型书 `chat-thread-composer.md` 明确排除，不得扩大范围 |
| B01 完整光幕背景 | — | — | **不迁移** | `calm-background.md` 说明「不需要选 B01」 |
| P04 Live2D | — | — | **不迁移** | 用户明确排除；手册列为高成本专项 |
| P05 外观选择器 | — | — | **不迁移** | 未选中；本项目桌面宠选择已由原生 select 满足 |
| `globals.css` 全量 reset | — | — | **不迁移** | 用户明确排除；本项目无 Tailwind，且手册 §2.9 警告全局禁选破坏复制 |
| 职业规划业务（岗位/三年规划/百宝箱候选） | — | — | **不迁移** | 保留 K12 业务，手册 §0.1 默认边界 |
| U01–U05 基础组件 | 本项目用原生元素 + `--sl-*` | — | **不迁移** | 手册 §10.6：目标已有基础设施时不新建第二套同名库 |
| `features/workbench/nav.ts`、`capabilities.ts` | 无引用且声明过时 | — | **新增（删除）** | 实测零引用，`nav.ts` 声称三页未建但三页已存在 |
