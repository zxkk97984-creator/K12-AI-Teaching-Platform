# 霜铃 K12 本地合成原型

这是一个 FastAPI + React/Vite + PostgreSQL 的本地教学流程原型，范围截至
`synthetic_competition_prototype_until_authorized`。它不是已接入 Knodo 的正式 K12 产品；
fixture、真实 Docker runner、正式人审内容和真实平台证据始终分开记录。

## 快速启动

配置只从进程环境读取，不自动读取或覆盖根目录 `.env`。准备本地开发/测试数据库密码和至少
32 字符的 `APP_SESSION_SECRET` 后，按 [T29 部署说明](docs/operations/DEPLOYMENT_T29.md)
注入 `DATABASE_URL`、`TEST_DATABASE_URL` 等配置，然后执行：

```bash
./scripts/doctor.sh
./scripts/bootstrap.sh
```

需要同时构建并启动本项目 API、worker、web、PostgreSQL 时使用：

```bash
BOOTSTRAP_DEPLOY=1 ./scripts/bootstrap.sh
```

服务默认位于 `127.0.0.1:18081`（FastAPI）和 `127.0.0.1:15173`（web）；开发库和测试库
分别使用 `55433` 和 `55434`。重复运行 bootstrap 是幂等的。默认 Compose 不启动 CodeLab
runner；runner 未配置时页面如实显示 `UNAVAILABLE`，不会回退到宿主机执行。

可选合成演示账号通过 `T05_DEMO_STUDENT_A_USERNAME/PASSWORD`、
`T05_DEMO_STUDENT_B_USERNAME/PASSWORD`、`T05_DEMO_ADMIN_USERNAME/PASSWORD` 注入；密码不写入
仓库。更多身份、资源、CodeLab、动画和恢复步骤见 [最终验收说明](docs/handoff/FINAL_ACCEPTANCE.md)。

## 本地验证

```bash
python3 .rebuild-kit/tools/validate_kit.py
python3 contracts/test_contracts.py -v
PYTHONPATH=. backend/.venv/bin/pytest backend/tests -q
npm test --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
```

真实 Docker runner 回归使用 `./scripts/runner-live-test.sh`；完整交接中的退出码、预期跳过、
浏览器证据和外部阻塞见 [本地建设完成记录](docs/handoff/LOCAL_BUILD_COMPLETE.md)。

## 边界

不要在本项目中放置 PAT、Cookie、真实学生资料、数据库 dump、运行时上传文件或浏览器状态。
真实 Knodo、付费调用、K12/未成年人条款、平台隔离和四档正式内容人审均需要独立授权与证据；
当前状态见 [RESUME](docs/handoff/RESUME.md) 和 [Knodo 清单](docs/handoff/KNODO_FINALIZATION_CHECKLIST.md)。
