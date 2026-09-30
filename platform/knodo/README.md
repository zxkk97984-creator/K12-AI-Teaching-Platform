# platform/knodo —— Knodo 交付资产

本目录保存三位教师、Designer、内部记忆助手的提示词，三份 Skill 及完整 Plugin 包、受控课堂知识包与私有边界清单。系统提示词、插件和知识包分别配置，不是一键 Bot 导入包，也不代表任何 Skill 已在线加载。

运行目标和学段映射由 `/admin/ai` 的数据库注册表管理；本机配置保存 PAT、地址及可选首次初始化目标。本目录 manifest 只记录可复现包版本，保持 `PACKAGED / NOT_DEPLOYED`，不会冒充个人部署证据。实际远端核验与协议探测结果在管理页面查看。
操作步骤见 `docs/integrations/knodo/DEPLOYMENT_GUIDE.md`，资产说明见
`docs/integrations/knodo/ASSET_BOUNDARIES.md`。

## 目录

```
platform/knodo/
  VERSION.json                 包版本 + 契约版本
  contracts/                   业务契约副本（与 contracts 同步）
  tutor/v1/                    Tutor 公共提示词，stages/ 包含三位教师的完整提示词
  memory/v1/                   内部记忆助手提示词与提取协议
  designer/v1/                 Designer 系统提示词、Bot profile、题稿样例（样例只用于校验）
  skills/<name>/               SKILL.md + references/（schema 与冻结契约逐字节一致）
  bundles/classroom/           Tutor 可见课堂知识包（当前只有显式标记的测试内容）
  bundles/designer-private/    Designer 私有边界（本发布不含答案类素材）
  releases/<release_id>/       ZIP + SHA256SUMS + release-manifest.json
  deployment-manifest.json     本地五个助手角色与包哈希，不写个人部署凭据
```

## 复现与校验

```bash
python3 scripts/package-knodo.py build-bundles          # 从 curriculum/releases 生成课堂知识包
python3 scripts/package-knodo.py build                  # 生成 ZIP + SHA 清单 + 部署登记
python3 scripts/package-knodo.py verify                 # 安全/哈希/schema/答案边界/部署状态全套校验
python3 scripts/package-knodo.py selftest               # 篡改、越界、绝对路径、密钥注入反例
```

ZIP 是可复现产物：条目顺序、时间戳与压缩级别固定，重复构建字节一致。

`skill-<name>.zip` 根目录是 `SKILL.md`，用于单独上传 Skill；`plugin-<name>.zip` 包含 `.claude-plugin/plugin.json`、`plugin.yaml` 和 `skills/<name>/`，用于创建或替换完整 Plugin。构建器补齐并校验 `author` 对象，不要混用两种上传入口。

三位教师共享课堂空间的 `k12-teaching-core` 时无需重复个人绑定；空间插件会合并到助手技能中。记忆助手只返回结构化候选，保存、召回、归属和遗忘由本地 PostgreSQL 处理，个人记忆不能上传到共享课堂知识包。新增后端能力通过受控处理器与输入输出契约接入，不加载用户提交的任意脚本。
