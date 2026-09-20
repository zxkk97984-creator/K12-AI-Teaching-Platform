# Knodo 部署与配置说明（人工步骤，PACKAGED → DEPLOYED 分离）

适用对象：有 Knodo 租户权限的团队操作者。
本仓交付物是**文件资产**（ZIP + manifests），不是 Knodo 官方一键 Bot 导入包，也不代表任何
Bot/Skill 已在线可用。真实创建、上传、读取验证必须在获得平台授权后由人工执行，并按本文件登记。

## 0. 当前状态（如实记录，禁止提前打勾）

| 项目 | 状态 | 证据 |
|---|---|---|
| 资产已打包 | PACKAGED | `platform/knodo/releases/knodo-assets-1.0.0/SHA256SUMS` |
| Bot/Skill 已部署 | NOT_DEPLOYED | `platform/knodo/deployment-manifest.json`（`bot_id: null`） |
| 真实租户读取验证 | NOT_RUN | 无平台执行证据 |
| Skill 在线加载 | NOT_RUN | 同上 |
| 教学效果 | NOT_RUN | 同上 |

当前声明范围为成人参赛者 + 合成学生数据，不使用真实未成年人，因此 `G_K12_TERMS` 不阻塞
这个合成竞赛原型；若范围扩展，必须重新取得该门禁证据。其余真实性门禁仍 BLOCKED：
`G_API_CONTRACT`、`G_LIVE_BUDGET`、`G_AGENT_ISOLATION`、`G_HUMAN_CONTENT_REVIEW`。
本指南**不会**因为“打包成功”而解锁任何真实性门禁。

## 1. 人工部署步骤（每个租户执行一次）

1. **取得授权**：确认本次操作已获平台写入授权与预算授权；未获授权时到第 0 步为止。
2. **核对租户条款**：当前仅成人参赛者 + 合成学生数据，不进入真实未成年人场景；若未来改为真实 K12，必须先确认租户允许该用途。
3. **创建 Tutor Bot**：在平台按官方菜单创建，绑定的系统提示词取自
   `platform/knodo/tutor/v1/system-prompt.md`（与 `bot-profile.json` 同版本）。
   仅使用 `TEACH_TURN`、`CODE_FEEDBACK` 两类操作，不依赖平台原生多 Agent 或工作流格式。
4. **创建 Designer Bot**：系统提示词取自 `platform/knodo/designer/v1/system-prompt.md`，
   仅使用 `QUIZ_DRAFT`、`LESSON_PACKAGE_DRAFT` 两类操作。
5. **上传 Skill（三份，分别配置，不合并、不改名）**：
   - `k12-teaching-core` → 绑到 Tutor
   - `k12-assessment-author` → 绑到 Designer
   - `k12-content-author` → 绑到 Designer
   ZIP 位于 `platform/knodo/releases/knodo-assets-1.0.0/skill-*.zip`；系统提示词与 Skill
   是**分别配置**的两类资产。
6. **挂载课堂知识包**：`bundles-classroom.zip` 为 Teacher 可见内容（当前仅含显式标记的测试
   内容，`is_test_fixture=true`）。标准答案、参考解、隐藏测试、原始学生档案一律不挂载。
7. **核对权限清单**（逐项勾选，缺一不可）：
   - [ ] 模型：租户实际可用模型 ID（记录真实值，不写猜测；本仓不预填）
   - [ ] AgentOS / 运行环境：实际版本与区域
   - [ ] 工具权限：仅授予上述四类操作所需的工具；禁用不必要的文件/网络工具
   - [ ] 历史（history）：确认是否开启、保留时长、是否跨会话
   - [ ] 记忆（memory）：确认写入范围与隔离边界；学生数据不得进入共享记忆
   - [ ] 隔离：确认租户/工作空间隔离边界（对应 `G_AGENT_ISOLATION`）
8. **回填登记**：把真实的 Bot ID、workspace ID、模型 ID、AgentOS 版本、上传时间与
   实际加载结果写回团队登记（**不是**本仓的 `deployment-manifest.json` 默认值）。
   只有拿到平台执行证据（含与本地 run 的关联标识）后，状态才可从 NOT_DEPLOYED 改为 DEPLOYED。

## 2. 明确禁止

- 不把本仓 ZIP 描述为"官方一键导入"；
- 不在无授权时创建 Bot、上传 Skill、发起付费调用或创建学生账号；
- 不写入或猜测 `bot_id`/`workspace_id`；不复制 PAT 到文档、代码或测试；
- 不把公开文档快照里的示例参数当作已验证的官方 HTTP 契约（见 `CONTRACT_DISCOVERY.md`）。

## 3. 回滚

- 未部署：删除本地 `platform/knodo/releases/<release_id>/` 重新打包即可，无平台副作用。
- 已部署（由人工执行）：在平台停用对应 Bot/Skill 绑定 → 恢复上一版本哈希的资产 →
  在登记中记录回滚时间与操作人；本地资产按 `release-manifest.json` 的 SHA256 校验后重放。
