# curriculum/published —— 学生可见快照（当前为空）

只有满足全部条件的修订才允许写入本目录：

1. `review_status = HUMAN_APPROVED`（真实审校者、有时间与身份记录）；
2. `publication_status = PUBLISHED`；
3. 非 `is_test_fixture`，且 `license_code != SYNTHETIC-FIXTURE`。

写入由 `app.modules.content.importer.materialize_published` 完成；对 `DRAFT/WITHDRAWN` 修订会直接抛错，
不会产生“看起来已发布”的空文件。

截至 T06：四个学段的示范章都没有真实人工审校记录（`G_HUMAN_CONTENT_REVIEW` 仍为 BLOCKED），
因此本目录刻意为空。合成夹具只用于开发/测试，且永远不会进入这里。
