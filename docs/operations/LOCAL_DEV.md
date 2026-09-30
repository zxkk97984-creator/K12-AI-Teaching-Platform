# 本地运行与开发

当前项目的 GitHub 备份是私有仓库 `zxkk97984-creator/K12-AI-Teaching-Platform`，
与旧 `K12-Learning-platform`、`k12-multimodal-learning-assistant` 仓库独立。
`main` 保存已集成版本，功能开发使用独立分支。私有仓库只保存代码与必要资产，
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
./k12 logs --tail 100 api worker memory-worker
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
`k12r1` Compose 项目标记的 API、教学 worker、记忆 worker、web 容器；未知端口占用会直接报错。

`check` 使用 fixture 网关和独立测试库，验证协议、OpenAPI 与前端类型同步、后端测试与
格式、前端测试与构建，以及 Knodo 资产。测试库连接必须通过隔离地址校验。
浏览器检查可运行 `npm run test:e2e:ui --prefix frontend`；演示账号由本机配置和
`scripts/seed-demo-accounts.sh` 管理。特殊工具如 `scripts/package-knodo.py`、
`scripts/build-runner.sh` 仍可直接运行。

Knodo ZIP 不提交 Git；首次克隆或修改提示词／技能／打包源后，先运行 `python3 scripts/package-knodo.py build`，再执行 `./k12 check`。构建生成的 SHA 和发布清单需要与对应源码一起提交，实际 Bot 绑定仍从数据库读取。

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

当前 `/growth` 展示自动记忆、手写文档、条目管理及整理状态；旧学习证据和候选记忆仍保留兼容，不应因入口调整而删除相关表、API 或测试。旧 UI 导出与一次性截图可移到仓库外备份，不能替代现行源码和测试。

真实 CodeLab 浏览器验收使用 `frontend/src/e2e/codelab.spec.ts`，默认连到开发前端。需要隔离时，将 Playwright 指向 `http://127.0.0.1:15174`，并让测试 API 使用 `APP_ENV=test`、`TEST_DATABASE_URL` 和当前 loopback runner；不要让测试 API 使用开发库。分别设置 `E2E_CODELAB_STAGE=JUNIOR` 和 `E2E_CODELAB_STAGE=SENIOR`，从 `frontend` 目录明确运行该测试文件：

```bash
CODELAB_E2E_BASE_URL=http://127.0.0.1:15174 E2E_CODELAB_STAGE=JUNIOR \
  npx playwright test --config playwright.config.ts src/e2e/codelab.spec.ts --reporter=line
```

## 验证入口与结果范围

`./k12 check` 使用隔离数据库和 fixture 网关，不发起真实 Knodo 调用。浏览器合成回归使用拦截 API，验证实际页面交互；真实模型调用需单独执行：

```bash
./scripts/knodo-live-test.sh
```

脚本从本机运行配置读取 PAT，对开发库的教师注册表仅做只读快照，然后在隔离的 `55434 / k12r1_test` 数据库运行 `test_knodo_live_ai_memory.py`。快照只在权限 600 的临时文件中保存，退出时删除。需要先启动测试数据库、完成迁移与 `/admin/ai` 配置；按当前三位教师的 `primary`、`junior`、`senior` 标识及内部记忆路由验收。它会清理隔离测试库，不能与其他后端 pytest 同时运行。

真实验收包含四学段路由、成功回复后的自动提取、跨会话与跨教师召回、人工更正、遗忘后的上下文、另一账号隔离和旧来源重放抑制。合成消息会在 Knodo 产生远端会话。结果按本次命令输出判断，不能用绑定核验、fixture 或历史结果代替真实调用。

2026-09-30 已执行完整检查：协议 38 项、后端 443 项、前端 143 项通过；四份 OpenAPI／TypeScript 同步、Ruff、类型检查、构建和 Knodo 包校验通过。默认后端回归跳过 3 项（2 项专用 runner 用例、1 项真实 Knodo 用例）。另行运行真实 Knodo 验收，7 次教师回复与 1 次记忆提取的完整流程通过；合成浏览器回归 26 项通过，覆盖桌面及 320／390 等窄屏场景。Plugin 缺少作者、ZIP 篡改、路径越界、密钥注入及协议篡改反例自检通过。

这次未重新执行专用 runner live 用例或真实后端的全套浏览器流程，不能将合成 UI 回归算作真实端到端验证。构建仍提示主 JavaScript 包约 1.14 MB（gzip 约 365 KB），后端仍有 Starlette 兼容性弃用警告；未借本次交付升级依赖。

## AI 配置与个人记忆

`/admin/ai` 管理教师和学段路由；`/growth` 查看自动记忆、手写文档和后台整理状态。
启动命令现在同时启动独立的 `memory-worker`，避免记忆提取阻塞聊天。
默认合并窗口 30 秒、连续聊天最长等待 120 秒；可通过本机配置中的
`MEMORY_COALESCE_SECONDS`、`MEMORY_MAX_WAIT_SECONDS`、`MEMORY_EXTRACT_TIMEOUT_SECONDS` 调整。

Tutor/Designer 环境变量只用于注册表首次初始化，Tutor 的 Bot／空间变量可以同时留空。已有数据库配置不会被后续启动覆盖；后续改绑使用管理页面。当前旧课堂教师已退役，三位教师、Designer 和内部记忆助手使用数据库绑定。
新增教师及内部记忆助手的 Knodo 配置见 `docs/integrations/knodo/DEPLOYMENT_GUIDE.md`。
没有绑定真实记忆助手时，任务明确提示待配置，不会伪造成功总结。

管理端新增教师时设置名称、角色、Bot／工作空间、提示词版本，保存后核验并测试协议，再启用和调整学段路由。系统提示词、模型、Plugin 内容及助手个人技能仍在 Knodo 配置；本地能力登记不等于远端已生效。配置步骤见[Knodo 接入指南](../integrations/knodo/DEPLOYMENT_GUIDE.md)。

用户可分别关闭自动整理和聊天召回；手动整理历史聊天可取消、重试。删除会话默认保留自动记忆，勾选“同时遗忘”才撤回关联自动条目。遗忘不删除手写文档，也不承诺删除 Knodo 的历史。个人数据导出与清理覆盖自动条目、来源、摘要和后台任务。
