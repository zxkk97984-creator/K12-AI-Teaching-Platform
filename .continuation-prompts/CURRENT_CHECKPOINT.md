# 续作起点：用户报告的T05检查点

本记录根据用户本轮提供的摘要整理，供后续Agent恢复上下文。不是我读取其本地源码或重跑测试后的独立验收，不能替代实际的docs/acceptance/T05.md。

目标：/home/zxk/Projects/K12。T00—T05已由执行Agent报告完成，current_task=T06。

固定技术：Python3.12/FastAPI、React/TypeScript/Vite、独立PostgreSQL；Knodo两类Bot，受限runner。不要切Next.js或复用旧JWT/localStorage登录。

已报告的身份基线：
- 本地学生/管理员、Argon2id密码；sl_session HttpOnly，DB仅存SHA-256 token hash，服务端可撤销。
- sl_csrf双提交CSRF与同源Origin检查；登录、登出和全部PATCH受保护。
- /auth/login、/auth/logout、/me、/me/profile、/me/preferences及管理员状态接口已实际实现。完整前缀和字段读本地OpenAPI，不另起一套。
- stage四档：1—3/4—6/7—9/10—12；grade可空；冲突与非法值422。
- 偏好含讲解方式、兴趣、主动引导、语音；语音只保存偏好，真实能力未开启。
- PATCH携带base_revision，旧版本409且无部分更新。
- 已应用迁移0001_identity、0002_identity_constraints；新迁移接在实际head之后，不能编辑已应用迁移制造新基线。
- contracts/openapi.identity.json真实导出，前端openapi-typescript生成类型。
- 登录/onboarding/设置/401/503页面已接通，不重做。

用户报告的验证（历史参考，不是后续任务的新增通过数）：后端28 passed，原契约38 passed，前端3 passed，Playwright2 passed，scripts/check.sh与scripts/identity-e2e.sh均exit0。A修改偏好刷新保留、注销后旧Cookie401、B不能借伪造A标识越权。

环境：开发库k12r1_dev @127.0.0.1:55433；测试库k12r1_test @127.0.0.1:55434。两者迁移revision为0002_identity_constraints。缺测试配置/误指开发库时，在迁移/清表/fixture写入之前拒绝。旧shuangling-*和5432/6379/9000/9001不动。

现存快照：.snapshots/T05-before-20260918/（65文件，报告称校验通过）。证据位置：docs/acceptance/T05.md、T05-check.log、T05-browser.log、浏览器JSON/脱敏截图、运行清单和负向日志。读取报告定位准确日志路径，不假定全部日志与MD同目录。

根.env不存在，不必创建。现阶段临时配置记录为/tmp/k12r1-t05.env，权限600；仅在实际文件仍存在且归属/权限正确时通过已定脚本加载，不打印、不复制进提示词、不扫描其他人的/tmp。持久密钥与合成账号配置PENDING_USER_ACTION；不能轮换DB密码或重建卷。临时配置失效时只阻塞依赖它的运行验证，不假造已运行。

项目不是Git仓库；未获git init/add/commit/push授权。保留当前状态，必要时只对将改的非敏感源码做有清单/哈希的受限快照，排除.env、密钥、Cookie、数据库数据和依赖目录。不要凭猜测重建.agents/.codex。

G_API_CONTRACT、G_LIVE_BUDGET、G_AGENT_ISOLATION、G_K12_TERMS、G_HUMAN_CONTENT_REVIEW仍BLOCKED。未调用Knodo、未使用PAT、未开放真实未成年人注册。T02已记录部分公开Bot字段，不把已有证据说成完全没有；完整契约/租户行为仍按证据核对。

本文件只是当时检查点，不能用于覆盖真实progress.json。后续完成T06等后，以本地进度、验收和源码为准；不反复重跑T00—T05全部审计。
