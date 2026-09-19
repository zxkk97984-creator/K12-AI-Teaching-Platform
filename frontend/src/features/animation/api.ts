/** Animation API client (T21). The server validates ids and parameters. */

import { ApiError, ensureCsrfToken } from "../identity/api";
import type { AnimationDefinition, AnimationList, AnimationSpec } from "./types";

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

export function listAnimations(): Promise<AnimationList> {
  return request<AnimationList>(`${API_BASE}/animations`);
}

export function getAnimation(animationId: string): Promise<AnimationDefinition> {
  return request<AnimationDefinition>(`${API_BASE}/animations/${animationId}`);
}

/** Parameters are validated server-side before any step is generated. */
export function requestAnimationSpec(
  animationId: string,
  params: Record<string, unknown>,
): Promise<AnimationSpec> {
  return request<AnimationSpec>(
    `${API_BASE}/animations/${animationId}/spec`,
    { method: "POST", body: JSON.stringify({ params }) },
    true,
  );
}
