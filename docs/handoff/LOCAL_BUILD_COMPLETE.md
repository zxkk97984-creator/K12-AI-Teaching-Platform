# Local build completion status

## Status

**本文件不是用户最终验收或正式发布证明。当前本地合成可执行范围已完成，仍有外部阻塞。**

可执行的本地范围已经有真实证据：T29 bootstrap/Compose、T13 backend 371 passed + 真实 Knodo 浏览器竖切、T30 backend 333 passed、
frontend 101 passed、既有 browser 21 passed + 1 explicit skip，以及本轮动画 fixture browser
1 passed、T24 Docker 5 passed、T31 offline + live eval 16 cases。Git 未添加远端或 push；本轮变更已记录
在本地提交 `0a7c7ab`。

## Verification record

| 命令/证据 | 退出码 | 实际结果 |
| --- | ---: | --- |
| `python3 .rebuild-kit/tools/validate_kit.py` | 0 | 38 个任务、DAG、契约和语法校验通过 |
| `python3 contracts/test_contracts.py -v` | 0 | 38 个契约测试通过 |
| `PYTHONPATH=. backend/.venv/bin/pytest backend/tests -q`（T30 带 runner 基线） | 0 | 333 passed |
| 同一命令（本轮未配置 runner） | 0 | 332 passed，1 个 runner bridge 预期 skip |
| `npm test --prefix frontend` / `npm run typecheck --prefix frontend` / `npm run build --prefix frontend` | 0 | 101 passed；类型检查和生产构建通过 |
| `playwright test src/e2e/animation.spec.ts --config frontend/playwright.config.ts --reporter=line` | 0 | 1 passed；真实 FastAPI、PostgreSQL、Chrome，截图已保存 |
| `./scripts/runner-live-test.sh` | 0 | 真实 Docker runner 5 passed |
| `python3 evals/run_offline.py --output docs/acceptance/T31-offline-report.json` | 0 | 16 个合成评测样例 |
| `python evals/run_live.py --live --prompt-pat` | 0 | 16/16 已记录；13 OK、2 Schema失败、1超时；无重试 |
| T13 live Chrome → API → Knodo → PostgreSQL → Chrome | 0 | A 两轮续聊、B 独立会话；3 个真实 run 成功；预算 16/20 |
| `./scripts/check.sh` | 1 | 只读 CareerMate source-audit 检测外部 HEAD/tree/status/untracked 漂移后 fail-closed；未修改 K12 工作树 |
| source-audit 之后的 K12 checks | 0 | public evidence、plan、contracts、OpenAPI、ruff 和生成类型全部通过 |

验收由本单 Agent 完成第一遍实现和同一 Agent 的第二遍针对性复核；第二遍不是独立 Agent
审核。用户最终验收尚待进行。

## Why this is not marked complete

- T30 动画控制器已在明确的合成 T06 fixture 上执行并通过，但这不是正式 senior 内容人审；
  正式内容仍需真实审校者签署和发布证据。
- G_API_CONTRACT 和 G_LIVE_BUDGET PASS；T31 16-case live 已执行，可信 usage/cost 与人工教学质量仍未完成。
- G_AGENT_ISOLATION、G_HUMAN_CONTENT_REVIEW 仍 BLOCKED；当前范围明确为成人参赛者 + 合成数据，
  因此 G_K12_TERMS 不阻塞本原型；任何真实未成年人发布必须重新取得条款证据。
- 完整 `scripts/check.sh` 还保留 CareerMate 只读源审计的外部漂移失败；这不是 K12 源码修复项，
  不能删除记录或用 `|| true` 绕过。

因此当前可写“本地范围建设完成，等待外部配置、人审和用户最终验收”；这句话不解除
G_* 门禁，也不把合成 fixture 通过等同教学质量或正式发布。
