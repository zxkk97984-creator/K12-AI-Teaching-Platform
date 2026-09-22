# 既有浏览器 e2e 实测盘点（2026-09-22）

首次给全套 live spec 配齐账号后实测。**这些是既有测试的状态，不是本次 UI 复用的产物** ——
本盘点只报告事实，不声称通过未通过的项。

## 条件

- 真实 FastAPI(18081) + 真实 PostgreSQL(k12r1_dev) + 真实 Chrome
- 账号：`demo_junior` / `demo_lower` / `demo_senior` / `demo_admin`
  （`./scripts/seed-demo-accounts.sh`；密码在 `~/.config/k12/runtime.env`）
- 运行：`/tmp/run-live.sh`，把上述账号映射到 spec 各自要求的 `E2E_*` 变量

## 结果

| spec | 结果 | 未通过原因 |
|---|---|---|
| `animation.spec.ts` | ✅ **1 passed** | — |
| `ui-reuse.spec.ts` | ✅ 15 passed | 自包含 fixture，不依赖此栈 |
| `content.spec.ts` | ❌ 4 failed | `learn`/`content` 路由与内容断言 |
| `conversation.spec.ts` | ❌ 1 failed | 1 passed；取消终态断言 |
| `learn.spec.ts` | ❌ 1 failed | `/learn` 现为重定向到 `/study` |
| `lesson.spec.ts` | ✅ 通过（修复登录断言后） | — |
| `growth.spec.ts` | ❌ 1 failed | 证据投影流程断言 |
| `practice.spec.ts` | ❌ 2 failed | 判分/owner 隔离断言 |
| `resources.spec.ts` | ❌ 1 failed | 需真实文件上传，见下 |
| `authoring.spec.ts` | ❌ 1 failed | 需 `E2E_T22_REVISION` 指向已发布修订 |
| `codelab.spec.ts` | ❌ 1 failed | 需要 runner 服务在 18090 |
| `t13-live.spec.ts` | ⏭ 跳过 | 需 `T13_LIVE=1` + 真实 Knodo PAT |

## 本次已修复的过时断言（11 处，跨 10 个 spec）

全部同一根因：**登录后的落地页变了，测试仍断言旧页面。**

应用实际行为（`LoginPage.tsx:17-19`）：
- admin → `/admin/resources`
- 学生且档案完整 → `/conversations`
- 学生未完成引导 → `/onboarding`

测试原先只接受 `/settings|onboarding`。已改为接受四种真实落地页。

## 未修复的失败 —— 需要你决定

这些不是同一个根因，每一条都要单独判断是「测试过时」还是「真缺陷」：

| # | 表现 | 需要判断 |
|---|---|---|
| 1 | `content.spec.ts` 4 条：`learn` 断言、reader 链路、390/820/1280 溢出、503 状态 | `/learn` 已是重定向；其余需逐条看是路由变了还是真回归 |
| 2 | `learn.spec.ts`：`/learn` 上找不到 `next-page` | 同上，`/learn` → `/study` |
| 3 | `practice.spec.ts` 2 条：判分与 owner 隔离 | 需确认是 fixture 依赖还是真缺陷 |
| 4 | `growth.spec.ts`：证据投影链路 | 同上 |
| 5 | `resources.spec.ts`：真实 docx/pptx/视频上传 + 撤回 | 需要 `E2E_T20_*` 有上传权限；可能是权限而非断言 |
| 6 | `authoring.spec.ts`：`E2E_T22_REVISION must point at a published revision` | **环境前置**：需要一个已发布修订的 ID，不是断言问题 |
| 7 | `codelab.spec.ts`：真实 runner | **环境前置**：runner 服务未起（`--with-runner`） |

第 6、7 项是**环境缺前置**，不是测试错误；第 1–5 项需要逐条判断。

## 我没有做的事

- 没有为了让测试变绿而删除、跳过或放宽任何断言（手册 §10.8 禁止）
- 没有修改应用逻辑去迎合测试
- 没有声称上表任何 ❌ 项通过
