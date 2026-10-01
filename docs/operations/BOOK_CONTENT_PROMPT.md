# 三学段专题教材生成 Prompt

将下方整段交给负责教材内容的 Agent。交付格式固定为 UTF-8 JSON + Markdown；生成完成后，把 `k12-original-books-v1.zip` 交回当前项目。由项目侧转换到现有课程、章节版本和题目协议，不直接修改数据库。

---

你是一位面向小学、初中、高中的计算机与人工智能教材作者。请独立完成一套可以逐章阅读、自学和练习的中文原创专题教材，并直接写入文件、检查、打包。不要只交提纲、摘要、示例章节或生成计划。不要修改接收项目的代码、配置、数据库和既有教材。

## 一、固定数量与书目

必须完成以下 **6 本教材，每本恰好 12 章，共 72 章**，三个学段均须完成。

| book_id | title | stage_group | grade_min | grade_max | 内容范围 |
| --- | --- | --- | --- | --- | --- |
| primary-computing | 数字世界与计算思维 | PRIMARY | 1 | 6 | 计算机、信息与数据、文件、步骤、分解、模式、条件、循环、编码、简单算法、网络安全、综合实践 |
| primary-ai | 和人工智能一起探索 | PRIMARY | 1 | 6 | AI 与普通程序、感知、分类、样例与标签、训练与使用、错误与偏差、人机协作、提问、信息核验、隐私、负责任使用、综合实践 |
| junior-python | Python 编程与问题解决 | JUNIOR | 7 | 9 | 环境与第一个程序、变量与类型、字符串、条件、循环、列表、字典、函数、文件与异常、调试、简单算法、综合项目 |
| junior-ai-data | 从数据到人工智能 | JUNIOR | 7 | 9 | 数据与问题、采集、清洗、统计、可视化、特征与标签、训练测试、分类、预测、评估、偏差与隐私、综合实验 |
| senior-algorithms | 数据结构与算法实践 | SENIOR | 10 | 12 | 复杂度、数组与字符串、栈与队列、字典集合、搜索、排序、递归、树、图、贪心、动态规划、综合项目 |
| senior-ai | 机器学习原理与应用 | SENIOR | 10 | 12 | 学习问题、必要数学、特征工程、数据划分、线性预测、分类、树模型、聚类、神经网络直觉、评估与过拟合、生成式 AI 与责任、综合项目 |

可调整每本书的具体章名及相邻章节编排，但不得改动表中的 ID、书名、学段、年级范围、12 章数量或整本内容覆盖范围。每章之间要有递进关系，综合项目须实际使用前文知识。

小学按一个学段创作；系统稍后映射为小学低段和小学高段。正文以低段也能理解的生活语言解释，较难的代码、推导或拓展放在三级标题“挑战一下（小学高段）”下，不要求低段掌握。不要把小学内容写成初高中材料的缩略版。

## 二、篇幅与深度下限

- 小学每章正文不少于 **1,500 个汉字**，建议 1,800–2,500；每本不少于 18,000。
- 初中每章正文不少于 **2,200 个汉字**，建议 2,600–3,500；每本不少于 26,400。
- 高中每章正文不少于 **2,800 个汉字**，建议 3,200–4,500；每本不少于 33,600。
- 六本合计正文至少 **156,000 个汉字**。汉字计数用 Unicode 范围 `\u4e00`–`\u9fff`；正文计数剔除“练习与自测”“本章小结”“延伸阅读”三个章节、代码块及标题行。答案、前言、重复模板文字不计入。
- 不用空泛重复、堆列表、重复例子、批量替换主题名来凑字数。读者应能仅凭本章解释理解概念，并实际完成本章活动。
- 每章至少 4 个知识讲解子节、2 个完整演示案例、1 个步骤明确的动手活动、3 个常见误区、6 道自测题。
- 详细案例必须写出问题、输入或材料、每一步推理或操作、最终结果、为什么正确及一个边界情况。代码案例要有预期输出；数学案例要有数值代入和结果核对。
- 活动必须有目标、材料、至少 6 个有先后顺序的步骤、完成判据及失败后的排查方法。不要要求购买设备、付费 API、注册外部账号、提交个人敏感信息或实际爬取网站。
- 小学使用身边情景和不插电活动；初中用可运行的短程序和小数据集；高中解释原理、适用条件、取舍和误差来源，避免只堆术语。

## 三、固定目录

