import type { RunDTO } from "../conversation/types";

export type LearningPolicy = {
  schema_version?: string;
  stage?: string;
  grade?: number | null;
  preferred_style?: string;
  evidence_level?: string;
  allowed_actions?: string[];
  max_quiz_questions?: number;
  allowed_difficulties?: string[];
  allowed_question_types?: string[];
  max_explanation_chars?: number;
  media_candidates?: string[];
  scaffolding?: string;
  proactive_opening_allowed?: boolean;
};

export type LessonEvidenceSummary = {
  total: number;
  real_activities: number;
  correct_activities: number;
  skipped: number;
  evidence_level: string;
};

export type LessonPhaseDTO = {
  session_id: string;
  phase: string;
  lifecycle: string;
  phase_revision: number;
  policy: LearningPolicy;
  policy_snapshot_id: string | null;
  evidence: LessonEvidenceSummary;
  run: RunDTO | null;
  proactive_opening: string | null;
};

export type LessonEventName =
  | "ENTER"
  | "RESUME"
  | "ASK"
  | "START_EXPLAIN"
  | "EXPLAIN_DONE"
  | "CHECK_CORRECT"
  | "CHECK_INCORRECT"
  | "PRACTICE_DONE"
  | "SKIP_ACTIVITY"
  | "REFLECT_DONE"
  | "COMPLETE_REQUESTED"
  | "PAUSE"
  | "RESUME_FROM_PAUSE";
