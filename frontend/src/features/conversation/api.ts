import { ApiError, ensureCsrfToken } from "../identity/api";
import type { RunDTO, SceneSnapshot, SessionDetail, SessionSummary, TurnAccepted } from "./types";

const API_BASE = "/api/v1";

type ErrorEnvelope = { error?: { code?: string; message?: string; request_id?: string } };

async function request<T>(path: string, init: RequestInit = {}, mutation = false): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (mutation) headers.set("X-CSRF-Token", await ensureCsrfToken());
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!response.ok) {
    const envelope = (body ?? {}) as ErrorEnvelope;
    const error = new ApiError(
      response.status,
      envelope.error?.code ?? `HTTP_${response.status}`,
      envelope.error?.message ?? "请求失败",
      envelope.error?.request_id ?? null,
    );
    if (response.status === 401) {
      window.dispatchEvent(new CustomEvent("identity:unauthorized", { detail: error }));
    }
    throw error;
  }
  return body as T;
}

export async function listSessions(includeArchived = false, limit = 100): Promise<SessionSummary[]> {
  try {
    const query = new URLSearchParams({ include_archived: String(includeArchived), limit: String(limit) });
    return await request<SessionSummary[]>(`${API_BASE}/conversations?${query}`);
  } catch (error) {
    // Keep the existing lesson-session endpoint as a compatibility path for
    // older deployments and the browser fixture server.
    if (error instanceof ApiError && error.status === 404)
      return request<SessionSummary[]>(`${API_BASE}/lesson-sessions?include_archived=${includeArchived}&limit=${limit}`);
    throw error;
  }
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  try {
    return await request<SessionDetail>(`${API_BASE}/conversations/${sessionId}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404)
      return request<SessionDetail>(`${API_BASE}/lesson-sessions/${sessionId}`);
    throw error;
  }
}

/**
 * Create a lesson session or a free conversation. The conversation endpoint
 * is used when no chapter is supplied so students can start with a question
 * from the empty state; the legacy lesson endpoint remains available for
 * chapter-bound classroom sessions.
 */
export function createSession(chapterId?: string, idempotencyKey?: string): Promise<SessionSummary> {
  if (!chapterId) {
    return request<SessionSummary>(
      `${API_BASE}/conversations`,
      { method: "POST", body: JSON.stringify({ idempotency_key: idempotencyKey ?? null }) },
      true,
    );
  }
  return request<SessionSummary>(
    `${API_BASE}/lesson-sessions`,
    { method: "POST", body: JSON.stringify({ chapter_id: chapterId }) },
    true,
  );
}

export function updateSession(
  sessionId: string,
  patch: { title?: string | null; archived?: boolean },
): Promise<SessionSummary> {
  return request<SessionSummary>(
    `${API_BASE}/conversations/${sessionId}`,
    { method: "PATCH", body: JSON.stringify(patch) },
    true,
  );
}

export async function deleteSession(sessionId: string): Promise<void> {
  await request<void>(
    `${API_BASE}/conversations/${sessionId}`,
    { method: "DELETE" },
    true,
  );
}

export function createTurn(
  sessionId: string,
  message: string,
  idempotencyKey: string,
  mode: "FREE" | "LESSON" = "LESSON",
  scene?: SceneSnapshot,
): Promise<TurnAccepted> {
  if (mode === "FREE") {
    return request<TurnAccepted>(
      `${API_BASE}/conversations/${sessionId}/messages`,
      {
        method: "POST",
        body: JSON.stringify({ message, idempotency_key: idempotencyKey, scene }),
      },
      true,
    );
  }
  return request<TurnAccepted>(
    `${API_BASE}/lesson-sessions/${sessionId}/turns`,
    { method: "POST", body: JSON.stringify({ message, idempotency_key: idempotencyKey, scene }) },
    true,
  );
}

export function getRun(runId: string): Promise<RunDTO> {
  return request<RunDTO>(`${API_BASE}/agent-runs/${runId}`);
}

export function cancelRun(runId: string): Promise<RunDTO> {
  return request<RunDTO>(`${API_BASE}/agent-runs/${runId}/cancel`, { method: "POST" }, true);
}

export type RunSubscription = {
  close: () => void;
};

const RUN_STATUSES = new Set(["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "STALE"]);

/**
 * Native SSE: reconnect after a refresh only re-reads the stored run; the
 * server never starts a second model call for the same run.
 */
export function subscribeRun(
  runId: string,
  handlers: { onUpdate: (run: RunDTO) => void; onError?: () => void },
): RunSubscription {
  const source = new EventSource(`${API_BASE}/agent-runs/${runId}/events`, {
    withCredentials: true,
  });
  const terminal = new Set(["done", "failed", "cancelled", "stale"]);
  let finished = false;
  const handle = (event: MessageEvent<string>) => {
    if (finished) return;
    let payload: unknown;
    try {
      payload = JSON.parse(event.data);
    } catch {
      handlers.onError?.();
      return;
    }
    const candidate = payload as Partial<RunDTO> | null;
    if (!candidate || typeof candidate !== "object" ||
        typeof candidate.status !== "string" || !RUN_STATUSES.has(candidate.status) ||
        typeof candidate.id !== "string" || typeof candidate.session_id !== "string") {
      handlers.onError?.();
      return;
    }
    handlers.onUpdate(candidate as RunDTO);
    if (["SUCCEEDED", "FAILED", "CANCELLED", "STALE"].includes(candidate.status)) {
      finished = true;
      source.close();
    }
  };
  for (const name of ["update", "done", "failed", "cancelled", "stale"]) {
    source.addEventListener(name, (event) => {
      handle(event as MessageEvent<string>);
      if (terminal.has(name)) {
        finished = true;
        source.close();
      }
    });
  }
  // A closed stream also fires onerror in some browsers: never report that as
  // a connection problem once the run already reached a terminal event.
  source.onerror = () => {
    if (!finished) handlers.onError?.();
  };
  return {
    close: () => {
      finished = true;
      source.close();
    },
  };
}
