import type {
  AuthResponse,
  LoginRequest,
  MeResponse,
  PreferencesPatch,
  ProfilePatch,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;

  constructor(status: number, code: string, message: string, requestId: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

type ErrorEnvelope = {
  error?: { code?: string; message?: string; request_id?: string };
};

function cookieValue(name: string): string | null {
  const prefix = `${name}=`;
  const item = document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

export async function ensureCsrfToken(): Promise<string> {
  const existing = cookieValue("sl_csrf");
  if (existing) return existing;
  const response = await fetch("/api/v1/auth/csrf", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new ApiError(response.status, "CSRF_UNAVAILABLE", "无法建立会话保护", null);
  const body = (await response.json()) as { csrf_token: string };
  return body.csrf_token;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  options: { authenticated?: boolean; mutation?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (options.mutation) headers.set("X-CSRF-Token", await ensureCsrfToken());
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
    if (response.status === 401 && options.authenticated !== false) {
      window.dispatchEvent(new CustomEvent("identity:unauthorized", { detail: error }));
    }
    throw error;
  }
  return body as T;
}

export async function login(input: LoginRequest): Promise<AuthResponse> {
  return request<AuthResponse>(
    "/api/v1/auth/login",
    { method: "POST", body: JSON.stringify(input) },
    { authenticated: false, mutation: true },
  );
}

export async function logout(): Promise<void> {
  await request<void>("/api/v1/auth/logout", { method: "POST" }, { mutation: true });
}

export async function getMe(): Promise<MeResponse> {
  return request<MeResponse>("/api/v1/me");
}

export async function patchProfile(patch: ProfilePatch): Promise<MeResponse> {
  return request<MeResponse>(
    "/api/v1/me/profile",
    { method: "PATCH", body: JSON.stringify(patch) },
    { mutation: true },
  );
}

export async function patchPreferences(patch: PreferencesPatch): Promise<MeResponse> {
  return request<MeResponse>(
    "/api/v1/me/preferences",
    { method: "PATCH", body: JSON.stringify(patch) },
    { mutation: true },
  );
}
