# 课堂知识包（classroom bundle）

本目录是 Tutor 可读取的**受控课堂知识包**。构建者是 `scripts/package-knodo.py build-bundles`，
数据来源是 `curriculum/releases/` 下的不可变修订镜像。

规则：

1. 只包含 Teacher 可见内容：章节标题、学习目标、知识点说明、正文块与来源登记。
2. **不包含**标准答案、参考解、隐藏测试、未审题库、原始学生档案或任何密钥。
3. 当前包是**测试内容包**（`bundle_kind=TEST_FIXTURE_BUNDLE`），界面与说明必须保持
   “测试内容，未作人工教学审校”的标识，不得用于真实学生。
4. 正式知识包要求课程修订处于 `HUMAN_APPROVED + PUBLISHED`；文件系统打包器不产出正式包，
   正式包由应用在 T10/T12 绑定真实章节 ID 后导出。
