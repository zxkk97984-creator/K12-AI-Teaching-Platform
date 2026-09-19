/** Growth + memory API client (T18). Writes always send the CSRF header. */

import { ApiError, ensureCsrfToken } from "../identity/api";
import type {
  EvidenceDetailDTO,
  GrowthOverviewDTO,
  MemoryAction,
  MemoryDTO,
} from "./types";

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

export function getGrowthOverview(): Promise<GrowthOverviewDTO> {
  return request<GrowthOverviewDTO>(`${API_BASE}/growth/overview`);
}

/** Explicit, idempotent reprojection. A read never creates an observation. */
export function reprojectGrowth(): Promise<GrowthOverviewDTO> {
  return request<GrowthOverviewDTO>(`${API_BASE}/growth/projection`, { method: "POST" }, true);
}

export function getEvidenceDetail(evidenceId: string): Promise<EvidenceDetailDTO> {
  return request<EvidenceDetailDTO>(`${API_BASE}/growth/evidence/${evidenceId}`);
}

export function listMemories(): Promise<{ items: MemoryDTO[]; notice: string }> {
  return request<{ items: MemoryDTO[]; notice: string }>(`${API_BASE}/growth/memories`);
}

export function getMemory(memoryId: string): Promise<MemoryDTO> {
  return request<MemoryDTO>(`${API_BASE}/growth/memories/${memoryId}`);
}

export function postMemoryAction(
  memoryId: string,
  action: MemoryAction,
  baseRevision: number,
  extra: { statement?: string; reason?: string } = {},
): Promise<MemoryDTO> {
  return request<MemoryDTO>(
    `${API_BASE}/growth/memories/${memoryId}/events`,
    { method: "POST", body: JSON.stringify({ action, base_revision: baseRevision, ...extra }) },
    true,
  );
}
