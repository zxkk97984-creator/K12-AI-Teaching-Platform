# 课程迁移对账清单（T06）

日期：2026-09-18
旧仓库（只读）：`/home/zxk/Projects/K12-Learning-platform`，HEAD `696364ff54c99f711e1cddd7364c9ac4d5282943`
新项目包：`curriculum/source/legacy/k12-library-696364f/`
转换器：`backend/app/modules/content/legacy.py`（`legacy-library-v1 -> k12.content.chapter-blocks.v1`）

## 1. 已转换资产（2 项）

| 章节 | 源文件 | 源 sha256 | 新包文件 | revision | 学段/年级 | 审校状态 | 学生可见 |
|---|---|---|---|---|---:|---|---|
| `python-first-steps/ch05` 小项目：猜数字游戏 | `backend/data/library/books/python-first-steps/ch05.md` | `5714a715aab3318f6b7e8edca20c5234f0bd4d37878848fc5f91255e4d4f47bc` | `courses/python-first-steps/chapters/ch05.json` | 1 | JUNIOR 7–9 | `UNREVIEWED` / `DRAFT` | 否 |
| `algorithm-everyday/ch03` 查找的智慧：二分的力量 | `backend/data/library/books/algorithm-everyday/ch03.md` | `4c755b84214130e8b896ccfb147a53b93a6f86a36a75b1d53aa4bc156c3770ab` | `courses/algorithm-everyday/chapters/ch03.json` | 1 | SENIOR 10–12 | `UNREVIEWED` / `DRAFT` | 否 |

- 内容块数：ch05 = 21、ch03 = 19；`T/P/KC/CALL/FIG/S` 全部转换，`@kp` 标记（ch05: `condition-if, random-number`；ch03: `binary-search`）记录在章节文件并由导入器校验为已声明知识点。
- 章节级 `content_hash` 与 release `manifest_hash` 见 `curriculum/releases/legacy-k12-696364f-pending-review/`。
- 两个章节在数据库中的状态是 `UNREVIEWED/DRAFT`；本轮**没有**、也不允许由 Agent 生成人工审校记录。
- 结论：技术转换完成 ≠ 四档示范课完成审校。`G_HUMAN_CONTENT_REVIEW` 保持 BLOCKED。

## 2. 未迁移资产（23 本、0 个图资源）

- 旧 `manifest.json` 共登记 25 本书；本轮只迁移 T01 冻结表选中的 2 章，其余 23 本保持未迁移（未登记来源/许可与审校计划时不转换）。
- `PRIMARY_LOWER`、`PRIMARY_UPPER` 两档在旧仓库中没有适龄内容（旧课最低从三年级开始），T01 已登记为 `NEW_SOURCE_REQUIRED`；本轮**没有**把三年级内容改标签冒充一、二年级。
- 旧仓库只有 3 个 SVG（`ai-not-magic-junior/assets/two-smart-lines.svg`、`ai-primary-fun/assets/three-key-ideas.svg`、`ml-how-machines-learn/assets/learning-paradigms.svg`），都不属于本次选中的两章，因此**0 个图资源被复制**。
- 选中章节里的 `FIG:` 是文字描述（`alt` + `caption`），没有真实图片文件；本轮没有、也不得声称已有可用插图。

## 3. 未确认授权清单

| 对象 | 现状 | 处理 |
|---|---|---|
| 25 本旧书 | 旧 `manifest.json` 的 books 条目**没有** license 字段；只有各 `book.json` 自述 `license: CC-BY`、`copyright_status: 原创`、`author: null` | 记为该来源自述，不是已核实授权；发布前需真实授权复核 |
| 本次 2 章 | 继承上述 CC-BY 自述，写入 `content_chapter_revisions.license_code` 与 `license_notes` | 允许入库为草稿；`PUBLISHED` 前需人工复核授权 |
| 合成夹具 | 项目自造文本（`SYNTHETIC-FIXTURE`） | 数据库触发器禁止其成为 `PUBLISHED` |
| 未来插图/音视频 | 尚无登记 | 必须逐项登记来源与许可后才能关联章节 |

## 4. 格式映射与已知差异

| 旧格式 | 新格式 | 说明 |
|---|---|---|
| `T/P/KC/CALL/FIG` | `BlockType.TITLE/PARAGRAPH/KNOWLEDGE_CARD/CALLOUT/FIGURE` | 一一对应 |
| `FIG` 的 `aria_label` / `asset` | `alt` / `src` | 字段改名；`src` 只允许 `assets/<file>` 且必须真实存在 |
| `S: 中文锚点名` | `SECTION(key="section-N", text="锚点名")` | 旧锚点没有 ASCII slug，转换器按出现顺序生成稳定 key，标签保留在 `text` |
| `@kp=slug`（块级） | 章节级 `knowledge_points` 关系 | R1 schema 暂无块级知识点归属；转换器记录全部观察到的标记并要求它们在课程文件中已声明，否则报错 |
| `meta.estimated_minutes/summary` | 章节文件 `legacy_meta` | 保留在源文件里；T06 数据库 schema 未建对应列，后续教学节奏任务如需要再迁移 |
| 旧导入器固定 `status=PUBLISHED` | `UNREVIEWED + DRAFT` | 明确不复用旧行为 |

## 5. 复现命令

```bash
# 转换并校验（只读旧仓库）
cd backend
python -m app.scripts.import_content convert \
  --release-dir ../curriculum/source/legacy/k12-library-696364f \
  --legacy-root /home/zxk/Projects/K12-Learning-platform --check

# dry-run（不写库/不写盘）与幂等导入
python -m app.scripts.import_content import --release-dir ../curriculum/source/legacy/k12-library-696364f
python -m app.scripts.import_content import --release-dir ../curriculum/source/legacy/k12-library-696364f --apply
```
