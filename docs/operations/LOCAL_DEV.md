# 本地运行与开发

当前项目的 GitHub 备份是私有仓库 `zxkk97984-creator/K12-AI-Teaching-Platform`，
与旧 `K12-Learning-platform`、`k12-multimodal-learning-assistant` 仓库独立。
`main` 保存阶段基线，`Xiaoxiao/next-phase` 为下一阶段工作分支。私有仓库只保存代码与必要资产，
本机运行配置、数据库和上传内容仍需单独保管；不能通过将仓库改为公开来分享比赛材料。

所有日常命令从项目根目录执行，入口是 `./k12`。运行配置保存在
`~/.config/k12/runtime.env`（或 `K12_RUNTIME_ENV_FILE` 指定的绝对路径），
模板是 `config/runtime.env.example`。`setup` 首次创建权限为 600 的配置，自动生成本机
数据库密码和会话密钥；如果已存在 K12 Compose 数据库容器，会读取其现有密码，避免断开旧数据。
已有配置从不覆盖，凭据不会输出到终端。

```bash
./k12 doctor          # 检查 Python、uv、Node、Docker 和配置
./k12 setup           # 安装依赖、构建前端、启动隔离数据库、迁移并导入课程
./k12 start --build   # 用当前源码构建 API、worker 和前端镜像，再启动
./k12 status
```

新配置默认 `GATEWAY_MODE=fixture`，用于离线比赛演示。真实 Knodo 接入时编辑本机配置中的
`GATEWAY_MODE`、PAT、Bot/Workspace ID 和预算，再执行 `./k12 restart`。示例数据会明确标为
合成内容。服务地址固定为前端 `http://127.0.0.1:15173`、API `http://127.0.0.1:18081`，
开发库端口 `55433`、隔离测试库端口 `55434`。

常用运行命令：

```bash
./k12 dev                    # Vite 与宿主机 API，前台运行；Ctrl-C 退出
./k12 dev --with-runner      # 增加本机回环 runner 和后台 worker
./k12 start                 # 复用已有镜像启动 Compose 应用
./k12 start --with-runner   # 后台启动当前源码、worker 与真实 Docker runner
./k12 restart --build       # 源码变化后重新构建并启动
./k12 restart --with-runner # 重启带 runner 的本机应用
./k12 stop                  # 只停本项目应用，保留数据库和数据
./k12 logs --tail 100 api worker
./k12 check                 # 隔离测试库中的完整本地检查
```

需要编程执行时，首次运行 `./k12 setup --with-runner` 构建受限 runner 镜像，然后使用
`./k12 start --with-runner`（或前台开发用 `./k12 dev --with-runner`）。脚本在 `~/.local/state/k12/runner-control-token` 生成权限为 600 的
控制 token，runner 只绑定回环地址；API 不获得 Docker socket。未启动 runner 时，CodeLab
会显示运行环境不可用，不能将其算成学生答错。隔离原理见[runner 说明](RUNNER_T24.md)。

`/code` 题库按当前登录账号的学段显示初中或高中 6 道题。目录元数据与题目通过现有导入器保存；改动题目后可从仓库根目录执行以下幂等导入，不会覆盖内容哈希已变化的旧版本：

```bash
cd backend
uv run --locked python -m app.modules.codelab.importer --catalog-root ../curriculum/code-tasks
```

题目要求先保存代码再运行公开示例或提交正式判题。公开示例只展示公开输入、预期与实际返回；可信判分使用服务器端 70 分用例。AI 建议只在有效正式判分后提供，并与判分结果分开显示。修改宿主 runner 的题目白名单后，执行 `./k12 restart --with-runner` 使 runner 加载当前代码；只有镜像内执行器代码变化时才需重建镜像。

运行数据默认保存在 `~/.local/share/k12/runtime-storage`，包括上传、编排产物与 Knodo
预算账本。脚本会在首次迁移时核对旧 Compose 数据卷；遇到两份不同数据会停止并报告，
不会覆盖。`stop`、`restart` 和 `check` 均不清空这些数据。切换为 `dev` 时，只停止带
`k12r1` Compose 项目标记的 API、worker、web 容器；未知端口占用会直接报错。

