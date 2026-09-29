# K12 比赛作品开发指引

## 目标

这是霜铃 K12 教学助手的比赛作品。优先做好可运行的功能、完整的演示流程、界面体验和答辩材料。
以用户当前需求、现有代码和实际运行结果为准，不套用正式上线的审批流程。

## 项目与实现

- 工作目录：`/home/zxk/Projects/K12`。旧 K12、CareerMate 及其服务和数据库只作参考。
- 后端：`backend/app`，FastAPI / Python 3.12 / PostgreSQL；前端：`frontend/src`，React / TypeScript / Vite。
- AI 接入复用 Knodo Tutor / Designer；提示词、Skill 和打包资产在 `platform/knodo`，业务协议在 `contracts`。
- 课程与示例在 `curriculum`，代码执行在 `runner`，运行脚本在 `scripts`。
- 复用已有会话、四档学段、课程版本、题目快照和 OpenAPI 类型生成链，避免另建重复实现。

## 工作方式

- 默认单 Agent 直接完成修改、相关测试和第二遍复核。普通修复、重构、界面优化和文档维护连续推进。
- 不要求逐任务计划、进度 JSON、验收报告、角色 ACK 或审批单；复杂任务在对话里简述步骤即可。
- 历史 `.herdr-control` 仅为恢复记录，不加载其派工规则、不启动旧角色、不操作历史共享锁。
- 按实际改动选择测试；涉及行为变化时验证对应流程，涉及界面时检查浏览器效果。
- 完成后简要说明改动、验证结果和仍存在的问题；没有执行的测试不写成通过。
- 文档只维护使用者需要的说明。优先更新已有入口，不为每次工作新增计划、交接或总结文件。
- 当前功能入口以 `frontend/src/main.tsx`、`backend/app/main.py` 和 README 为准；旧静态页面、历史截图和验收批次不是实现依据。
- 浏览器截图和报告写入 `frontend/test-results/`；删除未跟踪的旧素材前先在仓库外保留可恢复副本，不把备份或一次性文件清单重新放入项目。

## 比赛范围与必要保护

- 演示可使用合成账号、示例课程和 fixture；展示时如实区分模拟结果与真实 Knodo 返回即可。
- 正式上线评审、真实未成年人准入、四档人工教学审校不作为本地比赛开发和演示的前置条件。
- 保留现有登录、CSRF、数据归属、答案隔离与 runner 沙箱保护；不为方便演示绕过它们。
- 密钥只放本机运行配置，不打印或提交；测试使用隔离测试库，不清空开发库、上传文件或旧项目数据。
- 已接入 Knodo 的本地调用次数不设项目上限，排查和验证可按需直接调用，无需按次数重新询问；新增购买额度、购买服务或公网发布需明确授权，不重复询问已授权事项。
- Git 使用本地历史，保留用户未提交改动；不添加远端、不 push、不重写已有历史。

## 常用入口

- 启动与配置：`README.md`、`docs/operations/LOCAL_DEV.md`。
- 首次配置与初始化：`./k12 setup`；按当前源码构建并启动：`./k12 start --build`。
- 日常开发：`./k12 dev`；查看状态：`./k12 status`；完整本地检查：`./k12 check`。
- 前端：`npm test --prefix frontend`、`npm run typecheck --prefix frontend`、`npm run build --prefix frontend`。
- 协议：`python3 contracts/test_contracts.py -v`；Knodo 资产：`python3 scripts/package-knodo.py verify`。
- 比赛演示与报告：`docs/competition/`；Knodo 配置：`docs/integrations/knodo/DEPLOYMENT_GUIDE.md`。
