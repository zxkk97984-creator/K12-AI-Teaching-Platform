# T00 源码与现场审计

核查时间：2026-09-18（Asia/Shanghai）  
目标根：`/home/zxk/Projects/K12`  
状态：只读审计完成；旧仓库未运行、未修改。

## 1. 目标目录保护

- `pwd` 与 `realpath` 均为 `/home/zxk/Projects/K12`，不是符号链接。
- T00 开始时除 `.rebuild-kit` 外，曾观察到空 `.git`、`.agents`、`.codex` 目录；`git status` 对空 `.git` 报 `fatal: not a git repository`。
- T00 写入前复核时，上述三个空目录已不在现场；执行 Agent 没有对它们执行删除、移动、初始化或写入。该环境变化无法由本 Agent 恢复；为避免伪造状态，未重新创建它们。
- `.rebuild-kit` 原样保留；执行包 `validate_kit.py` 与 `CHECKSUMS.sha256` 均通过。
- 根目录 T00 写入前没有 `.env`；本次没有创建、读取或覆盖 `.env`。
- 机器快照见 `source_roots.json`。未跟踪文件只登记路径、大小和 SHA-256/树摘要，不复制旧仓库内容。

## 2. 旧仓库基线

| 仓库 | realpath | branch | HEAD | tree | tracked dirty | untracked |
|---|---|---|---|---:|---:|---:|
| K12-Learning-platform | `/home/zxk/Projects/K12-Learning-platform` | `master` | `696364ff54c99f711e1cddd7364c9ac4d5282943` | `9934960af86236f3f13a8f1040d6d3fcebfdff3b` | 0 | 5 |
| CareerMate | `/home/zxk/Projects/CareerMate` | `master` | `724c00f943f277fa75f29dcc47bdf8e93e201eda` | `cb75941aa8ee0ee890178ab74c0730f5a8d5c146` | 0 | 4 |

两仓库均与 `origin/master` 为 `0/0`。用户未跟踪资产包括 K12 的 `.playwright-mcp/`、`backend/空`、`docs/handoff/`、赛题 Word、深度交接 Prompt，以及 CareerMate 的三份 MCP 文档和架构图目录；逐项摘要记录在 `source_roots.json`，不读取 `.env` 明文。

## 3. 实际读取的 K12 代码

| 文件 | SHA-256 | 已核对的实现点 |
|---|---|---|
| `backend/app/modules/content/service.py` | `f2e6244a4f4a10822cd86aea427f341c78f6505fa7ca2eec6fd93ccf0cedf0ae` | `ContentService`、分页与缓存 |
| `backend/app/modules/content/schemas.py` | `df9a084c649b2034beea14d03f3289cfd92fc971678174a0e8311491f30767ec` | 内容 DTO 边界 |
| `backend/app/modules/content/router.py` | `305c7e500fa4f96b25faf0b2c94777fd1d495add526f9036199fba76ce07a555` | 内容读取入口 |
| `backend/app/modules/conversation/teacher_context.py` | `b2745b597d01c0b66626e278cf801cbd6acea0ef6b9be499dc0520a55609d686` | `build_teacher_context`、答案/错题上下文 |
| `backend/app/modules/conversation/service.py` | `3d581dd3eea090c200b72b34cc79e10ee27e47d7ff96a12eca483e1389e79d76` | 会话锁、消息游标、SSE 帧与服务边界 |
| `backend/app/modules/quiz/quiz_bank.py` | `342e22e3109910d46f20c25b3a51aa2c860c20f2385a76e8fe4a458edb6787b5` | 题库筛选、审校题选择 |
| `backend/app/modules/quiz/service.py` | `b16b447b234458389d4fe5520c6ce3c362d8065914a1468d243dbeceec52be07` | `QuizService`、答题会话 DTO |
| `backend/app/modules/quiz/chapter_source.py` | `a6095237da5b10c790249c3d5a2dcb7331400e014742801c6cece9dd8c435160` | 章节来源与模板题生成 |
| `backend/app/modules/memory/service.py` | `347c8281b0eb79f40eeca958d55306d5c46bfa78fc3441f17b16cc01a81a7fb1` | 证据、画像、Episode DTO |
| `backend/app/modules/memory/pipeline.py` | `69288757c3316eb765773795fcddb883d926efff29423f350e38634df8df2004` | 学习事件到记忆候选/Episode |
| `backend/app/modules/recommendation/service.py` | `b1155a56cb53ed2cec47bbdb8e3e2b112e5596436c992714ca0a6051d7eec998` | 候选依据、进度/兴趣/答题信号 |
| `backend/app/modules/learning/service.py` | `3be9f182b12168695fbadfea1ba15420c11a97d21a3a4bd588664f602960f918` | 学习事件游标与持久化 |
| `backend/app/modules/codelab/scoring.py` | `be59ded4001b252af08290207aae25b7e1e6c9c34715539606e84f504e23ab37` | 确定性分数、矛盾提示、钳制 |
| `backend/app/modules/codelab/sandbox.py` | `0d629f291208086e6b432505af04f1d26061f4aa16acb05d59290bff21d97d3a` | Docker 参数、输出截断、清理与 runner |
| `backend/app/modules/codelab/execution.py` | `7ddb605276b40818f77dc33347461f698d18e72d4f0449653ffcd2e803f50cdb` | 确定性组评分 |
| `backend/data/library/manifest.json` | `68f561bd7c587f80ff91e563139b21e0a219c48a0ee97b02129d0dde89c27353` | 25 本课程及年级范围 |
| `frontend/src/entities/student/types.ts` | `2cc229994d98abf8068d48f5612ab331edf7d04e84181dbbe2077d24dd478e74` | 旧三档 Stage 与年级派生 |