`check` 使用 fixture 网关和独立测试库，验证协议、OpenAPI 与前端类型同步、后端测试与
格式、前端测试与构建，以及 Knodo 资产。测试库连接必须通过隔离地址校验。
浏览器检查可运行 `npm run test:e2e:ui --prefix frontend`；演示账号由本机配置和
`scripts/seed-demo-accounts.sh` 管理。特殊工具如 `scripts/package-knodo.py`、
`scripts/build-runner.sh` 仍可直接运行。

## 演示账号与数据

账号名和密码放在本机运行配置中，文档不固定其当前数量、年级或密码。
`./k12 setup` 仅在配置了 `T05_DEMO_STUDENT_A_*`、`T05_DEMO_STUDENT_B_*` 和
`T05_DEMO_ADMIN_*` 时调用账号初始化；已存在账号及其档案不会被覆盖。
`scripts/seed-demo-accounts.sh` 按 `DEMO_STUDENT_LOWER_*`、`DEMO_STUDENT_JUNIOR_*`、
`DEMO_STUDENT_SENIOR_*`、`DEMO_ADMIN_*` 重置已有演示账号密码，不是清库脚本；
账号缺失会报错，应先完成初始化。无需重置密码时不运行该脚本。

学生默认进入 `/workbench`，管理员进入 `/admin/resources`，首次设置进入 `/onboarding`。
需要演示四学段时，可在专用演示账号的学习设置中切换具体年级。用户上传内容、学习记录及
发布资源归属均需保留，不能为准备演示直接删除账号或重置开发库。

## 浏览器检查与文件维护

合成浏览器回归入口和覆盖范围见[浏览器回归说明](../acceptance/ui-reuse/README.md)。
所有浏览器截图、JSON 报告写到 `frontend/test-results/`，不放进文档目录或提交 Git。
`frontend/dist/` 是可重建的运行产物，启动时由脚本检查；`frontend/public/` 中的品牌、绘本和
桌宠素材是实际运行资源，需要保留。所有 Alembic 迁移及课程版本用于升级和历史快照，不按日期删除。

当前 `/growth` 仅编辑个人记忆主文档；后台学习证据与候选记忆仍存在，不应因前端入口调整而删除
相关表、API 或测试。旧 UI 导出与一次性截图可移到仓库外备份，不能替代现行源码和测试。

真实 CodeLab 浏览器验收使用 `frontend/src/e2e/codelab.spec.ts`，默认连到开发前端。需要隔离时，将 Playwright 指向 `http://127.0.0.1:15174`，并让测试 API 使用 `APP_ENV=test`、`TEST_DATABASE_URL` 和当前 loopback runner；不要让测试 API 使用开发库。分别设置 `E2E_CODELAB_STAGE=JUNIOR` 和 `E2E_CODELAB_STAGE=SENIOR`，从 `frontend` 目录明确运行该测试文件：

```bash
CODELAB_E2E_BASE_URL=http://127.0.0.1:15174 E2E_CODELAB_STAGE=JUNIOR \
  npx playwright test --config playwright.config.ts src/e2e/codelab.spec.ts --reporter=line
```

## 2026-09-29 阶段检查

本次整理执行了 `./k12 check`：协议 38 项、后端 424 项、前端 141 项通过，
四份 OpenAPI／TypeScript 类型一致性、Ruff、类型检查、生产构建和 Knodo 资产校验通过。
后端 2 项真实 runner 测试因未设置专用运行参数跳过。Knodo 资产反例自检也通过。

`npm run test:e2e:ui --prefix frontend` 的 24 项合成接口浏览器测试通过，包含 320、390、768、1440px
尺寸场景。本次没有重新进行真实 Knodo、真实 runner 或全套 live 浏览器验收；部分专项 live 用例
仍有旧登录／引导页断言，应在准备对应隔离环境时更新和复验，不能将其算作当前通过。

构建仍提示主 JavaScript 包约 1.13 MB（gzip 约 362 KB）；后端有 Starlette 兼容性弃用警告。
这些是下一阶段可处理的已知事项，本次未借清理工作升级依赖或改动业务行为。
