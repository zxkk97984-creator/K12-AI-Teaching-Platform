# Tutor / Designer 资产边界与 QA 对应（T09）

本文件把"哪份内容能进哪一类资产"写成可核对清单，并说明 T09 承担的两个通用场景
（QA16、QA35）在本卡的落点。打包器 `scripts/package-knodo.py` 会把下列规则变成实际断言。

## 1. 两类 Bot 的资产归属

| 资产 | 归属 | 允许的操作 | 打包位置 |
|---|---|---|---|
| Tutor 系统提示词 | Tutor Bot（独立配置） | `TEACH_TURN`、`CODE_FEEDBACK` | `platform/knodo/tutor/v1/` |
| 课堂知识包 | Tutor 可见（Teacher 共享） | 只读教学资料 | `platform/knodo/bundles/classroom/` → `bundles-classroom.zip` |
| Designer 系统提示词 | Designer Bot（独立配置） | `QUIZ_DRAFT`、`LESSON_PACKAGE_DRAFT` | `platform/knodo/designer/v1/` |
| 三份 Skill | 按角色分别绑定 | 见下 | `platform/knodo/skills/<name>/` → `skill-<name>.zip` |
| Designer 私有边界 | 服务端私有 | 永不随课堂包发布 | `platform/knodo/bundles/designer-private/`（`shipped_as_zip=false`） |

Skill 名称与编号固定，不合并、不重编号：
`k12-teaching-core`（Tutor）、`k12-assessment-author`（Designer）、`k12-content-author`（Designer）。

## 2. 绝不进入 Tutor 包 / 学生可见面的内容

`FORBIDDEN_KEYS`（打包器逐键扫描）：`answer`、`correct_answer`、`correct_option`、`solution`、
`reference_solution`、`hidden_test(s)`、`expected_output`、`reviewer`、`review_comment`、
`student_id`、`user_id`、`email`、`phone`、`password`、`token`、`pat`。

补充边界（写在 `bundles/designer-private/BOUNDARY.md`）：
- 标准答案与正确选项 key、解析全文、三级提示全文、隐藏测试与参考解；
- 真实学生身份/联系方式/学校、完整学生会话记录、聚合误区以外的个体数据。

分离结果登记在 `platform/knodo/bundles/manifest.json` 的 `separation` 字段
（`tutor_visible_count` / `designer_private_count` / `answers_in_tutor_bundle=false`）。

## 3. QA16 落点（题稿：答案只进服务端）

可在本卡运行的断言（`python3 scripts/package-knodo.py verify`）：

1. `designer/v1/examples/quiz-draft.sample.json` 与冻结契约示例
   `contracts/examples/quiz-draft.json` **逐字节一致**（题量/题型/来源等约束由冻结契约与
   `contracts/test_contracts.py` 的 38 项用例负责，打包器不另立一套口径）；
2. 每题必须带私有答案字段 `correct_answer`；单选答案必须是选项之一，选项 key 不重复；
3. 学生可见投影（`stem`/`options`/`hints`/`type`/`objective_id`/`source_refs`）不得携带
   `correct_answer` 或 `explanation` 键，也不得包含解析文本。

本卡**不**实现题稿服务端流转本身（属 T07/T12 等业务卡）；本卡只保证素材与样例满足该边界。

## 4. QA35 落点（真实 Knodo 目标与执行证据）

- 现状：**NOT_RUN / NOT_DEPLOYED**。没有平台执行证据，`deployment-manifest.json` 中
  `bot_id`/`workspace_id`/`deployed_config_hash` 全部为 `null`，`deployment_verified=false`。
- 本卡不做任何 Knodo 调用；本地打包、ZIP 校验、样例校验**不得**表述为"Skill 已在线加载"
  或"教学效果已验证"。
- 未来拿到授权后，QA35 要求的证据是：平台侧真实目标 Bot/Skill 标识 + 与本地 run 的关联标识，
  回填到团队登记（见 `DEPLOYMENT_GUIDE.md` 第 1 节第 8 步），而不是凭回复自称。

## 5. 复算方式

```bash
python3 scripts/package-knodo.py verify   # 安全 ZIP、SHA256、schema 字节一致、答案分离、部署状态
python3 scripts/package-knodo.py scan     # 全包扫描：无密钥/无绝对路径
python3 scripts/package-knodo.py selftest # 反例：篡改/越界/绝对路径/注入密钥/改 schema
```
