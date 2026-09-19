# Knodo配置、发布与真实接入

这是用户/平台配置负责人和代码Agent的协作步骤。平台菜单依据[P2–P6]；本项目命名、JSON协议、操作路由为自定义。未登录租户、未创建Bot、未做真实调用，不能把下面“应该填写”写成“已经部署”。

## 1. 首先记录五项门禁

- `G_API_CONTRACT`：已获取登录后Bot API完整请求/响应、续聊/流/错误定义并保存脱敏来源。
- `G_LIVE_BUDGET`：用户授权的调用目的、最大请求数、可确认的积分/费用范围；缺计价依据只限制次数不编人民币。
- `G_AGENT_ISOLATION`：平台身份、历史工具、共享文件、记忆和执行权限边界已有可执行约束，不能仅凭prompt。
- `G_K12_TERMS`：真实学生尤其16岁以下适用安排已由平台/赛方确认。团队合成测试不伪称真实学生试用。
- `G_HUMAN_CONTENT_REVIEW`：示范课和公开资源有人审校并签署实际记录，不由AI自签。

API文档缺失只阻塞真实wire实现/验收，不阻塞前端、数据库、离线契约、动画和测试工作。安全与适用范围未确认则不得开放真实学生数据接入。

## 2. 工作空间与两类Bot

先创建两个私有、团队限定空间：`sl-classroom-poc`与`sl-design-studio`。这两个名字是建议，可自行命名并登记ID。

Tutor：`霜铃·课堂教师`，处理`TEACH_TURN`和`CODE_FEEDBACK`。系统提示词源`platform/prompts/TUTOR_SYSTEM.md`，绑定`k12-teaching-core` Skill。只放审校后的课堂内容/规范，不放答案/隐藏测试，不绑定研发电脑目录。

Designer：`霜铃·教研助手`，处理`QUIZ_DRAFT`与`LESSON_PACKAGE_DRAFT`。系统提示词源`platform/prompts/DESIGNER_SYSTEM.md`，绑定`k12-assessment-author`和`k12-content-author`。产生结构化草稿，不直接写本地正式数据；题目生成会话绝不作为学生续聊会话。

操作顺序：工作空间设置→AI成员/AI助手→新建（若租户界面提供能力中心→助手入口，也可使用；公开页面不同抓取版本菜单存在差异，以实际UI为准）→填写名称/描述/系统提示词→限定可见范围→加入对应空间→绑定Skill→保存→新建对话验证。不要仅写workspace guideline而漏掉Bot自身系统提示词，也不要假定二者自动合并。[P2]

## 3. 运行时和模型

进入空间设置→AI配置→修改模型→先选择AgentOS，再从其实际可用列表选模型。记录运行时、实际model ID、组织渠道与配置hash，不只抄显示名称。[P4]

用户的`DeepSeek-v4.1flash`目前作为执行本重建任务的模型描述，不自动等于Knodo运行教师的model ID。Knodo的公开模型配置页仅证明有DeepSeek系列，并没有在本次读取中核实比赛账号可用的该具体型号。可选择兼容的实际模型；不能凭空填写名称或编造它支持工具/视觉/JSON。

补充核实：[D1]的2026-09-10官方发布记录说明，DeepSeek自己的API使用`deepseek-flash`调用V4.1-Flash。这不意味着Knodo采用同一模型标识，也不授权把教师主链路改为直连DeepSeek。

插件文档的兼容矩阵比“最佳实践中所有组件通用”的笼统话更具体：例如Codex能复用Skill/MCP，但不会首期自动注册Claude子Agent或Hook。[P3] 因此MVP使用Bot+Skill，不依赖`agents/`自动协作、Claude Hook或平台可视化工作流与百宝箱一模一样。

## 4. Skill发布

`platform/skills/<name>/SKILL.md`有name/description frontmatter。将每个目录单独打ZIP，在插件管理的上传Skill入口导入，确认所需Bot/工作空间绑定。

本包附三份Skill ZIP，可作为初始配置测试，不是已验收在线能力。先草稿试用，确认后发布只读版本；按平台文档新开会话核对挂载快照。仓库内保存内容hash与测试样例。平台内临时修改必须同步回源码或重新打包，禁止“平台最新版、仓库旧版”不知差异。[P3]

## 5. 知识发布与答案分离

由本地课程发布版本导出`manifest.json`、每章正文、目标/先备知识、资源目录；每项标识source_id/revision/sha256/stage。初始只选一课验证，后续每档一课。

知识包不含：`.env`、用户库、聊天备份、参考解、隐藏测试、未审核题库、交接审计全文或Agent研发指令。发布后在Bot里问只能从该包回答的校验问题，核对确实读到正确版本和来源，不以“上传成功”替代实际读取。

