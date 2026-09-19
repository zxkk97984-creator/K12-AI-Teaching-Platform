/** Student quiz API client (T17) — the only place the practice UI talks HTTP. */

import { ApiError, ensureCsrfToken } from "../identity/api";
import type {
  AnswerResultDTO,
  HintResultDTO,
  QuizAnswer,
  QuizReviewDTO,
  QuizSessionDTO,
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

/**
 * One explicit student click maps to exactly one create call. The frozen T16
 * route takes no idempotency key, so the client keeps a single-flight promise
 * per (chapter) and stores the returned id immediately: two racing clicks and
 * a StrictMode double effect reuse the same request instead of creating two
 * quiz sessions.
 */
const createInFlight = new Map<string, Promise<QuizSessionDTO>>();

export function createQuizSession(chapterId: string): Promise<QuizSessionDTO> {
  const running = createInFlight.get(chapterId);
  if (running) return running;
  const pending = request<QuizSessionDTO>(
    `${API_BASE}/quiz-sessions`,
    { method: "POST", body: JSON.stringify({ chapter_id: chapterId }) },
    true,
  ).finally(() => {
    createInFlight.delete(chapterId);
  });
  createInFlight.set(chapterId, pending);
  return pending;
}

export function getQuizSession(sessionId: string): Promise<QuizSessionDTO> {
  return request<QuizSessionDTO>(`${API_BASE}/quiz-sessions/${sessionId}`);
}

export function submitQuizAnswer(
  sessionId: string,
  questionId: string,
  answer: QuizAnswer,
  idempotencyKey: string,
): Promise<AnswerResultDTO> {
  return request<AnswerResultDTO>(
    `${API_BASE}/quiz-sessions/${sessionId}/questions/${questionId}/answers`,
    { method: "POST", body: JSON.stringify({ answer, idempotency_key: idempotencyKey }) },
    true,
  );
}

export function requestQuizHint(
  sessionId: string,
  questionId: string,
  level: number,
  idempotencyKey: string,
): Promise<HintResultDTO> {
  return request<HintResultDTO>(
    `${API_BASE}/quiz-sessions/${sessionId}/questions/${questionId}/hints`,
    { method: "POST", body: JSON.stringify({ level, idempotency_key: idempotencyKey }) },
    true,
  );
}

export function getQuizReview(sessionId: string): Promise<QuizReviewDTO> {
  return request<QuizReviewDTO>(`${API_BASE}/quiz-sessions/${sessionId}/review`);
}
