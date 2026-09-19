export type RunStatus =
  | "QUEUED"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED"
  | "STALE";

export type SessionSummary = {
  id: string;
  chapter_id: string;
  chapter_title: string;
  curriculum_revision: string;
  stage: string;
  grade: number | null;
  base_revision: number;
  created_at: string;
  message_count: number;
  last_message_at: string | null;
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
  role: "USER" | "ASSISTANT";
  content_markdown: string;
  card: CardDTO | null;
  created_at: string;
};

export type SessionDetail = SessionSummary & { messages: MessageDTO[] };

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
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  idempotent_replay: boolean;
};

export type TurnAccepted = { run: RunDTO };