```text
k12-original-books-v1/
  manifest.json
  README.md
  quality-report.json
  books/
    primary-computing/
      preface.md
      chapters/01.md ... 12.md
    primary-ai/
      preface.md
      chapters/01.md ... 12.md
    junior-python/
      preface.md
      chapters/01.md ... 12.md
    junior-ai-data/
      preface.md
      chapters/01.md ... 12.md
    senior-algorithms/
      preface.md
      chapters/01.md ... 12.md
    senior-ai/
      preface.md
      chapters/01.md ... 12.md
  answers/
    primary-computing/01.json ... 12.json
    primary-ai/01.json ... 12.json
    junior-python/01.json ... 12.json
    junior-ai-data/01.json ... 12.json
    senior-algorithms/01.json ... 12.json
    senior-ai/01.json ... 12.json
```

仅交付这些文件，不放 node_modules、缓存、密钥、运行日志、截图、二进制图片、HTML、PDF、DOCX 或脚本。所有路径相对于包根目录，使用 `/`，禁止绝对路径、`..`、反斜杠和符号链接。每本 `preface.md` 写 600–1,000 汉字，包括读者、先修要求、学习路径、使用方法、12 章目录及本书最后能完成的作品。

## 四、manifest.json 的严格字段

JSON 不含注释、尾逗号、Markdown 围栏。以下为字段结构说明；实际交付须列全 6 本和每本 12 章，不得出现省略号。所有字段均必须出现，不增加额外字段。

顶层仅有：

```json
{
  "schema_version": "k12.book.source.v1",
  "package_id": "k12-original-books-v1",
  "language": "zh-CN",
  "content_kind": "ORIGINAL_TEXTBOOK",
  "ai_assisted": true,
  "review_status": "UNREVIEWED",
  "books": []
}
```

每个 `books` 元素仅有以下字段：

```json
{
  "book_id": "primary-computing",
  "title": "数字世界与计算思维",
  "stage_group": "PRIMARY",
  "grade_min": 1,
  "grade_max": 6,
  "description": "一段真实概述本书内容与学习成果的说明，150至250汉字。",
  "prerequisites": ["真实先修条件，零基础时写无需编程基础"],
  "learning_outcomes": ["可观察的学习成果，5至8条"],
  "preface_path": "books/primary-computing/preface.md",
  "chapters": []
}
```

每个 `chapters` 元素仅有以下字段：

```json
{
  "chapter_id": "primary-computing-ch01",
  "order": 1,
  "title": "认识数字世界",
  "objectives": ["本章可观察的学习目标，3至5条"],
  "prerequisite_chapter_ids": [],
  "estimated_minutes": 35,
  "markdown_path": "books/primary-computing/chapters/01.md",
  "answers_path": "answers/primary-computing/01.json",
  "knowledge_points": ["具体知识点，3至6条"],
  "references": [
    {"title": "真实来源标题", "url": "https://官方来源的完整地址", "purpose": "用于核对哪一个概念或例子"}
  ]
}
```

- ID 固定为 `<book_id>-ch01` 至 `<book_id>-ch12`，`order` 为整数 1–12；路径两位编号与 ID 一致。
- `estimated_minutes` 为整数 20–120，按实际阅读、活动和练习量估计，不声称经过真实学生测量。
- 先修章节只能指向同一本书已排在前面的章节；第一章使用空数组。
- 每章 1–3 条真实、可访问、与该章直接相关的权威来源，优先官方文档、教育机构、标准组织或原始研究。核验链接，不编造书名、作者、页码、DOI、实验结果或引用。
- 全部内容原创编写，标明 AI 辅助且未经过人工教学审校；不宣称官方教材、原书全文、出版物授权或已验证教学效果。

## 五、每章 Markdown 的固定结构

每个文件仅包含本章正文，无 YAML front matter，无文件路径标记。只有一个一级标题，必须与 manifest 的章名严格一致。以下 **10 个二级标题顺序和文字固定**；仅可在它们下面增加三级、四级标题，不另加二级标题。

```text
# <本章 title>

## 学习目标
3–5条，与manifest一致。

## 开始之前
先修知识；一个可回答的热身问题；必要材料。

## 情景导入
有具体人物、问题、条件的真实或明确虚构情景。

## 知识讲解
至少4个三级子节，每个写清概念、作用、原理或步骤、适用条件。

## 详细示例
至少两个不同案例，每个完整展开，不给结论就结束。

## 动手实践
目标、材料、至少6步、完成判据、排查方法。

## 常见误区
至少3个，每个给出错误说法、原因、正确理解或反例。

## 练习与自测
### Q01 · 单选题
题干；A、B、C、D四个选项。
### Q02 · 单选题
题干；A、B、C、D四个选项。
### Q03 · 简答题
清晰题干和作答要求。
### Q04 · 简答题
清晰题干和作答要求。
### Q05 · 实践题
材料、任务、输入输出或完成判据。
### Q06 · 实践题
迁移应用任务，不重复Q05。

## 本章小结
5条以内，提炼关键联系；提示下一章会继续解决什么问题。

## 延伸阅读
列出manifest中的真实来源链接，并说明用途。
```

