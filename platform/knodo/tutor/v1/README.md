# 三学段教师交付资产 v1

- `stages/primary.md`、`junior.md`、`senior.md`：小学、初中、高中教师的完整提示词，小学两档共用小学教师。
- `system-prompt.md`：共用基础模板，供新增教师参考；保留文件不代表旧课堂教师仍在使用。
- `bot-profile.json`：角色、operation、绑定 Skill、响应模式与禁止接收清单。
- 绑定 Skill：`k12-teaching-core`。

平台配置：将对应阶段的完整提示词粘贴到各助手；课堂空间绑定 `k12-teaching-core` 并挂载 `bundles/classroom`。用 `plugin-k12-teaching-core.zip` 创建／替换完整 Plugin，`skill-k12-teaching-core.zip` 只用于单独上传 Skill。空间已绑定时不需要每位教师重复绑定。提示词不会自行安装插件，绑定也不证明每轮执行。

运行目标、版本和路由由 `/admin/ai` 管理，已有对话保存教师快照。真实配置和验收见 [Knodo 接入指南](../../../../docs/integrations/knodo/DEPLOYMENT_GUIDE.md)。
