/** Next-step API client (T19). Writes send the CSRF header; GETs never write. */

import { ApiError, ensureCsrfToken } from "../identity/api";
import type { FeedbackDTO, NextStepDTO } from "./types";

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

export function getNextStep(): Promise<NextStepDTO> {
  return request<NextStepDTO>(`${API_BASE}/recommendation/next-step`);
}

/** Explicit, idempotent projection (a real event path); the GET never writes. */
export function refreshNextStep(): Promise<NextStepDTO> {
  return request<NextStepDTO>(`${API_BASE}/recommendation/refresh`, { method: "POST" }, true);
}

export function postFeedback(
  subjectKey: string,
  action: "IGNORE" | "RESTORE",
  baseRevision: number,
  reason?: string,
): Promise<FeedbackDTO> {
  return request<FeedbackDTO>(
    `${API_BASE}/recommendation/feedback`,
    {
      method: "POST",
      body: JSON.stringify({
        subject_key: subjectKey,
        action,
        base_revision: baseRevision,
        ...(reason ? { reason } : {}),
      }),
    },
    true,
  );
}

/** Reuse T18's evidence detail endpoint so "依据" is the same fact everywhere. */
export function getEvidenceDetail(evidenceId: string) {
  return request<{
    id: string;
    source_kind: string;
    outcome: string;
    objective_id: string | null;
    source_ref: Record<string, string | null>;
    observed_at: string;
    summary: string;
    rule_version: string;
  }>(`${API_BASE}/growth/evidence/${evidenceId}`);
}
