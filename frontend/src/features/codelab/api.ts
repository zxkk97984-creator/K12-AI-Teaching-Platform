import { ApiError, ensureCsrfToken } from "../identity/api";
import type { CodeDraft, CodeRun, CodeRunDetail, CodeRunPage, CodeTask, CodeTaskPage } from "./types";

const API_BASE = "/api/v1";

async function request<T>(path: string, init: RequestInit = {}, mutation = false): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (mutation) headers.set("X-CSRF-Token", await ensureCsrfToken());
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body?.error;
    throw new ApiError(
      response.status,
      error?.code ?? `HTTP_${response.status}`,
      error?.message ?? body?.detail ?? "请求失败",
      error?.request_id ?? null,
    );
  }
  return body as T;
}

export type ListCodeTasksParams = {
  q?: string;
  category?: string;
  difficulty?: string;
  progress?: string;
  favorite_only?: boolean;
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
};

export async function listCodeTasks(params: ListCodeTasksParams = {}): Promise<CodeTaskPage> {
  const query = new URLSearchParams();
  for (const key of ["q", "category", "difficulty", "progress", "limit", "offset"] as const) {
    const value = params[key];
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  if (params.favorite_only) query.set("favorite_only", "true");
  const suffix = query.size ? `?${query.toString()}` : "";
  return request(`${API_BASE}/code-tasks${suffix}`, { signal: params.signal });
}

export async function getCodeTask(
  taskId: string,
  revision?: number,
  signal?: AbortSignal,
): Promise<CodeTask> {
  const query = revision === undefined ? "" : `?revision=${revision}`;
  return request(
    `${API_BASE}/code-tasks/${encodeURIComponent(taskId)}${query}`,
    { signal },
  );
}

export async function getRunnerStatus(): Promise<{ available: boolean; reason: string }> {
  return request(`${API_BASE}/code-runner/status`);
}

export async function getCodeDraft(
  taskId: string,
  revision: number,
  scope?: CodeWorkspaceScope,
  signal?: AbortSignal,
): Promise<CodeDraft> {
  const query = new URLSearchParams({ revision: String(revision) });
  if (scope && scope.kind !== "STANDALONE") {
    query.set("scope_kind", scope.kind);
    query.set(
      "scope_id",
      scope.kind === "CHAPTER"
        ? scope.chapter_revision_id
        : scope.kind === "LESSON"
          ? scope.lesson_session_id
          : `${scope.quiz_session_id}:${scope.question_id}`,
    );
  }
  return request(
    `${API_BASE}/code-tasks/${encodeURIComponent(taskId)}/draft?${query.toString()}`,
    { signal },
  );
}

export type CodeWorkspaceScope =
  | { kind: "STANDALONE" }
  | { kind: "CHAPTER"; chapter_revision_id: string }
  | { kind: "LESSON"; lesson_session_id: string }
  | { kind: "QUIZ"; quiz_session_id: string; question_id: string };

export async function saveCodeDraft(
  taskId: string,
  revision: number,
  code: string,
  lessonSessionId?: string,
  scope?: CodeWorkspaceScope,
  baseRevision = 0,
): Promise<CodeDraft> {
  return request(
    `${API_BASE}/code-tasks/${encodeURIComponent(taskId)}/draft`,
    {
      method: "PUT",
      body: JSON.stringify({
        task_revision: revision,
        code,
        lesson_session_id: lessonSessionId ?? null,
        scope: scope ?? null,
        base_revision: baseRevision,
      }),
    },
    true,
  );
}

export async function createCodeRun(
  taskId: string,
  revision: number,
  code: string,
  idempotencyKey: string,
  lessonSessionId?: string,
  purpose: "EXAMPLE" | "GRADE" = "GRADE",
  scope?: CodeWorkspaceScope,
  quizSessionId?: string,
  questionId?: string,
): Promise<{ run: CodeRun; idempotent_replay: boolean }> {
  return request(
    `${API_BASE}/code-runs?task_id=${encodeURIComponent(taskId)}`,
    {
      method: "POST",
      body: JSON.stringify({
        task_revision: revision,
        code,
        idempotency_key: idempotencyKey,
        lesson_session_id: lessonSessionId ?? null,
        purpose,
        async_run: true,
        scope: scope ?? null,
        quiz_session_id: quizSessionId ?? null,
        question_id: questionId ?? null,
      }),
    },
    true,
  );
}

export async function getCodeRun(runId: string, signal?: AbortSignal): Promise<CodeRunDetail> {
  return request(`${API_BASE}/code-runs/${encodeURIComponent(runId)}`, { signal });
}

export async function cancelCodeRun(runId: string): Promise<{ run: CodeRun }> {
  return request(
    `${API_BASE}/code-runs/${encodeURIComponent(runId)}/cancel`,
    { method: "POST", body: JSON.stringify({}) },
    true,
  );
}

export async function requestCodeFeedback(runId: string): Promise<{ run: CodeRun; fixture: boolean; reason?: string | null }> {
  return request(
    `${API_BASE}/code-runs/${encodeURIComponent(runId)}/feedback`,
    { method: "POST", body: JSON.stringify({}) },
    true,
  );
}

export async function favoriteCodeTask(taskId: string): Promise<{ task_id: string; is_favorite: boolean }> {
  return request(
    `${API_BASE}/code-tasks/${encodeURIComponent(taskId)}/favorite`,
    { method: "PUT", body: JSON.stringify({}) },
    true,
  );
}

export async function unfavoriteCodeTask(taskId: string): Promise<{ task_id: string; is_favorite: boolean }> {
  return request(
    `${API_BASE}/code-tasks/${encodeURIComponent(taskId)}/favorite`,
    { method: "DELETE" },
    true,
  );
}

export type ListCodeRunsParams = {
  q?: string;
  task_id?: string;
  task_revision?: number;
  purpose?: "EXAMPLE" | "GRADE";
  scope_kind?: "STANDALONE" | "CHAPTER" | "LESSON" | "QUIZ";
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
};

export async function listCodeRuns(params: ListCodeRunsParams = {}): Promise<CodeRunPage> {
  const query = new URLSearchParams();
  for (const key of ["q", "task_id", "task_revision", "purpose", "scope_kind", "limit", "offset"] as const) {
    const value = params[key];
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const suffix = query.size ? `?${query.toString()}` : "";
  return request(`${API_BASE}/code-runs${suffix}`, { signal: params.signal });
}
