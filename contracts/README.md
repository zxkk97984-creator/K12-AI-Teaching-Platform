# 本地业务契约

版本：`1.0.0`  
状态：本地语义契约，不是 Knodo HTTP wire。

这些 schema 约束教师／Designer 的建议和草稿，以及内部记忆提取结果：请求标识、账号／课程版本、来源、允许动作和结构化输出。示例全部是 synthetic fixture；经服务端校验并由 HTTP 适配器包装后才能用于合成调用，不能把业务 JSON 当作 Knodo HTTP 请求体。

- `teaching-request.schema.json` / `teaching-response.schema.json`
- `designer-request.schema.json`
- `quiz-draft.schema.json`
- `lesson-package-draft.schema.json`
- `memory-extract-request.schema.json` / `memory-extract-response.schema.json`：独立的 `k12.memory.extract.*.v1` 契约，来源消息、现有条目、候选事实与会话摘要。
- `knodo-wire-evidence.template.json`：仅调查模板，未知字段必须保留 null。

教学请求的可选 `personal_context` 携带服务端检索的自动记忆和手写内容，不能当作系统指令、评分证据或“用户已确认”事实。学生不能提交任意 Bot ID 或工作空间 ID。

验证命令：`python3 contracts/validate_contracts.py` 需要 `jsonschema`；单元测试为 `python3 contracts/test_contracts.py -v`。数据库、权限、状态机和发布服务继续执行交叉校验。修改记忆 Pydantic 模型后运行 `uv run --project backend --locked python -m app.modules.memory.contracts` 同步根目录、Knodo 副本及提示词，再更新 SHA 清单并重新打包：

```bash
(cd contracts && sha256sum *.schema.json knodo-wire-evidence.template.json version.json > SHA256SUMS)
cp contracts/SHA256SUMS platform/knodo/contracts/SHA256SUMS
python3 scripts/package-knodo.py build
python3 scripts/package-knodo.py verify
```

## 身份 HTTP OpenAPI

`openapi.identity.json` 是 FastAPI 运行时导出的实际接口文档，包含 `/api/v1/auth/*`、`/api/v1/me`、管理员状态和会话/CSRF Cookie/Header 参数。前端类型由 `frontend/package.json` 的 `generate:identity` 从该文件生成；不要手写第二套冲突 DTO。

`openapi.content.json` 同样由运行时导出，除课程、章节和阅读接口外，包含学习中心的目录、书架、打开记录、历史和继续学习接口。

`openapi.learning.json` 覆盖学习、练习、CodeRun、聊天、个人文档及 `/api/v1/growth/personal-memory` 的条目、开关和历史整理任务；对应生成类型为 `frontend/src/shared/types/generated/learning.ts`。

`openapi.admin.json` 包含教学管理及 `/api/v1/admin/ai/` 注册表、远端核验、协议探测和提示词模板。配置保存与个人记忆修改使用版本冲突检查，管理接口不返回 PAT，也不默认开放学生记忆正文。`./k12 check` 核对四份 OpenAPI 与生成 TypeScript，不另建手写 DTO。
