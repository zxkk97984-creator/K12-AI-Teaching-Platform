# Knodo 资产说明

| 资产 | 使用位置 |
| --- | --- |
| `tutor/v1/system-prompt.md` | Tutor：讲解与编程反馈 |
| `designer/v1/system-prompt.md` | Designer：题目与课程草稿 |
| `skills/k12-teaching-core` | Tutor Skill |
| `skills/k12-assessment-author`、`skills/k12-content-author` | Designer Skills |
| `bundles/classroom` | Tutor 可读取的课堂资料 |
| `stage-policy.json` | 四档学段策略的维护源 |

以上路径相对 `platform/knodo`。协议维护源在根目录 `contracts`，发布时保持资产中的副本一致。
答案、参考解和隐藏测试留在服务端，避免教学提示直接泄露解答；密钥不进入任何资产包。

`python3 scripts/package-knodo.py verify` 校验哈希、协议副本和答案分离；
`python3 scripts/package-knodo.py selftest` 检查篡改、路径越界等反例。
本地包版本与实际 Bot 绑定分别管理，配置步骤见 [接入指南](DEPLOYMENT_GUIDE.md)。
