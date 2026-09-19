import { ApiError, ensureCsrfToken } from "../identity/api";
import type { CodeDraft, CodeRun, CodeTask } from "./types";

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

export async function listCodeTasks(): Promise<{ items: CodeTask[] }> {
  return request(`${API_BASE}/code-tasks`);
}

export async function getCodeDraft(taskId: string, revision: number): Promise<CodeDraft> {
  return request(`${API_BASE}/code-tasks/${encodeURIComponent(taskId)}/draft?revision=${revision}`);
}

export async function saveCodeDraft(
  taskId: string,
  revision: number,
  code: string,
  lessonSessionId?: string,
): Promise<CodeDraft> {
  return request(
    `${API_BASE}/code-tasks/${encodeURIComponent(taskId)}/draft`,
    {
      method: "PUT",
      body: JSON.stringify({
        task_revision: revision,
        code,
        lesson_session_id: lessonSessionId ?? null,
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
      }),
    },
    true,
  );
}

export async function getCodeRun(runId: string): Promise<{ run: CodeRun }> {
  return request(`${API_BASE}/code-runs/${encodeURIComponent(runId)}`);
}

export async function cancelCodeRun(runId: string): Promise<{ run: CodeRun }> {
  return request(
    `${API_BASE}/code-runs/${encodeURIComponent(runId)}/cancel`,
    { method: "POST", body: JSON.stringify({}) },
    true,
  );
}

export async function requestCodeFeedback(runId: string): Promise<{ run: CodeRun; fixture: boolean }> {
  return request(
    `${API_BASE}/code-runs/${encodeURIComponent(runId)}/feedback`,
    { method: "POST", body: JSON.stringify({}) },
    true,
  );
}
