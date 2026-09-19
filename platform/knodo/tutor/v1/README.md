# Tutor 交付资产 v1

- `system-prompt.md`：Tutor 系统提示词（源：`.rebuild-kit/platform/prompts/TUTOR_SYSTEM.md`，逐字复制）。
- `bot-profile.json`：角色、operation、绑定 Skill、响应模式与禁止接收清单。
- 绑定 Skill：`k12-teaching-core`。

平台配置：把本目录的 `system-prompt.md` 粘贴到 Tutor Bot 的系统提示词，单独上传 `skill-k12-teaching-core.zip`，
挂载 `bundles/classroom` 知识包。**系统提示词与 Skill 是两项配置**，不是一个 ZIP 一键导入。

当前状态：`NOT_DEPLOYED`（无 bot_id）。真实部署与读取验证步骤见 `docs/integrations/knodo/DEPLOYMENT_GUIDE.md`。
