import { ApiError, ensureCsrfToken } from "../identity/api";
import type {
  ChapterDetailDTO,
  CourseListDTO,
  CourseSummaryDTO,
  PageContextDTO,
  PageContextRequest,
  ReadingEventReceipt,
  ReadingEventRequest,
  ReadingStateDTO,
} from "./types";

const API_BASE = "/api/v1";

type ErrorEnvelope = { error?: { code?: string; message?: string; request_id?: string } };

/**
 * Content requests keep the T05 semantics (same-origin cookie, standard error
 * envelope, 401 informs the global identity listener) while the identity
 * request helper stays untouched in its own module.
 */
async function request<T>(
  path: string,
  init: RequestInit = {},
  options: { mutation?: boolean } = {},
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
    if (response.status === 401) {
      window.dispatchEvent(new CustomEvent("identity:unauthorized", { detail: error }));
    }
    throw error;
  }
  return body as T;
}

export async function listCourses(): Promise<CourseListDTO> {
  return request<CourseListDTO>(`${API_BASE}/courses`);
}

export async function getCourse(courseId: string): Promise<CourseSummaryDTO> {
  return request<CourseSummaryDTO>(`${API_BASE}/courses/${encodeURIComponent(courseId)}`);
}

export async function getChapter(
  chapterId: string,
  revision?: number,
): Promise<ChapterDetailDTO> {
  const suffix = revision ? `?revision=${revision}` : "";
  return request<ChapterDetailDTO>(
    `${API_BASE}/chapters/${encodeURIComponent(chapterId)}${suffix}`,
  );
}

export async function getReadingState(chapterId: string): Promise<ReadingStateDTO | null> {
  return request<ReadingStateDTO | null>(
    `${API_BASE}/chapters/${encodeURIComponent(chapterId)}/reading-state`,
  );
}

export async function postPageContext(payload: PageContextRequest): Promise<PageContextDTO> {
  return request<PageContextDTO>(
    `${API_BASE}/content/page-context`,
    { method: "POST", body: JSON.stringify(payload) },
    { mutation: true },
  );
}

export async function postReadingEvent(
  payload: ReadingEventRequest,
): Promise<ReadingEventReceipt> {
  return request<ReadingEventReceipt>(
    `${API_BASE}/reading-events`,
    { method: "POST", body: JSON.stringify(payload) },
    { mutation: true },
  );
}
