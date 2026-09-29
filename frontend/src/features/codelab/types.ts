import type { components } from "../../shared/types/generated/learning";

type GeneratedTask = components["schemas"]["CodeTaskView"];
type GeneratedRun = components["schemas"]["CodeRunView"];

export type CodeTask = GeneratedTask;

export type CodeDraft = {
  task_id: string;
  task_revision: number;
  code: string;
  code_hash: string;
  scope_key?: string;
  revision_number?: number;
  updated_at: string | null;
};

export type CodeRun = Omit<GeneratedRun, "purpose" | "result" | "feedback"> & {
  purpose: "EXAMPLE" | "GRADE";
  result: {
    grading?: {
      status: string;
      deterministic_score: number | null;
      groups: Array<Record<string, unknown>>;
    };
    observations?: Array<Record<string, unknown>>;
    error?: string;
  } | null;
  feedback: {
    status: string;
    source?: "KNODO" | "FIXTURE";
    facts_version?: string;
    summary: string;
    references: Array<Record<string, unknown>>;
  } | null;
};

export type CodeTaskPage = components["schemas"]["CodeTaskPage"];
export type CodeRunSummary = components["schemas"]["CodeRunSummaryView"];
export type CodeRunPage = components["schemas"]["CodeRunPage"];
export type CodeRunDetail = Omit<components["schemas"]["CodeRunDetailView"], "run"> & {
  run: CodeRun;
};
