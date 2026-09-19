# curriculum/source —— 可编辑课程源（不是发布目录）

这里的文件是**课程源**：经转换、带来源与许可登记，但**尚未**经过真实人工审校。
学生端可见性由 PostgreSQL 中的 `content_chapter_reviews` 状态决定，不由目录结构决定。

## 目录约定

```
curriculum/source/
  legacy/<release>/          # 从只读旧仓库转换来的待审稿（EXISTING_REUSED_PENDING_REVIEW）
  synthetic/<release>/       # 合成夹具（is_test_fixture=true），只允许 dev/test 加载
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
3. **未审不发布**：导入只会创建 `UNREVIEWED/DRAFT`。技术校验最多 `AUTO_VALIDATED`；只有真实审校者可以
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