旧实现确认：沙箱按名称前缀清理，未看到任务租约；`capture_output` 后截断不等于执行中内存限额。以上是静态审计事实，不是本次运行结论。

## 4. 实际读取的 CareerMate 代码

| 文件 | SHA-256 | 已核对的模式 |
|---|---|---|
| `src/lib/tbox/client.ts` | `2e83c1d080ca063bad7612e87208bd9f0ea30dc545912600de996c23d7757390` | 百宝箱客户端、取消与响应消费；协议不可移植到 Knodo |
| `src/lib/agentic-v2/candidate-ingestion.ts` | `442316404b54d995b8fad739b6e6365138dceb06f44fe7875254124ebb48d923` | 待确认候选与业务投影分离 |
| `src/lib/agentic-v2/artifact-stream-filter.ts` | `3bcfb0346091fb66c3aa85933f2b386272c313bbecf1bbde252a3b636cfd6f3b` | 跨 chunk 信封过滤 |
| `src/lib/agentic-v2/platform-contracts.ts` | `6e29250a17848b1759495a785d1d9c6e0605bd9ae4bdca0d92927370a01ed5af` | task context 与 evidence bundle 分层 |
| `src/lib/agent-context-auth.ts` | `dda96c1c54efe7e9b0b7fd37c52f220529da36492d3612527cb5d58b9120b81f` | sub/sid/scopes/TTL/JTI 短期上下文令牌 |
| `src/lib/chat/context-builder.ts` | `ed6e79f45893a86da92b8258f21f0b72ab77b3922e3a65fde4b3fdf103b744f4` | 最小上下文和预算裁剪 |
| `src/lib/chat/stream-service.ts` | `becd83aaf993fe16f632eb1575d89235b6cf6552fdfd950a0dbb27a930920525` | 流式处理、候选操作与最终化边界 |
| `src/lib/chat/agentic-v2-context.ts` | `4d762adf5ebb5e4e46d8f993f5609e2835e5c2f1ac8599c8bae0b9859d0630d9` | V2 上下文快照 |
| `docs/architecture.md` | `18fbc69bc873379862e555760d423c7c8ff2a2599c86c75119c148cd4b5e7de7` | 平台/业务/证据分层说明 |

## 5. 未读取和未验证

- 未逐行审计两个完整仓库，未运行旧项目测试、seed、bootstrap、服务或数据库迁移。
- 未读取任何 `.env` 内容、GitHub PAT、Cookie 或平台 Key。
- 历史交接报告中的通过数量没有转写成本次通过。
- Knodo 真实登录后请求/响应、身份隔离、模型 ID、预算和低龄适用性仍待 T02/平台负责人核实。
- 旧沙箱的完整判题后半段未在本次读取范围中；新 runner 必须独立重建和验证。
