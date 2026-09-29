export type BookChapter = {
  id: string;
  title: string;
};

export type StudyBook = {
  slug: string;
  title: string;
  topic: string;
  level: string;
  description: string;
  estimatedMinutes: number;
  chapters: BookChapter[];
};

type BookMetadata = Omit<StudyBook, "chapters"> & { chapterTitles: string[] };

function chapterId(bookSlug: string, title: string): string {
  const normalized = title
    .toLocaleLowerCase("zh-CN")
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-|-$/g, "");
  return `${bookSlug}-${normalized}`;
}

function createBook({ chapterTitles, ...metadata }: BookMetadata): StudyBook {
  return {
    ...metadata,
    chapters: chapterTitles.map((title) => ({
      id: chapterId(metadata.slug, title),
      title,
    })),
  };
}

export const studyBooks: StudyBook[] = [
  createBook({
    slug: "python3",
    title: "Python 3：从基础到项目",
    topic: "Python 编程",
    level: "入门到进阶",
    description: "从变量、数据结构和函数开始，逐步掌握文件、异常、类、环境、测试与异步任务，最后完成一个命令行学习记录工具。",
    estimatedMinutes: 95,
    chapterTitles: [
      "第1章 从解释器到第一个程序",
      "第2章 值、变量与类型",
      "第3章 数字、字符串与格式化",
      "第4章 列表、元组、集合与字典",
      "第5章 条件、循环与分支",
      "第6章 函数：把步骤变成接口",
      "第7章 推导式、迭代器与生成器",
      "第8章 模块、包与程序入口",
      "第9章 文件、路径与结构化数据",
      "第10章 错误、异常与资源清理",
      "第11章 类、对象与数据类",
      "第12章 标准库：解决常见问题的工具箱",
      "第13章 虚拟环境、pip 与依赖管理",
      "第14章 测试、调试与代码风格",
      "第15章 异步任务入门",
      "第16章 综合项目：学习记录命令行工具",
    ],
  }),
  createBook({
    slug: "ai-agent",
    title: "AI Agent：从工具调用到可靠工作流",
    topic: "人工智能",
    level: "入门到进阶",
    description: "理解 Agent 运行循环，使用 Python Agents SDK 组织工具、会话、多 Agent、审批与评估，完成一个课堂资料问答助手设计。",
    estimatedMinutes: 90,
    chapterTitles: [
      "第1章 从聊天回答到任务执行",
      "第2章 选择运行方式：Responses、Agents API 与 SDK",
      "第3章 建立第一个可运行的 Agent",
      "第4章 写出可执行的 Agent 指令",
      "第5章 工具：把可执行能力切成窄接口",
      "第6章 工具循环、结果与失败处理",
      "第7章 多轮状态与记忆",
      "第8章 多 Agent：交接还是作为工具",
      "第9章 Guardrails 与人工审批",
      "第10章 MCP、数据源与沙箱边界",
      "第11章 观测与评估：从“看起来不错”到可比较",
      "第12章 综合项目：课堂资料问答助手",
    ],
  }),
  createBook({
    slug: "vibe-coding",
    title: "Vibe Coding：从想法到可交付作品",
    topic: "AI 协作开发",
    level: "零基础友好",
    description: "学习把想法写成验收标准，给编码助手准确上下文，分步实施、调试、检查安全与 Git 历史，并完成一条真实产品流程。",
    estimatedMinutes: 85,
    chapterTitles: [
      "第1章 Vibe Coding 是协作方式，不是免学编程",
      "第2章 从想法写成清楚的任务说明",
      "第3章 写出助手容易执行的提示词",
      "第4章 让助手理解项目，而不是猜项目",
      "第5章 把大作品拆成可运行的小步",
      "第6章 与编码助手一起实施",
      "第7章 验证代码，而不是信任生成结果",
      "第8章 调试：从复现到根因",
      "第9章 界面作品：先让使用者看懂",
      "第10章 数据、安全与自动生成代码",
      "第11章 Git：让尝试可以比较和撤回",
      "第12章 交付、演示与维护",
      "第13章 综合练习：从一句想法做成学习书架",
    ],
  }),
];

export function findStudyBook(slug: string | undefined): StudyBook | undefined {
  return studyBooks.find((book) => book.slug === slug);
}

export function searchStudyBooks(query: string): StudyBook[] {
  const needle = query.trim().toLocaleLowerCase("zh-CN");
  if (!needle) return studyBooks;
  return studyBooks.filter((book) =>
    [
      book.title,
      book.topic,
      book.level,
      book.description,
      ...book.chapters.map((chapter) => chapter.title),
    ]
      .join(" ")
      .toLocaleLowerCase("zh-CN")
      .includes(needle),
  );
}
