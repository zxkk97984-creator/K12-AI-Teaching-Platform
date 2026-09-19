---
name: k12-content-author
description: 根据已授权章节生成可审核课程包规格，区分真实产物与待制作资源，不自动发布。
---


# 使用时机

Designer收到LESSON_PACKAGE_DRAFT。读references/designer-request.schema.json与lesson-package-draft.schema.json。

# 操作顺序

1. 核对章节版本/适用学段/学习目标与来源。
2. 给出讲稿和短活动序列，READ/RESOURCE/ANIMATION/QUIZ/CODE/REFLECT只用必要项。
3. 动画限定ADJACENT_SORT/BINARY_SEARCH且必须在请求允许集合；步骤由本地可信算法生成，模型给可校验参数和解说。
4. 已存在资源ID只能选allowed_resource_ids，否则null；待制作Word/PPT/视频/图片放asset_requests并为NOT_PROVIDED。
5. 输出严格JSON与准确来源，不把规格当成渲染视频，不把生成草稿当发布内容。
6. 没有工具/文件/授权时说明待补，不虚构文件路径、专家审核、版权或外部API。

本Skill不携带脚本/通用shell权限。若后续启用实际文件制作工具，需要另行授权、文件获取验证和内容审校；不能自动修改学生状态或课程发布版本。
