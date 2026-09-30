export type RunStatus =
  | "QUEUED"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED"
  | "STALE";

export type SessionSummary = {
  teacher?: { id: string; name: string; description?: string } | null;
  id: string;
  /** A free conversation has no chapter context. */
  conversation_type?: "FREE" | "LESSON" | string;
  /** Compatibility with older fixture payloads. */
  type?: "FREE" | "LESSON" | string;
  title?: string | null;
  archived_at?: string | null;
  chapter_id: string | null;
  chapter_title: string | null;
  curriculum_revision: string;
  stage: string;
  grade: number | null;
  base_revision: number;
  created_at: string;
  message_count: number;
  last_message_at: string | null;
};

export type SceneSnapshot = {
  route: string;
  page_type: string;
  chapter_id?: string | null;
  chapter_title?: string | null;
  visible_section?: string | null;
  selected_text?: string | null;
  content_kind?: "PICTUREBOOK" | "GUIDED_ANIMATION" | "INTERACTIVE" | null;
  content_id?: string | null;
  content_version?: string | null;
  section_index?: number | null;
  knowledge_points?: string[];
  activity_type?: string | null;
  task_id?: string | null;
  task_revision?: number | null;
  code_hash?: string | null;
  execution_status?: string | null;
  quiz_session_id?: string | null;
  question_id?: string | null;
  interactive_session_id?: string | null;
  interactive_scene_id?: string | null;
  interactive_prompt_id?: string | null;
};

export type CardDTO = {
  message_markdown: string;
  source_refs: Array<{ source_id: string; revision: string; locator: string }>;
  evidence_refs: string[];
  followup_question?: string | null;
  action?: Record<string, unknown> | null;
  phase_suggestion?: string | null;
  warnings: string[];
  fixture: boolean;
};

export type MessageDTO = {
  id: string;
  /** Owning generation run; older fixture payloads may omit this field. */
  run_id?: string | null;
  role: "USER" | "ASSISTANT";
  content_markdown: string;
  card: CardDTO | null;
  created_at: string;
};

export type SessionDetail = SessionSummary & {
  messages: MessageDTO[];
  /** An accepted run can be resumed after a page reload without sending again. */
  active_run_id?: string | null;
};

export type RunDTO = {
  id: string;
  session_id: string;
  operation: string;
  status: RunStatus;
  attempt: number;
  fixture: boolean;
  error_category: string | null;
  stale_reason: string | null;
  card: CardDTO | null;
  /** Persisted assistant message id, used to hand off the final card without a flash. */
  result_message_id?: string | null;
  /** Provisional visible answer while a run is active; the validated card wins on completion. */
  draft_markdown?: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  idempotent_replay: boolean;
};

export type TurnAccepted = { run: RunDTO };
