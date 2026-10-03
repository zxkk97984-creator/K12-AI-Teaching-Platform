import { ApiError, ensureCsrfToken } from "../identity/api";

export type LearningItem = {
  kind: "COURSE" | "RESOURCE" | "ANIMATION";
  id: string;
  title: string;
  slug?: string | null;
  description: string;
  route: string;
  resource_type?: string | null;
  stage?: string | null;
  chapter_count?: number | null;
  is_textbook?: boolean;
  body_han_chars?: number | null;
  content_notice?: string | null;
  is_test_fixture?: boolean;
  available?: boolean;
  unavailable_reason?: string | null;
  created_at?: string | null;
  is_bookmarked?: boolean;
};
export function isStudentFacingLearningItem(item: Pick<LearningItem, "is_test_fixture" | "slug" | "title">): boolean {
  return !(item.is_test_fixture && (item.slug?.startsWith("t06-") || item.title.includes("非教学")));
}
export type HistoryItem = Omit<LearningItem, "kind" | "id" | "created_at"> & {
  kind: "READING" | "OPEN";
  target_kind: "COURSE" | "RESOURCE" | "ANIMATION";
  target_id: string;
  chapter_id?: string | null;
  block_id?: string | null;
  revision?: number | null;
  created_at: string;
};
export type Bookmark = LearningItem & { bookmarked_at: string };
export type ContinueItem = {
  chapter_id: string;
  course_id: string;
  course_title: string;
  chapter_title: string;
  block_id?: string | null;
  route: string;
  created_at: string;
  is_current_revision: boolean;
};

async function request<T>(path: string, init: RequestInit = {}, mutation = false): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (mutation) headers.set("X-CSRF-Token", await ensureCsrfToken());
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body?.error;
    throw new ApiError(response.status, error?.code ?? `HTTP_${response.status}`, error?.message ?? body?.detail ?? "请求失败", error?.request_id ?? null);
  }
  return body as T;
}

export function listCatalog(options: {
  q?: string;
  kind?: LearningItem["kind"];
  resourceType?: string;
  topic?: string;
  stage?: string;
  limit?: number;
  offset?: number;
} = {}, signal?: AbortSignal) {
  const params = new URLSearchParams();
  if (options.q?.trim()) params.set("q", options.q.trim());
  if (options.kind) params.set("kind", options.kind);
  if (options.resourceType) params.set("resource_type", options.resourceType);
  if (options.topic) params.set("topic", options.topic);
  if (options.stage) params.set("stage", options.stage);
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.offset !== undefined) params.set("offset", String(options.offset));
  const query = params.toString();
  return request<{ items: LearningItem[]; total: number; limit: number; offset: number }>(
    `/api/v1/learning/catalog${query ? `?${query}` : ""}`,
    { signal },
  );
}
export const getBookshelf = () => request<{ items: Bookmark[]; total: number }>("/api/v1/learning/bookshelf");
export const getHistory = () => request<{ items: HistoryItem[]; total: number }>("/api/v1/learning/history");
export const getContinue = () => request<{ item: ContinueItem | null }>("/api/v1/learning/continue");
export const addBookmark = (kind: LearningItem["kind"], id: string) => request<Bookmark>(`/api/v1/learning/bookshelf/${kind}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({}) }, true);
export const removeBookmark = (kind: LearningItem["kind"], id: string) => request<void>(`/api/v1/learning/bookshelf/${kind}/${encodeURIComponent(id)}`, { method: "DELETE" }, true);
export function newOpenEventId(kind: LearningItem["kind"], id: string): string {
  const random = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `open-${kind.toLowerCase()}-${id}-${random}`.slice(0, 64);
}

export const recordOpen = (
  kind: LearningItem["kind"],
  id: string,
  clientEventId = newOpenEventId(kind, id),
) => request(`/api/v1/learning/open-events`, { method: "POST", body: JSON.stringify({ target_kind: kind, target_id: id, client_event_id: clientEventId }) }, true);

export type PicturebookProgress = { story_id: string; page_index: number; updated_at: string | null };
export type StudentPicturebook = {
  id: string; title: string; subtitle: string; image: string; topic: string; question: string;
  version: string; is_test_fixture: boolean;
  pages: Array<{ title: string; text: string }>;
};
export type GuidedStudentAnimation = {
  id: string; title: string; subject: string; topic: string; stage: string;
  version: string; is_test_fixture: boolean; steps: string[];
};
export type StudentContent = {
  stage: string;
  picturebooks: StudentPicturebook[];
  guided_animation: GuidedStudentAnimation | null;
};
export const getStudentContent = (signal?: AbortSignal) => request<StudentContent>("/api/v1/learning/student-content", { signal });
export const getPicturebookProgress = (storyId: string) =>
  request<PicturebookProgress>(`/api/v1/learning/picturebooks/${encodeURIComponent(storyId)}/progress`);
export const savePicturebookProgress = (storyId: string, pageIndex: number) =>
  request<PicturebookProgress>(`/api/v1/learning/picturebooks/${encodeURIComponent(storyId)}/progress`, {
    method: "PUT", body: JSON.stringify({ page_index: pageIndex }),
  }, true);
