/** Student quiz API client (T17) — the only place the practice UI talks HTTP. */

import { ApiError, ensureCsrfToken } from "../identity/api";
import type {
  AnswerResultDTO,
  HintResultDTO,
  QuizAnswer,
  QuizReviewDTO,
  QuizResultDTO,
  QuizSessionDTO,
  QuizSessionListDTO,
  QuizSessionSummaryListDTO,
} from "./types";

const API_BASE = "/api/v1";

export type StudentGenerationJob = {
  id: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "REJECTED" | "FAILED";
  error_code: string | null;
  error_detail?: string | null;
  quiz_session_id: string | null;
  source_conversation_id?: string | null;
  source_message_id?: string | null;
  chapter_id?: string | null;
  fixture?: boolean;
  request_summary?: { topic?: string; count?: number; generated_count?: number; chapter_id?: string | null };
};
export type ConversationQuizOptions = {
  stage: string;
  max_question_count: number;
  allowed_difficulties: string[];
  allowed_question_types: string[];
};

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

export function listQuizSessions(status?: "ACTIVE" | "COMPLETED", favoriteOnly = false): Promise<QuizSessionListDTO> {
  const query = new URLSearchParams();
  if (status) query.set("status_filter", status);
  if (favoriteOnly) query.set("favorite_only", "true");
  return request<QuizSessionListDTO>(`${API_BASE}/quiz-sessions${query.size ? `?${query}` : ""}`);
}

export function listQuizSummaries(limit = 3): Promise<QuizSessionSummaryListDTO> {
  return request<QuizSessionSummaryListDTO>(
    `${API_BASE}/quiz-sessions?view=summary&limit=${limit}`,
  );
}

export function repeatQuizSession(sessionId: string): Promise<QuizSessionDTO> {
  return request<QuizSessionDTO>(
    `${API_BASE}/quiz-sessions/${encodeURIComponent(sessionId)}/repeat`,
    { method: "POST", body: JSON.stringify({}) },
    true,
  );
}

export function setQuizFavorite(sessionId: string, favorite: boolean): Promise<{ is_favorite: boolean }> {
  return request(`${API_BASE}/quiz-sessions/${encodeURIComponent(sessionId)}/favorite`, {
    method: favorite ? "PUT" : "DELETE",
  }, true);
}

export function saveQuizDraft(
  sessionId: string,
  questionId: string,
  answer: QuizAnswer,
  baseRevision = 0,
): Promise<{ draft: { question_id: string; answer: QuizAnswer; revision: number; updated_at: string }; last_submitted_answer: QuizAnswer | null }> {
  return request(`${API_BASE}/quiz-sessions/${encodeURIComponent(sessionId)}/questions/${encodeURIComponent(questionId)}/draft`, {
    method: "PUT",
    body: JSON.stringify({ answer, base_revision: baseRevision }),
  }, true);
}

export function saveQuizPosition(sessionId: string, position: number): Promise<{ position: number }> {
  return request(`${API_BASE}/quiz-sessions/${encodeURIComponent(sessionId)}/position`, {
    method: "PATCH",
    body: JSON.stringify({ position }),
  }, true);
}

export function getQuizHistory(sessionId: string): Promise<{ quiz_session_id: string; attempts: unknown[]; code_submissions: unknown[] }> {
  return request(`${API_BASE}/quiz-sessions/${encodeURIComponent(sessionId)}/history`);
}

export function generateQuiz(
  chapterId: string,
  idempotencyKey: string,
): Promise<{ job: { id: string; status: string; error_code: string | null }; quiz: QuizSessionDTO | null }> {
  return request(`${API_BASE}/quiz-generation-jobs`, {
    method: "POST",
    body: JSON.stringify({ chapter_id: chapterId, idempotency_key: idempotencyKey }),
  }, true);
}

export function getQuizGenerationJob(jobId: string): Promise<{
  job: StudentGenerationJob;
}> {
  return request(`${API_BASE}/quiz-generation-jobs/${encodeURIComponent(jobId)}`);
}

export function listConversationQuizJobs(conversationId: string): Promise<{ items: StudentGenerationJob[] }> {
  return request(`${API_BASE}/quiz-generation-jobs?conversation_id=${encodeURIComponent(conversationId)}`);
}

export function generateCompanionQuiz(input: {
  conversationId: string; message: string; scene: import("../conversation/types").SceneSnapshot;
  count: number; topic?: string; difficulty: string; idempotencyKey: string;
}): Promise<{ job: StudentGenerationJob; quiz: QuizSessionDTO | null }> {
  return request(`${API_BASE}/quiz-generation-jobs`, { method: "POST", body: JSON.stringify({
    conversation_id: input.conversationId, student_request: input.message,
    scene: input.scene, ordinary_question_count: input.count,
    knowledge_point: input.topic, difficulty: input.difficulty, idempotency_key: input.idempotencyKey,
  }) }, true);
}

export function retryQuizGeneration(jobId: string): Promise<{ job: StudentGenerationJob }> {
  return request(`${API_BASE}/quiz-generation-jobs/${encodeURIComponent(jobId)}/retry`, { method: "POST" }, true);
}
export function getConversationQuizOptions(): Promise<ConversationQuizOptions> {
  return request(`${API_BASE}/quiz-options/conversation`);
}

export function generateConversationQuiz(input: {
  conversationId: string;
  messageId: string;
  knowledgePoint: string;
  idempotencyKey: string;
  questionCount: number;
  difficulty: string;
}): Promise<{ job: StudentGenerationJob; quiz: QuizSessionDTO | null }> {
  return request(`${API_BASE}/quiz-generation-jobs`, {
    method: "POST",
    body: JSON.stringify({
      conversation_id: input.conversationId,
      message_id: input.messageId,
      knowledge_point: input.knowledgePoint,
      idempotency_key: input.idempotencyKey,
      ordinary_question_count: input.questionCount,
      difficulty: input.difficulty,
    }),
  }, true);
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

export function getQuizResult(sessionId: string): Promise<QuizResultDTO> {
  return request<QuizResultDTO>(`${API_BASE}/quiz-sessions/${encodeURIComponent(sessionId)}/result`);
}
