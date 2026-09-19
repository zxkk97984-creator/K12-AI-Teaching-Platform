---
name: k12-assessment-author
description: 为指定K12章节生成限定题型与数量的题目草稿，答案私有，科学性和人工审校分离。
---


# 使用时机

Designer收到QUIZ_DRAFT。读references/designer-request.schema.json与quiz-draft.schema.json，按请求quiz_spec执行。

# 操作顺序

1. 核对本章版本、source资料、目标与学段；题目不能跨出给定课程依据。
2. 生成准确数量及允许类型，SINGLE_CHOICE/TRUE_FALSE/ORDERING，不追加未支持题型。
3. 选项/排序项key唯一；单选答案在options中；排序答案精确覆盖所有items且不重复。
4. 每题一个objective_id，源ID/版本/定位来自knowledge_context；不能编造source。
5. 三级提示逐渐增加信息；解析说明原因。标准答案只在私有题稿返回，不进入学生自由聊。
6. 输出一个严格JSON，不含人工审核字段。缺依据/歧义放warnings并标草稿，不自称已审通过。

# 禁止

不读取学生私聊/成绩库、不运行代码、不发明题库数据库ID、不写APPROVED或reviewer、不返回可执行脚本。结构正确不保证科学正确，需要真实人工审校和实测。
