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

export type QuestionType = "SINGLE_CHOICE" | "TRUE_FALSE" | "ORDERING";

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
  /** Present only after the server scored at least one attempt. */
  feedback?: QuestionFeedback;
};

export type QuizProgress = { answered: number; correct: number; total: number };

export type QuizSessionDTO = {
  id: string;
  chapter_id: string;
  revision_id: string;
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
  created_at: string;
  completed_at: string | null;
  progress: QuizProgress;
  questions: QuizQuestionDTO[];
  notices: string[];
};

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

/** The three accepted JSON shapes for `answer` (T16 scoring contract). */
export type QuizAnswer = string | boolean | string[];

export const QUESTION_TYPE_LABEL: Record<QuestionType, string> = {
  SINGLE_CHOICE: "单选",
  TRUE_FALSE: "判断",
  ORDERING: "排序",
};

export const DIFFICULTY_LABEL: Record<string, string> = {
  EASY: "基础",
  MEDIUM: "进阶",
  HARD: "挑战",
};