共享知识库文档有具体的可见性与可添加列表限制[P9]，不要写死“建只读库就一定能给任意空间挂载”。初版采用显式版本快照；真正共用挂载在租户里验证后才纳入自动化。工作空间文件可以被Agent访问不等于已证实向量RAG/强学段过滤。

Tutor、Designer不共用学生聊天存储。自动记忆先关闭或隔离，清楚记录关闭是否影响已有记录；没有删除证据就不要声称平台历史已清除。

## 6. 令牌

个人设置→API密钥→创建密钥→设置实际所需能力和有效期；后端通过`Authorization: Bearer <PAT>`调用平台`/api/v1/...`。[P5]

使用最小权限的专用测试身份，不默认用全组织管理员PAT。PAT沿用创建者业务权限，旧资源范围字段不构成按学生隔离。Site token用于站点访问者委托，组织模型API Key用于模型网关；三者不可混用。

本地环境变量只由用户填写，不在提交、浏览器、截图、测试fixture或聊天输出中暴露。公共.env.example留空值并描述用途；程序`knodo`模式缺配置时fail-closed。

## 7. 已知API与尚未知的wire协议

[P6]列出平台路径：

```text
POST /api/v1/bots/{botId}/chat/completions
POST /api/v1/workspaces/{workspaceId}/chat/submit
GET  /api/v1/workspaces/{workspaceId}/chat/conversations
```

第一条是本项目优先验证的Bot调用；不能只调模型网关冒充Bot。`/docs/api/simple-api`本次跳登录；所需请求字段、message roles、会话续用、可选workspace、响应结构、SSE、usage、取消、幂等和上传产物下载契约尚不完整。

仅已知认证/路径不能写出真实客户端。T02须补`contracts/knodo-wire-evidence.template.json`每个必需项，附官方文档或授权账户脱敏样例。缺失时接口实现保持`CONTRACT_UNVERIFIED`且不发网络，不猜`question/messages/input/user_id`。

下面仅是HTTP外壳，不是可直接成功的业务请求：

```bash
# KNODO_PAT由安全环境注入，勿把值粘进命令历史
curl --fail-with-body --no-buffer \
  -H "Authorization: Bearer $KNODO_PAT" \
  -H 'Content-Type: application/json' \
  -X POST "$KNODO_PLATFORM_BASE_URL/api/v1/bots/$KNODO_TUTOR_BOT_ID/chat/completions" \
  --data-binary @request-from-verified-official-contract.json
```

本包`teaching-request/response` JSON是应用内语义，不是官方HTTP body。只有mapper可以把语义输入变成经证实的wire字段。

## 8. Site、PAT与流式的区别

[P6]说明Site认证前缀不提供相关会话SSE/Bot `stream=true`，需要独立后端PAT调用再转发。另一方面站点HTTP服务代理能够透传自己的SSE，这两句话不矛盾，不能归纳成“Knodo不支持流式”或“Site全部API支持流式”。

本项目默认独立Web/API部署，后端PAT走平台Bot接口。初版完整结构化响应校验后下发；native text模式是否可用记录在部署清单，不把心跳或完整结果再分片作为真实首字优化。

## 9. 最小验证序列（每项实际执行才写通过）

1. 配置检查与一次无敏感信息的Bot调用；核对目标Bot而不只是200。
2. 课程校验问答，核对bundle source_id/revision；没有资料时承认缺失。
3. 两轮续聊，确认返回/传入会话ID语义；不自行假设全量history加conversation_id双投喂。
4. 两个合成学生各自输入不同无敏感标记，跨会话查询不得出现对方数据；另审查工具历史和共享文件权限。
5. 切换Bot版本/课程版本后远端绑定失效规则；旧响应不会写新lesson。
6. 非法JSON、缺引用、未知动作、超时、取消、401/403/429、网络中断；本地结果/成本状态准确。
7. Designer生成一份有答案的题稿，答案不会进入学生自由聊的可见内容或历史。
8. 记录request_id、Bot/workspace、配置hash、回复模式、实际用量来源、耗时、失败，不存PAT/cookie/完整私人正文。

## 10. 暂不接的能力

不接IM、不启用组织管理/通用shell/任意网页抓取作为学生工具、不自动发布站点、不调用用户的研发电脑执行、不通过可写共享目录更新成绩。

MCP是O02增强：公开接口契约、平台工具挂载和每请求授权都验证后，才暴露少数受约束读/候选操作。静态共享API Key+模型填写student_id不被接受；平台JAVIS_LOGIN_USER_ID也不直接等于本地学生。网关无可靠传递上下文授权的能力时，继续快照模式，不能把权限搬进prompt。
