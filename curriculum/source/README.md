# curriculum/source —— 可编辑课程源（不是发布目录）

这里的文件是**课程源**：经转换、带来源与许可登记，但**尚未**经过真实人工审校。
学生端可见性由 PostgreSQL 中的 `content_chapter_reviews` 状态决定，不由目录结构决定。

## 目录约定

```
curriculum/source/
  legacy/<release>/          # 从只读旧仓库转换来的待审稿（EXISTING_REUSED_PENDING_REVIEW）
  synthetic/<release>/       # 合成夹具（is_test_fixture=true），只允许 dev/test 加载
  imported/<release>/        # 本地导入讲义、原文哈希档案与归一化 Markdown
```

每个 release 目录包含：

| 文件 | 作用 | 作者 |
|---|---|---|
| `release.json` | release_key、来源类型、是否夹具、授权、课程清单 | 人工编写 |
| `courses/<slug>/course.json` | 课程元数据、知识点目录、章节登记（学段/年级/目标/来源/hash/许可） | 人工编写 |
| `courses/<slug>/chapters/<ch>.json` | 章节正文块（`k12.content.chapter-blocks.v1`） | 旧课由转换器生成，合成内容人工编写 |

## 规则

1. **唯一入口**：正文只能通过 `python -m app.scripts.import_content` 进入数据库；不绕过管道直接写库。
2. **不原地覆盖**：正文变化＝新 `revision`。同 `(chapter, revision)` 不同 `content_hash` 是硬错误。
3. **正式发布**：导入只会创建 `UNREVIEWED/DRAFT`。技术校验最多 `AUTO_VALIDATED`；只有真实审校者可以
   `HUMAN_APPROVED`，只有人工通过且非夹具的修订可以 `PUBLISHED`。
4. **未知即失败**：未知标记、未知授权、越界路径、缺失图资源、重复 slug/关联都直接失败，不静默丢弃。
5. **来源可追溯**：每个章节登记 `source_commit` / `source_path` / `original_sha256` / 转换版本。

## 命令

```bash
# 1) 从只读旧仓库转换正文（只写 curriculum/source）
python -m app.scripts.import_content convert \
    --course-file ../curriculum/source/legacy/k12-library-696364f/courses/python-first-steps/course.json \
    --legacy-root /home/zxk/Projects/K12-Learning-platform

# 2) 校验转换结果是否与磁盘一致（不写入）
python -m app.scripts.import_content convert \
    --release-dir ../curriculum/source/legacy/k12-library-696364f \
    --legacy-root /home/zxk/Projects/K12-Learning-platform --check

# 3) dry-run：完整校验 + 计划，不写数据库、不写磁盘
python -m app.scripts.import_content import \
    --release-dir ../curriculum/source/legacy/k12-library-696364f

# 4) 实际导入（幂等），并刷新 curriculum/releases 镜像
python -m app.scripts.import_content import \
    --release-dir ../curriculum/source/legacy/k12-library-696364f --apply
```

`convert` 仅在旧仓库 commit `696364ff54c99f711e1cddd7364c9ac4d5282943` 上验证过；转换器不联网、不改旧仓库。

## 本地 Markdown 讲义

`imported/computing-ai-md-v1/` 包含 20 门课程及四学段章节。`normalized/` 保存整理后的正文，
`sources/` 按原文件哈希保留来源，`inventory.json` 对照原文件、哈希与档案。
转换配置在 `app.modules.content.markdown_import` 中；小学低段只开放预定基础章节，公共正文源只维护一份。

使用 `python -m app.scripts.import_content convert-md --source-dir <原文目录> --output-dir <课程包目录>` 重新转换，
再用现有 `import --release-dir ...` 先校验、后加 `--apply` 导入。正文更新产生新 revision 与新批次 key，重复转换和导入不会重复创建。
无 Git 来源的 NEW_SOURCE 用原文件哈希追溯；没有明确许可时保留 UNKNOWN。
`local_demo_visible=true` 只扩展本地比赛模式的可见性，撤回始终优先，正式模式继续使用正式发布条件。
