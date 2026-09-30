# Knodo 资产说明

| 资产 | 使用位置 |
| --- | --- |
| `tutor/v1/stages/{primary,junior,senior}.md` | 三位教师：讲解与编程反馈；共用基础模板保留在 `system-prompt.md` |
| `designer/v1/system-prompt.md` | Designer：题目与课程草稿 |
| `memory/v1` | 内部记忆助手：结构化提取，不直接写数据库 |
| `skills/k12-teaching-core` | 教师共用 Skill |
| `skills/k12-assessment-author`、`skills/k12-content-author` | Designer Skills |
| `bundles/classroom` | 教师可读资料：四学段入门章节与原有 fixture；不含学生个人记忆 |
| `stage-policy.json` | 四档学段策略的维护源 |

以上路径相对 `platform/knodo`。协议维护源在根目录 `contracts`，发布时保持资产中的副本一致。
答案、参考解和隐藏测试留在服务端，避免教学提示直接泄露解答；密钥不进入任何资产包。

`python3 scripts/package-knodo.py verify` 校验哈希、协议副本和答案分离；
`python3 scripts/package-knodo.py selftest` 检查篡改、路径越界等反例。
本地包版本与实际 Bot 绑定分别管理，配置步骤见 [接入指南](DEPLOYMENT_GUIDE.md)。

完整 Plugin 包 `plugin-*.zip` 与单独 Skill 包 `skill-*.zip` 分别生成。Plugin 清单必须含 `author` 对象；知识包、提示词和插件也不能混用上传入口。新增教师只需数据库配置及对应 Knodo 助手，无需修改固定路由代码。

学生记忆存于本地 PostgreSQL，只有当前学生的相关内容进入本轮请求。空间级插件对空间内所有助手可用，个人技能可以按助手绑定；本地能力开关不能替代远端权限。管理端分别展示本地登记、空间读取核验和协议探测，未核实的个人绑定或单轮 Skill 执行不宣称已验证。
