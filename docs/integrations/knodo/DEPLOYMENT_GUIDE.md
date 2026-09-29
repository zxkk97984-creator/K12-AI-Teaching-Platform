# Knodo 接入与资产配置

日常运行使用 `~/.config/k12/runtime.env` 中的网关模式、PAT、Tutor/Designer Bot ID 和 workspace ID。
配置模板为 `config/runtime.env.example`；更新后执行 `./k12 restart`。
已有目标可直接复用，不需要重新创建 Bot 或执行历史任务审批。

## 配置资产

1. Tutor 使用 `platform/knodo/tutor/v1/system-prompt.md`，绑定 `k12-teaching-core` Skill。
2. Designer 使用 `platform/knodo/designer/v1/system-prompt.md`，绑定
   `k12-assessment-author` 和 `k12-content-author` Skill。
3. 如需课堂知识包，使用 `platform/knodo/bundles/classroom`；答案与隐藏测试留在服务端。
4. 系统提示词、Skill、知识包分别配置。打包 ZIP 是资产文件，不是平台的一键 Bot 导入格式。

```bash
python3 scripts/package-knodo.py build-bundles
python3 scripts/package-knodo.py build
python3 scripts/package-knodo.py verify
python3 scripts/package-knodo.py selftest
```

`platform/knodo/deployment-manifest.json` 描述本地打包版本，实际运行目标以本机配置为准。
历史真实调用结果保存在本目录的 `live-smoke.redacted.json` 和
`docs/acceptance/T31-live-summary.json`；这些记录不代表当前连接一定可用。

## 接口与调试

Tutor 支持 `TEACH_TURN`、`CODE_FEEDBACK`；Designer 支持 `QUIZ_DRAFT`、`LESSON_PACKAGE_DRAFT`。
业务输入输出由 `contracts` 校验，HTTP 适配位于 `backend/app/integrations/knodo`。
接口说明见 [Simple API](SIMPLE_API_SUMMARY.md)。

CodeLab 的 Tutor 反馈只在确定性 runner 已完成后发起：服务端从保存的运行快照重建
`CODE_FEEDBACK` 请求，并校验返回内容必须绑定同一个运行 ID 和代码哈希。AI 建议不会改变
判题结果。runner 未配置、运行中、取消或缺少可信输出时，界面显示对应状态，不会把平台故障记成学生错误。

本地测试用 fixture，真实演示用已授权的 Knodo 配置和预算。PAT 不放到浏览器、文档或截图。
返回失败时检查 API/worker 日志、目标配置与超时；模拟结果按模拟结果展示。
