# K12人工智能教学平台

霜铃 K12：面向比赛展示的 AI 教学作品，串联课程学习、自由对话、互动练习、动画演示、在线编程和学习记录。
采用 FastAPI + React/TypeScript/Vite + PostgreSQL，AI 通过 Knodo Tutor / Designer 接入。

本项目为非开源比赛作品，代码保存在私有仓库
[K12-AI-Teaching-Platform](https://github.com/zxkk97984-creator/K12-AI-Teaching-Platform)。
`main` 保存阶段基线，`Xiaoxiao/next-phase` 用于下一阶段开发；仓库不包含本机密钥、数据库或上传文件。

## 启动

本机运行配置位于 `~/.config/k12/runtime.env`，由 `./k12 setup` 首次创建，
模板为 [config/runtime.env.example](config/runtime.env.example)。已有配置和数据库凭据会保留。
详细步骤见[本地开发说明](docs/operations/LOCAL_DEV.md)。

```bash
./k12 setup           # 首次配置、依赖、数据库迁移与课程导入
./k12 start --build   # 按当前源码构建并启动完整服务
./k12 status          # 查看服务
```

前端：<http://127.0.0.1:15173>；API：<http://127.0.0.1:18081>。
修改运行配置后使用 `./k12 restart` 重启应用。

比赛演示使用示例账号和四学段演示课程。`GATEWAY_MODE=fixture` 用于离线演示和测试；真实 Knodo 模式
使用本机配置中的平台凭据和目标。对话页面支持不选课程直接提问，CodeLab 需单独启动
[Docker runner](docs/operations/RUNNER_T24.md)。需要完整本地编程演示时，先运行
`./k12 setup --with-runner` 构建 runner，再运行 `./k12 start --with-runner`；脚本会在用户状态目录
自动生成权限为 600 的 runner token，同时启动 API、worker、前端和回环 runner。

## 当前项目状态

截至 2026-09-29，学生默认进入 `/workbench`，管理员进入 `/admin/resources`。
未完成首次设置的学生先选择具体年级；一年级至高三映射到小学低段、小学高段、初中和高中。
四学段共用业务数据和账号体系，首页、导航名称及内容入口按学段变化。

| 模块 | 当前入口与能力 |
| --- | --- |
| 学习首页 | `/workbench`：四学段布局、学习入口、书架和继续学习 |
| 资源与阅读 | `/resources`、`/study`：资料筛选、课程、书架、收藏和阅读历史；`/books/:bookSlug` 提供三本内置教材；`/picturebooks` 提供小学绘本续读 |
| AI 教师 | `/conversations`：无课程也可提问、历史会话、回复生成练习；桌宠支持当前页面提问；`/study/lesson` 提供课程课堂 |
| 互动内容 | `/animations` 讲解、`/activities` 探索、`/practice` 小学小游戏；`/interactive/:resourceId` 支持场景、进度保存、恢复和重试 |
| 学科练习 | `/practice`：按章节或教师回复生成、答题与提示、草稿、结果回顾、收藏；初高中提供错题入口 |
| CodeLab | `/code`：初中／高中各 6 道题，搜索筛选、收藏、草稿、公开示例、正式判题和历史回看 |
| 个人记忆 | `/growth`：账号 Markdown 主文档的创建、编辑、预览和版本恢复，当前保存内容供 AI 教师参考 |
| 学习设置 | `/settings`：年级、昵称、头像、教师风格、语音偏好和六套桌宠形象；昵称不改变登录账号 |
| 教学管理 | `/admin/resources` 管理资料，`/admin/resources/interactive` 导入和发布互动包，`/admin/authoring` 生成题目与课程草稿 |

内置教材源文件在 `frontend/src/features/books/content/`；绘本和学段知识点示例的唯一维护源为
`curriculum/source/synthetic/k12-demo-v1/student-content.json`。它们是预置内容，不冒充实时 AI 生成。
互动内容支持 HTML 或 ZIP 包，制作与导入规则见[互动内容接入说明](docs/operations/INTERACTIVE_CONTENT.md)。
[趣味答题小游戏](docs/competition/趣味答题小游戏.html) 保留为可独立打开的演示素材。

### 当前能力边界

- 个人记忆由用户手动填写，没有自动总结聊天或语义检索。文档最多保存 20,000 字符，单份注入最多 1,200 字符（含说明），优先保留主文档开头；空文档和旧版本不注入。后台候选记忆机制仍在，但当前页面没有候选确认入口。
- 练习生成失败会显示失败状态。CodeLab 公开示例不产生正式成绩，提交判题使用服务器可信用例和 70 分制；AI 建议独立标明来源，不改变成绩。runner 未启动时不能声称代码已执行。
- 语音输入、回复朗读和互动讲解依赖浏览器能力、权限、中文语音或内容包音频；独立服务端 ASR/TTS 未接入。文本输入始终是基础入口。
- 完整演示取决于本机 Knodo、runner 和已发布内容。静态检查、合成浏览器测试与真实调用分别记录，不把通过测试等同于教学效果已验证。

学生端视觉源自本机 Open Design 的页面与素材设计，实际实现以 `frontend/src` 和
`frontend/public` 为准，运行不依赖 Open Design 项目。旧静态 HTML 导出、重复绘本定义、
废弃前端组件和一次性验收材料已清理；现有数据库迁移、课程历史版本、协议和仍被工具引用的
Knodo 历史评测资产继续保留。

## 检查

```bash
./k12 check
```

包含协议测试、后端测试与静态检查、OpenAPI 类型一致性、前端测试、类型检查和构建。
后端测试使用独立的 `55434 / k12r1_test` 数据库。可按修改范围单独执行：

```bash
python3 contracts/test_contracts.py -v
npm test --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
npm run test:e2e:ui --prefix frontend # 使用拦截 API 的合成浏览器场景
python3 scripts/package-knodo.py verify
```

## 项目导航

| 目录 | 内容 |
| --- | --- |
| `backend/app` / `backend/tests` | API、教学业务、后台任务与测试 |
| `frontend/src` | 页面、组件和浏览器测试 |
| `contracts` | 协议、示例与 OpenAPI |
| `curriculum` | 课程源、发布版本、动画和编程题 |
| `platform/knodo` | Tutor / Designer 提示词、Skill 和交付资产 |
| `runner` / `scripts` | 编程执行环境与开发工具 |
| `evals` | 教学评测用例与评测工具 |

[开发指引](AGENTS.md) · [启动说明](docs/operations/LOCAL_DEV.md) ·
[互动内容接入说明](docs/operations/INTERACTIVE_CONTENT.md) ·
[浏览器回归](docs/acceptance/ui-reuse/README.md) · [Knodo 接入](docs/integrations/knodo/DEPLOYMENT_GUIDE.md) ·
[演示脚本](docs/competition/DEMO_SCRIPT.md) · [参赛报告](docs/competition/REPORT_DRAFT.md)

密钥保存在仓库外；演示数据与真实学生数据分开。功能和评测结果按实际完成情况介绍。
