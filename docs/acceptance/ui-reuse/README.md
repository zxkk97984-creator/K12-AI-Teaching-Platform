# 当前界面的浏览器回归

当前学生端已采用四学段布局。本目录只保留测试入口说明；早期 CareerMate UI 复用清单、
批次日志和旧界面截图已移出工作树，不能作为当前版本的通过证明。

## 合成接口场景

从仓库根目录运行：

```bash
npm run test:e2e:ui --prefix frontend
```

`frontend/playwright.ui.config.ts` 自动启动或复用 `127.0.0.1:15173` 的 Vite，
运行 `ui-reuse.spec.ts` 和 `codelab-ui.spec.ts`。接口由测试拦截，未匹配的 API 返回 503；
不会调用真实 Knodo、runner 或写入开发库。

覆盖四学段导航、首页、聊天与桌宠、资源与绘本、互动内容保存及重试、个人记忆编辑和版本恢复、
账号切换隔离、设置与头像，以及 CodeLab 题库和工作区。测试中有窄屏尺寸检查；
这些结果不等于真实设备、Safari 或后端端到端验收。

## 真实后端场景

`frontend/playwright.config.ts` 用于连接已运行的完整服务。按测试文件准备专用合成账号、
发布课程、资源及 runner，并显式选择文件运行，避免把 fixture 套件或缺少前提的旧场景一并执行。
使用隔离测试库，配置方法见[本地开发说明](../../operations/LOCAL_DEV.md)。

个人记忆当前页面的浏览器覆盖位于 `ui-reuse.spec.ts`；已移除针对旧“成长观察／候选确认”页面的
`growth.spec.ts`。后台候选记忆状态机与账号隔离仍由 `backend/tests/test_growth_memory.py` 检查，
文档接口和 Tutor 注入分别由 `test_memory_documents.py`、`test_free_conversations.py` 检查。

报告和截图输出到 `frontend/test-results/`，不提交到 Git。检查结果以当次命令输出为准，
不把历史实测数量或跳过项写成当前通过。
