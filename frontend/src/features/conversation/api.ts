import { ApiError, ensureCsrfToken } from "../identity/api";
import type { RunDTO, SessionDetail, SessionSummary, TurnAccepted } from "./types";

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

export function listSessions(): Promise<SessionSummary[]> {
  return request<SessionSummary[]>(`${API_BASE}/lesson-sessions`);
}

export function getSession(sessionId: string): Promise<SessionDetail> {
  return request<SessionDetail>(`${API_BASE}/lesson-sessions/${sessionId}`);
}

export function createSession(chapterId: string): Promise<SessionSummary> {
  return request<SessionSummary>(
    `${API_BASE}/lesson-sessions`,
    { method: "POST", body: JSON.stringify({ chapter_id: chapterId }) },
    true,
  );
}

export function createTurn(
  sessionId: string,
  message: string,
  idempotencyKey: string,
): Promise<TurnAccepted> {
  return request<TurnAccepted>(
    `${API_BASE}/lesson-sessions/${sessionId}/turns`,
    { method: "POST", body: JSON.stringify({ message, idempotency_key: idempotencyKey }) },
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
    try {
      handlers.onUpdate(JSON.parse(event.data) as RunDTO);
    } catch {
      handlers.onError?.();
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
