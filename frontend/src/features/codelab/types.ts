export type CodeTask = {
  schema_version: string;
  task_id: string;
  revision: number;
  status: string;
  is_test_fixture: boolean;
  review_status: string;
  title: string;
  description: string;
  starter_code: string;
  entrypoint: string;
  io_contract: Record<string, unknown>;
  examples: Array<{ input: Record<string, unknown>; output: unknown }>;
  public_test_groups: Array<{
    id: string;
    name: string;
    dimension: "F" | "R";
    max_score: number;
    case_count: number;
  }>;
  chapter_binding: {
    course_slug: string;
    chapter_slug: string;
    revision: number;
    stage: string;
    knowledge_point_slugs: string[];
  };
};

export type CodeDraft = {
  task_id: string;
  task_revision: number;
  code: string;
  code_hash: string;
  updated_at: string | null;
};

export type CodeRun = {
  id: string;
  task_id: string;
  task_revision: number;
  lesson_session_id: string | null;
  status: string;
  execution_status: string;
  correctness_status: string;
  deterministic_score: number | null;
  code_hash: string;
  code: string;
  result: {
    grading?: {
      status: string;
      deterministic_score: number | null;
      groups: Array<Record<string, unknown>>;
    };
    observations?: Array<Record<string, unknown>>;
    error?: string;
  } | null;
  feedback_status: string;
  feedback: { status: string; summary: string; references: Array<Record<string, unknown>> } | null;
  created_at: string;
  completed_at: string | null;
};
