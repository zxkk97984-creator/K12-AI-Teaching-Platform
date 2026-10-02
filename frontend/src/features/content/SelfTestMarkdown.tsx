import { Fragment } from "react";
import { ChapterMarkdown } from "./ChapterMarkdown";
import { SelfTestAnswer } from "./SelfTestAnswer";
import type { SelfTestQuestionDTO } from "./types";

export function SelfTestMarkdown({ text, questions, chapterId, revisionId, accountId }: {
  text: string;
  questions: SelfTestQuestionDTO[];
  chapterId: string;
  revisionId: string;
  accountId?: string;
}) {
  const characters = Array.from(text);
  let start = 0;
  const parts = [...questions].sort((a, b) => a.end_offset - b.end_offset).map((question) => {
    const segment = characters.slice(start, question.end_offset).join("");
    start = question.end_offset;
    return <Fragment key={question.question_id}>
      <ChapterMarkdown text={segment} />
      <SelfTestAnswer chapterId={chapterId} revisionId={revisionId} accountId={accountId} question={question} />
    </Fragment>;
  });
  return <>{parts}<ChapterMarkdown text={characters.slice(start).join("")} /></>;
}
