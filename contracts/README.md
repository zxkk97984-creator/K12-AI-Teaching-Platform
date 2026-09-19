# 本地业务契约

版本：`1.0.0`  
状态：本地语义契约，不是 Knodo HTTP wire。

这些 schema 约束 Tutor/Designer 的建议/草稿边界：`request_id`、owner/课程 revision、来源三元组、允许动作、题量/难度、owner 校验和不能伪造人工审核。示例全部是 synthetic fixture；不得直接发送到 Knodo。

- `teaching-request.schema.json` / `teaching-response.schema.json`
- `designer-request.schema.json`
- `quiz-draft.schema.json`
- `lesson-package-draft.schema.json`
- `knodo-wire-evidence.template.json`：仅调查模板，未知字段必须保留 null。

验证命令：`python3 contracts/validate_contracts.py` 需要 `jsonschema`；单元测试为 `python3 contracts/test_contracts.py`。正式环境还必须由数据库、权限、状态机和发布服务执行交叉校验。

## 身份 HTTP OpenAPI

`openapi.identity.json` 是 FastAPI 运行时导出的实际接口文档，包含 `/api/v1/auth/*`、`/api/v1/me`、管理员状态和会话/CSRF Cookie/Header 参数。前端类型由 `frontend/package.json` 的 `generate:identity` 从该文件生成；不要手写第二套冲突 DTO。
