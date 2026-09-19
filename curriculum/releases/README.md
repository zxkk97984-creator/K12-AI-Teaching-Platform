# curriculum/releases —— 修订镜像（非学生可见）

导入成功后，唯一导入器会把每个修订写成本目录下的不可变快照：

```
curriculum/releases/<release_key>/<course_slug>/<chapter_slug>-r<revision>.json
```

- 快照是数据库修订的**镜像**，数据库才是权威；文件写失败记为 `mirror_pending`，重跑导入即可补齐。
- 快照内含 `content_hash`，可与数据库行比对；同一路径内容不同时不会覆盖，而是保持不变。
- 本目录**不是**学生可见目录：这里可以包含未审校、未发布的草稿。学生可见快照只出现在
  `curriculum/published/`，并且必须先是 `HUMAN_APPROVED` + `PUBLISHED` + 非夹具。
