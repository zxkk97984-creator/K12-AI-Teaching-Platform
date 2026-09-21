# UI 复用验收证据

按需复用 CareerMate 前端 UI（参考固定 commit `6456871e`）的实测记录。
每条日志都由真实命令产出，未运行的测试不写入通过。

| 文件 | 内容 |
|---|---|
| `batch0-e2e.log` | e2e 修复后的完整运行（15 条） |
| `batch1-motion.log` | M01 动效门控：typecheck + vitest |
| `batch2-background.log` | B02 calm 背景：typecheck + vitest + build + e2e |
| `batch3-r-audit.log` | 手册第 10 章 R 清单修复后的全量验证 |
| `batch3-r-audit.md` | R01–R30 逐条判定（适用 / 不适用及理由） |

截图不入库（`.gitignore` 已排除 `*.png`），需要时用下列命令重新生成：

```bash
cd frontend
npx playwright test --config playwright.ui.config.ts --reporter=list
```

该 config 带 `webServer`，会自动起前端；所有 `/api/**` 由 `src/e2e/ui-reuse-fixtures.ts`
合成拦截，未匹配的路径按 fail-closed 返回 503，因此**不会**打到真实后端或 Knodo。

## 所选模块

来自 `CareerMate_UI_Reuse_Kit/selected/` 的三份选型书：

- `chat-thread-composer.md` → C03 / C04 / C05
- `sprite-only.md` → P03
- `calm-background.md` → B02 + M01

未选中的 C02/C06/C10/M07/M08、B01、Live2D(P04)、`globals.css` 全量均未引入。
