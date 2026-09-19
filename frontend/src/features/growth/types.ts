/**
 * Growth / memory DTOs (T18).
 *
 * The growth and memory routes are not part of the frozen
 * `contracts/openapi.*.json` documents (those stay byte-identical in T18), so
 * these types mirror the T18 routers by hand. Nothing here carries a mastery
 * percentage: observations are qualitative levels plus the raw counts they were
 * derived from, and every memory exposes its own revision for conflict checks.
 */

export type ObservationLevel = "INSUFFICIENT_EVIDENCE" | "EMERGING" | "CONSISTENT";

export type ObservationBasis = {
  evidence_ids: string[];
  hint_evidence_ids?: string[];
  answered: number;
  correct: number;
  distinct_questions: number;
  hints_viewed: number;
  rule_version: string;
  thresholds_version: string;
  effect_verified: boolean;
};

export type ObservationDTO = {
  id: string;
  subject_kind: "OBJECTIVE";
  subject_key: string;
  level: ObservationLevel;
  statement: string;
  basis: ObservationBasis;
  rule_version: string;
  projection_revision: number;
  superseded_at: string | null;
  created_at: string;
  notice: string;
};

export type MemoryStatus = "CANDIDATE" | "ACTIVE" | "DISPUTED" | "REMOVED";

export type MemoryEventDTO = {
  id: string;
  action: "CREATE" | "CONFIRM" | "DISPUTE" | "EDIT" | "FORGET";
  from_status: string;
  to_status: MemoryStatus;
  from_revision: number;
  to_revision: number;
  statement_before: string | null;
  statement_after: string | null;
  reason: string | null;
  actor: string;
  created_at: string;
};

export type MemoryDTO = {
  id: string;
  kind: "STUDY_STRATEGY" | "PREFERENCE";
  status: MemoryStatus;
  statement: string;
  content: Record<string, unknown>;
  basis_evidence_ids: string[];
  basis_counts: Record<string, number>;
  rule_version: string;
  origin: string;
  revision: number;
  injection_status: "INJECTED" | "EXCLUDED";
  injection_note: string;
  local_withdrawal_notice: string | null;
  remote_residue: string;
  decided_at: string | null;
  removed_at: string | null;
  created_at: string;
  updated_at: string;
  history: MemoryEventDTO[];
};

export type GrowthOverviewDTO = {
  owner_scoped: boolean;
  evidence_total: number;
  evidence_by_kind: Record<string, number>;
  real_answers: number;
  correct_answers: number;
  observations: ObservationDTO[];
  memories: MemoryDTO[];
  insufficient_evidence: boolean;
  counts_not_effect_notice: string;
  no_percentage_notice: string;
  needs_projection: boolean;
  projection_rule_version: string;
  projection?: {
    evidence: { scanned: number; inserted: number; rule_version: string };
    observations: { objectives: number; created: number; reused: number; rule_version: string };
    memories: { created: number; skipped: number; rule_version: string };
  };
};

export type EvidenceDetailDTO = {
  id: string;
  source_kind: string;
  outcome: string;
  objective_id: string | null;
  knowledge_point_slugs: string[];
  source_ref: Record<string, string | null>;
  rule_version: string;
  observed_at: string;
  projected_at: string;
  summary: string;
};

export type MemoryAction = "CONFIRM" | "DISPUTE" | "EDIT" | "FORGET";

export const LEVEL_LABEL: Record<ObservationLevel, string> = {
  INSUFFICIENT_EVIDENCE: "证据不足",
  EMERGING: "正在形成",
  CONSISTENT: "较一致",
};

export const MEMORY_STATUS_LABEL: Record<MemoryStatus, string> = {
  CANDIDATE: "待你确认",
  ACTIVE: "已确认",
  DISPUTED: "有疑问",
  REMOVED: "已遗忘",
};

export const ACTION_LABEL: Record<MemoryEventDTO["action"], string> = {
  CREATE: "创建",
  CONFIRM: "确认",
  DISPUTE: "标记疑问",
  EDIT: "修改",
  FORGET: "遗忘",
};
