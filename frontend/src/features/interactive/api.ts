import { ApiError, ensureCsrfToken } from "../identity/api";
import type { components as LearningComponents } from "../../shared/types/generated/learning";
import type { components as AdminComponents } from "../../shared/types/generated/admin";

export type InteractivePurpose = LearningComponents["schemas"]["InteractiveCatalogItemDTO"]["purpose"];
export type InteractiveScene = LearningComponents["schemas"]["SceneSpec"];
export type InteractivePrompt = LearningComponents["schemas"]["PromptSpec"];
export type InteractiveManifest = LearningComponents["schemas"]["InteractiveManifestV1"];
export type InteractiveItem = LearningComponents["schemas"]["InteractiveCatalogItemDTO"];
export type InteractiveSession = LearningComponents["schemas"]["InteractiveSessionDTO"];
export type InteractiveDetail = LearningComponents["schemas"]["InteractiveSessionDetailDTO"];

async function request<T>(path: string, init: RequestInit = {}, mutation = false): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (mutation) headers.set("X-CSRF-Token", await ensureCsrfToken());
  const response = await fetch(path, { ...init, credentials: "same-origin", headers });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : "请求失败";
    throw new ApiError(response.status, body?.error?.code ?? `HTTP_${response.status}`, body?.error?.message ?? detail, body?.error?.request_id ?? null);
  }
  return body as T;
}

export function listInteractive(purpose?: InteractivePurpose, q?: string, signal?: AbortSignal) {
  const params = new URLSearchParams();
  if (purpose) params.set("purpose", purpose);
  if (q?.trim()) params.set("q", q.trim());
  return request<LearningComponents["schemas"]["InteractiveCatalogDTO"]>(`/api/v1/interactive/resources?${params}`, { signal });
}
export const getInteractive = (id: string) => request<LearningComponents["schemas"]["InteractiveContentDTO"]>(`/api/v1/interactive/resources/${id}`);
export const startInteractive = (id: string, restart = false) => request<InteractiveSession>("/api/v1/interactive/sessions", { method: "POST", body: JSON.stringify({ resource_id: id, restart }) }, true);
export const getInteractiveSession = (id: string) => request<InteractiveDetail>(`/api/v1/interactive/sessions/${id}`);
export const getInteractiveDocument = (id: string) => request<LearningComponents["schemas"]["InteractiveDocumentDTO"]>(`/api/v1/interactive/sessions/${id}/document`);
export const listInteractiveHistory = (signal?: AbortSignal) => request<LearningComponents["schemas"]["InteractiveHistoryDTO"]>("/api/v1/interactive/sessions", { signal });
export const saveInteractive = (id: string, payload: { base_revision: number; event_id: string; scene_id?: string | null; game_state?: Record<string, unknown> | null }) => request<InteractiveSession>(`/api/v1/interactive/sessions/${id}/checkpoint`, { method: "PATCH", body: JSON.stringify(payload) }, true);
export const completeInteractive = (id: string, payload: { base_revision: number; event_id: string; scene_id?: string | null; game_state?: Record<string, unknown> | null; game_result?: Record<string, unknown>; source?: "SDK_REPORTED" | "USER_CONFIRMED" }) => request<InteractiveSession>(`/api/v1/interactive/sessions/${id}/complete`, { method: "POST", body: JSON.stringify(payload) }, true);

export const adminListInteractiveVersions = (id: string) => request<AdminComponents["schemas"]["InteractiveVersionsDTO"]>(`/api/v1/admin/resources/${id}/interactive-revisions`);
export const adminListInteractiveOverview = () => request<AdminComponents["schemas"]["InteractiveAdminListDTO"]>("/api/v1/admin/interactive/resources");
export const adminUploadInteractive = (id: string, file: File) => request<AdminComponents["schemas"]["InteractiveVersionDTO"]>(`/api/v1/admin/resources/${id}/interactive-revisions`, { method: "POST", body: file, headers: { "X-Filename": file.name, "Content-Type": file.type || "application/octet-stream" } }, true);
export const adminSaveInteractiveManifest = (id: string, revision: string, manifest: InteractiveManifest) => request(`/api/v1/admin/resources/${id}/interactive-revisions/${revision}`, { method: "PATCH", body: JSON.stringify(manifest) }, true);
export const adminActivateInteractive = (id: string, revision: string) => request(`/api/v1/admin/resources/${id}/interactive-revisions/${revision}/activate`, { method: "POST", body: "{}" }, true);
export const adminPreviewInteractive = (id: string, revision: string) => request<AdminComponents["schemas"]["InteractivePreviewDTO"]>(`/api/v1/admin/resources/${id}/interactive-revisions/${revision}/preview`);
export const adminUploadPromptAudio = (id: string, revision: string, prompt: string, file: File) => request(`/api/v1/admin/resources/${id}/interactive-revisions/${revision}/audio/${prompt}`, { method: "PUT", body: file, headers: { "X-Filename": file.name, "Content-Type": file.type || "application/octet-stream" } }, true);
