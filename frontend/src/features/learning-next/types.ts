/**
 * Next-step DTOs (T19).
 *
 * The recommendation routes are not part of the frozen `contracts/openapi.*.json`
 * documents, so these types mirror the T19 router by hand. Every suggestion
 * carries a source, the evidence it used, a reason and the rule version; there
 * is deliberately no mastery percentage, rank or personality field.
 */

export type NextStepKind =
  | "CONTINUE_LESSON"
  | "REVIEW_MISTAKE"
  | "PRACTICE_WEAK"
  | "CONTINUE_COURSE"
  | "START_COURSE"
  | "INTEREST_MATCH"
  | "NO_CONTENT"
  | "ALL_IGNORED";

export type NextStepItem = {
  kind: NextStepKind;
  subject_key: string;
  title: string;
  reason: string;
  source: Record<string, string | null>;
  evidence_ids: string[];
  action: {
    type?: string;
    session_id?: string;
    chapter_id?: string;
    phase?: string;
    objective_id?: string;
    quiz_session_id?: string | null;
    question_position?: number | null;
    quiz_status?: "ACTIVE" | "COMPLETED" | null;
    quiz_answered?: number;
    quiz_title?: string;
  };
  rule_version: string;
  thresholds_version: string;
  effect_verified: boolean;
};

export type NextStepDTO = {
  primary: NextStepItem;
  alternatives: NextStepItem[];
  basis: {
    stage: string;
    grade: number | null;
    active_lesson_id: string | null;
    active_phase: string | null;
    real_answers: number;
    hints_or_skips_only: boolean;
    evidence_ids: string[];
    active_memory_ids: string[];
    ignored_subjects: string[];
    rule_version: string;
    thresholds_version: string;
    effect_verified: boolean;
  };
  rule_version: string;
  thresholds_version: string;
  effect_verified: boolean;
  honest_notes: string[];
  inputs_hash: string;
  snapshot_state: "NOT_PROJECTED" | "STALE" | "CURRENT";
  needs_projection: boolean;
  needs_refresh: boolean;
  snapshot: { id: string; source_revision: number; created_at: string } | null;
  ignored_subjects: string[];
  cold_start: boolean;
  feedback: FeedbackDTO[];
  projection?: { created: boolean; inputs_hash: string; source_revision: number | null };
};

export type FeedbackDTO = {
  subject_key: string;
  state: "IGNORED" | "ACTIVE";
  revision: number;
  reason: string | null;
  updated_at: string;
  history?: Array<{
    id: string;
    action: "IGNORE" | "RESTORE";
    from_state: string;
    to_state: string;
    from_revision: number;
    to_revision: number;
    reason: string | null;
    created_at: string;
  }>;
};

export const KIND_LABEL: Record<NextStepKind, string> = {
  CONTINUE_LESSON: "继续本课",
  REVIEW_MISTAKE: "错题复习",
  PRACTICE_WEAK: "继续练习",
  CONTINUE_COURSE: "课程续学",
  START_COURSE: "从这里开始",
  INTEREST_MATCH: "兴趣相关",
  NO_CONTENT: "暂无内容",
  ALL_IGNORED: "已忽略全部",
};

export function actionHref(item: NextStepItem, returnTo?: string): string | null {
  const action = item.action ?? {};
  if (action.type === "OPEN_LESSON" && action.session_id) {
    return action.chapter_id ? `/chapters/${encodeURIComponent(action.chapter_id)}?assistant=chat` : `/conversations?session=${encodeURIComponent(action.session_id)}`;
  }
  if (action.type === "OPEN_CHAPTER" && action.chapter_id) {
    return `/chapters/${encodeURIComponent(action.chapter_id)}`;
  }
  if (action.type === "OPEN_PRACTICE" && action.quiz_session_id) {
    const position = action.question_position ?? 0;
    return `/practice/sessions/${encodeURIComponent(action.quiz_session_id)}?q=${Number.isInteger(position) && position >= 0 ? position : 0}${returnTo ? `&returnTo=${encodeURIComponent(returnTo)}` : ""}`;
  }
  return null;
}

export function actionLabel(item: NextStepItem): string {
  switch (item.action?.type) {
    case "OPEN_LESSON":
      return "回到这一节";
    case "OPEN_CHAPTER":
      return "打开这一章";
    case "OPEN_PRACTICE":
      return item.action.quiz_status === "COMPLETED" ? "查看结果与解析"
        : item.action.quiz_status === "ACTIVE" ? item.action.quiz_answered ? "继续练习" : "开始练习" : "查看练习";
    default:
      return "查看";
  }
}
