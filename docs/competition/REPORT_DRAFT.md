# 霜铃 K12 × Knodo 参赛报告草稿（证据绑定版）

状态：草稿 / 合成数据参赛原型；不是已依托 Knodo 上线的真实 K12 产品。

## 1. 项目定位

霜铃把“目标—讲解—操作/练习—反馈—下一步”组织成一节可恢复的学习流程。FastAPI
保存本地权威身份、课程 revision、学习事件、确定性判分和 CodeLab run；Tutor/Designer
只负责经过契约校验的教学建议或结构化草稿。学生浏览器不持有平台 PAT，不决定 owner、
章节 revision、远端会话或成绩。

## 2. 架构与安全边界

React/TypeScript/Vite → FastAPI → PostgreSQL；资源文件进入路径受限的本地存储；后台
worker 通过租约消费教学/教研任务；CodeLab 由独立 loopback runner 启动 digest 固定、
无网络、非 root、只读、限 CPU/内存/PID/时间/输出的 Docker 容器。Docker socket 不挂给
API。系统架构见 plans/02_架构与数据边界.md，证据见 T24/T29 报告。

## 3. AI 策略与本地业务事实

- Tutor 操作：TEACH_TURN、CODE_FEEDBACK；Designer 操作：QUIZ_DRAFT、LESSON_PACKAGE_DRAFT。
- 本地先构建最小章节/学段/证据快照，再校验返回 schema、source refs、action allowlist 和
  owner/revision；没有来源时明确不足，不伪造引用。
- Quiz/CodeLab 的确定性结果不由模型改写。CodeLab AI feedback 不能添加分数；
  deterministic score/status 与 AI feedback 状态分开。
- fixture 仅在开发/测试 profile 使用，界面标明合成/未审校；production 拒绝 fixture gateway。

真实 Knodo 限定 Bot Chat wire 已通过 T11/T13/T31 合成验证；平台未返回可信 usage/成本及 Skill/bundle 挂载版本，不能写成正式教学质量或“换 BaseURL 即可接通”。

## 4. 多模态与五类 R1 功能

| 能力 | 本地证据 | 当前宣称 |
| --- | --- | --- |
| 教学对话/主动课堂 | T13 真实浏览器竖切；T31 16-case live；T14/T17/T30 本地链 | 合成数据真实 Knodo 已验证；真人教学质量未审 |
| Word/PPT/video 资源 | T20 真实合成文件上传、下载、播放、撤回；T30 截图 | 本地资源闭环通过；正式内容/人审未通过 |
| 确定性动画 | T21 后端边界测试；T30 synthetic fixture browser 1 passed、390/1280 截图 | 注册/参数/安全边界和本地控制器通过；正式内容仍需人审 senior chapter |
| 在线编程 | T23–T26、T30 CodeLab、T24 Docker 5 tests | 本地真实 Docker/可信判分通过；AI feedback 为 fixture |
| 趣味练习 | T15–T18、T30 practice browser | 本地题目快照/提示/判分/证据通过；教学效果未验证 |

图文绘本 O01 未纳入 R1 完成宣称。

## 5. 四档样板与来源

四档策略已冻结，但四档正式示范课没有全部完成人工审校：

- PRIMARY_LOWER：开发合成 fixture 可演示结构；正式低龄样章待真实内容审校。
- PRIMARY_UPPER：规划中“比较与排序”方向；正式内容待生产/审校。
- JUNIOR：legacy python-first-steps/ch05 revision 1 已按来源导入，发布/人审状态仍按数据库事实。
- SENIOR：legacy algorithm-everyday/ch03 revision 1 已按来源导入；正式动画内容仍待人审；T30 控制器使用 T06 合成 fixture 完成本地复核。

不把 stage label、fixture 通过或模型输出当成人工审校/适龄证明。

## 6. 评测与未验证

T31 四档 16-case synthetic eval 已在真实 Knodo 执行：13 个有效冻结 Schema 响应、2 个
`RESPONSE_SCHEMA_MISMATCH`、1 个超时；有效响应率 81.25%，median 88.134s，p95/max 120.104s。
13 个成功输出全部通过来源/action/秘密自动边界；上游 token 均报告 0，按不可用处理，不估算费用。
人工科学性、适龄、引用和教学可行动性 rubric 尚未填写。没有真实学生研究，不声称学习效率或成绩提升。

## 7. 证据索引

- T26 CodeLab：docs/acceptance/T26.md
- T28 安全与隐私：docs/acceptance/T28.md
- T29 干净部署：docs/acceptance/T29.md
- T30 全链路回归：docs/acceptance/T30.md
- T31 真实评测：docs/acceptance/T31.md、docs/acceptance/T31-live-summary.json
- Knodo 门禁登记：docs/integrations/knodo/GATE_REGISTER.md

报告可交付状态：本地 + 真实 Knodo 合成原型；等待平台完整隔离、真实人审和用户最终验收。
