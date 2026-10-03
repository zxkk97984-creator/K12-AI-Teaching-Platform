/**
 * Student quiz DTOs (T17).
 *
 * These mirror the frozen T16 student routes byte-for-byte in shape:
 *   POST /api/v1/quiz-sessions
 *   GET  /api/v1/quiz-sessions/{id}
 *   POST /api/v1/quiz-sessions/{id}/questions/{qid}/answers
 *   POST /api/v1/quiz-sessions/{id}/questions/{qid}/hints
 *   GET  /api/v1/quiz-sessions/{id}/review
 *
 * The quiz routes are not part of `contracts/openapi.*.json` (those two
 * documents are frozen at T03 and were verified byte-identical in T16/T17), so
 * these types are hand-written from the T16 router + DTO. The UI never derives
 * a verdict: `feedback` only exists once the server has scored an attempt.
 */

export type QuestionType = "SINGLE_CHOICE" | "TRUE_FALSE" | "ORDERING" | "CODE";

export type QuizStatus = "ACTIVE" | "COMPLETED";

export type SourceKind = "AI_DRAFT" | "HUMAN_REVIEWED";

export type ChoiceOption = { key: string; text: string };

export type OrderingItem = { key: string; text: string };

export type SourceRef = { source_id: string; revision: string; locator: string };

export type QuestionFeedback = {
  outcome: string;
  is_correct: boolean | null;
  correct_answer: unknown;
  explanation: string;
  attempts_used: number;
  max_attempts: number;
};

export type QuizQuestionDTO = {
  /** Server UUID used by the answer/hint routes (exposed since T16 repair 2). */
  id: string;
  question_key: string;
  position: number;
  type: QuestionType;
  stem: string;
  source_refs: SourceRef[];
  hint_limit: number;
  hints_used: number;
  hints: string[];
  attempts_used: number;
  max_attempts: number;
  options?: ChoiceOption[];
  items?: OrderingItem[];
  code_task_revision_id?: string | null;
  code_snapshot?: {
    task_id?: string;
    task_revision?: number;
    title?: string;
    description?: string;
    starter_code?: string;
    examples?: Array<Record<string, unknown>>;
  };
  is_demo?: boolean;
  /** Present only after the server scored at least one attempt. */
  feedback?: QuestionFeedback;
};

export type QuizProgress = { answered: number; correct: number; total: number };

export type QuizSessionDTO = {
  id: string;
  draft_id?: string | null;
  chapter_id: string | null;
  revision_id: string | null;
  source_conversation_id?: string | null;
  source_message_id?: string | null;
  source_title?: string;
  curriculum_revision: string;
  stage: string;
  status: QuizStatus;
  source_kind: SourceKind;
  source_label: string;
  difficulty: string;
  question_count: number;
  max_attempts: number;
  max_hints: number;
  scoring_version: string;
  thresholds_version: string;
  base_revision: number;
  current_position?: number;
  drafts?: Record<string, { answer: QuizAnswer; revision: number; updated_at: string }>;
  last_submitted_answers?: Record<string, QuizAnswer>;
  created_at: string;
  completed_at: string | null;
  progress: QuizProgress;
  questions: QuizQuestionDTO[];
  notices: string[];
  title?: string;
  has_code?: boolean;
  is_favorite?: boolean;
};

export type QuizSessionListDTO = { items: QuizSessionDTO[]; total: number };

/** Answer-free projection for the home page's recent practice list. */
export type QuizSessionSummaryDTO = {
  id: string;
  chapter_id: string | null;
  source_conversation_id?: string | null;
  title: string;
  status: QuizStatus;
  progress: QuizProgress;
  created_at: string;
  completed_at: string | null;
  is_favorite?: boolean;
};

export type QuizSessionSummaryListDTO = { items: QuizSessionSummaryDTO[]; total: number };

export type AnswerResultDTO = {
  outcome: string;
  is_correct: boolean | null;
  attempts_used: number;
  max_attempts: number;
  correct_answer: unknown;
  explanation: string;
  idempotent_replay: boolean;
  session_status: QuizStatus;
  progress: { answered: number; total: number };
};

export type HintResultDTO = {
  level: number;
  text: string;
  hints_used: number;
  hint_limit: number;
  idempotent_replay: boolean;
};

export type ReviewItemDTO = {
  question_id: string;
  objective_id: string;
  reason: string;
  similar_source: { draft_id: string | null; question_key: string | null; label: string | null };
  next_action: "REVIEW_SIMILAR_QUESTION" | "REVIEW_SOURCE_MATERIAL";
  thresholds_version: string;
  effect_verified: boolean;
};

export type QuizReviewDTO = {
  session_id: string;
  thresholds_version: string;
  scoring_version: string;
  items: ReviewItemDTO[];
  notice: string;
};

/** Completed-session result calculated and returned by the server. */
export type QuizResultDTO = {
  source_conversation_id?: string | null;
  session_id: string;
  status: "COMPLETED";
  scoring_version: string;
  correct: number;
  first_correct: number;
  total: number;
  score_percent: number;
  completed_at: string | null;
  questions: Array<{
    id: string;
    position: number;
    type: QuestionType;
    stem: string;
    first_answer: QuizAnswer | null;
    last_answer: QuizAnswer | null;
    first_correct: boolean | null;
    is_correct: boolean | null;
    attempts_used: number;
    hints_used: number;
    correct_answer: unknown;
    explanation: string;
    source_refs: SourceRef[];
    code_result: unknown;
  }>;
};

/** The three accepted JSON shapes for `answer` (T16 scoring contract). */
export type QuizAnswer = string | boolean | string[];

export const QUESTION_TYPE_LABEL: Record<QuestionType, string> = {
  SINGLE_CHOICE: "单选",
  TRUE_FALSE: "判断",
  ORDERING: "排序",
  CODE: "编程",
};

export const DIFFICULTY_LABEL: Record<string, string> = {
  EASY: "基础",
  MEDIUM: "进阶",
  HARD: "挑战",
};
/** Chapter-backed history keeps the revision captured when its group was created. */
export function quizChapterRevision(session: {chapter_id:string|null;curriculum_revision:string}): number | null {
  if (!session.chapter_id) return null;
  const revision = Number(session.curriculum_revision?.match(/:([1-9]\d*)$/)?.[1]);
  return Number.isSafeInteger(revision) && revision > 0 ? revision : null;
}