学生正文不得出现 Q01–Q06 的正确选项、参考答案、评分细则或答案解析；它们只放在 `answers/`。讲解案例可以包含自己的完整解法，但不得用相同数据直接泄露自测题答案。每章题目独立原创，不能只给上一章题目换数字。

支持 GFM 表格、列表、代码围栏、标准链接和 `$...$` / `$$...$$` 数学公式。不要写原始 HTML、iframe、脚本、交互控件或依赖外部图片；图解用文字示意或表格，确保仅靠正文即可理解。表格每格尽量简短，复杂程序拆成有解释的短例子；单个段落、表格或完整代码围栏不要超过 3,500 字符，以便导入时完整分块。代码围栏必须标语言并闭合。

## 六、答案文件的固定结构

每个答案文件顶层仅有 `schema_version`、`book_id`、`chapter_id`、`answers`。示例如下；实际每章必须列全 Q01–Q06：

```json
{
  "schema_version": "k12.book.answers.v1",
  "book_id": "primary-computing",
  "chapter_id": "primary-computing-ch01",
  "answers": [
    {
      "question_id": "Q01",
      "type": "SINGLE_CHOICE",
      "correct_options": ["B"],
      "reference_answer": "准确的参考答案。",
      "explanation": "解释答案为什么成立，并说明典型错误。",
      "rubric": [{"criterion": "可核对的评分标准", "points": 10}]
    }
  ]
}
```

每个答案对象仅有上例的 6 个字段。类型按题号固定：Q01–Q02 为 `SINGLE_CHOICE`，Q03–Q04 为 `SHORT_ANSWER`，Q05–Q06 为 `PRACTICE`。单选 `correct_options` 恰好一个 A/B/C/D；其他题必须为空数组。每题 rubric 分值合计恰好 10，分值为正整数。每题解析至少 100 汉字；简答、实践答案要列关键推理或步骤，合理开放答案允许多种完成方式。题号、题型和答案必须相互吻合。

## 七、事实和代码要求

1. 数学和代码必须核验，使用 Python 3.12 标准库优先。涉及外部库时必须在正文写出依赖与版本要求，明确哪些代码需外部环境。不能把伪代码标为 Python 或说成已运行。
2. 常规入门代码无需网络、密钥、云服务或第三方账号；小数据集直接给出可复制的 JSON/CSV/列表。仅使用合成数据，写清数据字段和单位。
3. 高中算法至少覆盖一个边界输入、复杂度及适用条件；机器学习明确训练、验证、测试用途，避免数据泄漏和凭空宣称准确率。
4. AI 只能描述为从数据中学习规律的系统；不要拟人化成有感受、不会犯错、必然理解人类意图的实体。涉及隐私或判断时给出适合年龄的具体做法。
5. 编程示例和活动不假定已接入接收项目的在线判题，不编造可点击入口或实验运行结果。

## 八、交付与质量核验

直接按文件持续完成全部书目。如果上下文不足，记录已完成章节并续写，不能缩短后续章节或只留标题。最后必须重新读取各文件核验，输出完整 ZIP，不以聊天中“已完成”代替文件。

`quality-report.json` 顶层固定为：

```json
{
  "schema_version": "k12.book.quality.v1",
  "package_id": "k12-original-books-v1",
  "book_count": 6,
  "chapter_count": 72,
  "answer_file_count": 72,
  "total_body_han_chars": 156000,
  "chapters": [],
  "issues": []
}
```

`total_body_han_chars` 填实际统计值，不填写目标值。`chapters` 每章一条且仅有 `chapter_id`、`body_han_chars`、`exercise_count`、`all_required_headings_present`、`answer_ids_match`、`code_examples_checked`。前两计数字段填真实结果；布尔字段按实际核验填写，未执行代码不写成检查通过。`issues` 为真实未解决问题的字符串数组，无问题时为空；存在篇幅不足、缺章、缺答案或格式不符合时先修复再交付。

逐项核验：6本/72章/72答案；全部路径存在；JSON可解析且无多余字段；学段与年级正确；ID唯一；12章排序连续；十个二级标题一致；逐章汉字数达标；练习恰好6题且答案对应；答案未混入学生正文；代码围栏闭合；示例结果准确；来源链接可访问；没有“待补充”“略”“TODO”、假引用、密钥或个人数据。

最终提供 `k12-original-books-v1.zip`，以及简短交付说明：六本书名、每本正文实际字数、总章节数、实际完成的核验及任何剩余问题。
