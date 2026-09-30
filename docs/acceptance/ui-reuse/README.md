# 当前界面的浏览器回归

当前学生端已采用四学段布局。本目录只保留测试入口说明；早期 CareerMate UI 复用清单、
批次日志和旧界面截图已移出工作树，不能作为当前版本的通过证明。

## 合成接口场景

从仓库根目录运行：

```bash
npm run test:e2e:ui --prefix frontend
```

`frontend/playwright.ui.config.ts` 自动启动或复用 `127.0.0.1:15173` 的 Vite，
运行 `ui-reuse.spec.ts`、`codelab-ui.spec.ts` 和 `ai-memory-ui.spec.ts`。接口由测试拦截，未匹配的 API 返回 503；
不会调用真实 Knodo、runner 或写入开发库。

覆盖四学段导航、首页、聊天与桌宠、资源与绘本、互动内容保存及重试、个人记忆编辑和版本恢复、
账号切换隔离、设置与头像，以及 CodeLab 题库和工作区。新增场景检查教师配置保存、路由和能力页面、自动记忆更正／遗忘与关闭召回。历史整理、任务取消、远端核验和删除联动的业务行为由后端测试覆盖，不将页面截图当作这些流程的真实通过证据。测试中有窄屏尺寸检查；
这些结果不等于真实设备、Safari 或后端端到端验收。

## 真实后端场景

`frontend/playwright.config.ts` 用于连接已运行的完整服务。按测试文件准备专用合成账号、
发布课程、资源及 runner，并显式选择文件运行，避免把 fixture 套件或缺少前提的旧场景一并执行。
使用隔离测试库，配置方法见[本地开发说明](../../operations/LOCAL_DEV.md)。

个人记忆的手写文档覆盖位于 `ui-reuse.spec.ts`，自动整理和管理页面位于 `ai-memory-ui.spec.ts`；旧 `growth.spec.ts` 和依赖旧教师／旧布局的 `t13-live.spec.ts` 已退役。后台候选记忆状态机与账号隔离仍由 `backend/tests/test_growth_memory.py` 检查，
文档接口和 Tutor 注入分别由 `test_memory_documents.py`、`test_free_conversations.py` 检查。

自动记忆任务、来源合并、更正、遗忘、导出与清理由 `test_automatic_memory.py` 检查；`test_memory_extraction_response.py` 验证提取返回格式。实际教师与记忆验收运行 `./scripts/knodo-live-test.sh`，默认后端回归跳过该真实调用用例，不与其他后端 pytest 共用测试库并发运行。

报告和截图输出到 `frontend/test-results/`，不提交到 Git。检查结果以当次命令输出为准，
不把历史实测数量或跳过项写成当前通过。
