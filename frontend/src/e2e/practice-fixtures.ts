import { type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { fixture } from "./ui-reuse-fixtures";
import type { QuizSessionDTO } from "../features/quiz/types";
const date = "2026-10-03T06:00:00Z";
export function quiz(id: string, completed = false, count = 1): QuizSessionDTO {
  return { id, draft_id: id === "older" ? "done" : id, source_title: "观察石子与水面的变化", chapter_id: null, revision_id: null, curriculum_revision: "synthetic-ui", stage: "PRIMARY_LOWER", status: completed ? "COMPLETED" : "ACTIVE", source_kind: "AI_DRAFT", source_label: "AI 生成草稿，未人工审校，仅供个人练习", difficulty: "EASY", question_count: count, max_attempts: 2, max_hints: 3, scoring_version: "synthetic", thresholds_version: "synthetic", base_revision: 1, created_at: date, completed_at: completed ? date : null, current_position: count > 1 ? 1 : 0, progress: { answered: completed ? count : 0, correct: completed ? count : 0, total: count }, notices: [], is_favorite: completed, questions: Array.from({ length: count }, (_, position) => ({ id: `${id}-q${position}`, question_key: `q${position}`, position, type: position === 2 ? "ORDERING" : "TRUE_FALSE", stem: position === 2 ? "先观察，再提出问题，最后验证。请排好顺序。" : "石子占据空间，会让水面升高。", source_refs: [], hint_limit: 3, hints_used: 0, hints: [], attempts_used: completed ? 1 : 0, max_attempts: 2, options: [{ key: "TRUE", text: "对" }, { key: "FALSE", text: "错" }], items: [{ key: "observe", text: "观察" }, { key: "ask", text: "提出问题" }, { key: "check", text: "验证" }], ...(completed ? { feedback: { outcome: "CORRECT", is_correct: true, correct_answer: true, explanation: "石子占据了原本由水占据的空间。", attempts_used: 1, max_attempts: 2 } } : {}) })) };
}

export async function setup(page: Page, stage: QuizSessionDTO["stage"] = "PRIMARY_LOWER") {
  const state = await fixture(page, { stage, interactive: true, interactivePurpose: "GAME" });
  const items = [quiz("active", false, 3), quiz("done", true), quiz("older", true)].map(item => ({...item,stage}));
  let creates = 0, failDraft = false, historyReads = 0;
  page.on("request", request => { if (request.method() === "GET" && new URL(request.url()).pathname === "/api/v1/interactive/sessions") historyReads++; });
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/v1/quiz-sessions**", async route => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    const path = url.pathname.slice("/api/v1/quiz-sessions".length);
    const id = path.split("/")[1];
    const current = items.find(item => item.id === id);
    const json = (body: unknown, status = 200) => route.fulfill({ json: body, status });
    if (!path && method === "GET") return json({ items, total: items.length });
    if (!current) return json({ error: { code: "NOT_FOUND", message: "练习不存在或无权访问" } }, 404);
    if (path.endsWith("/repeat")) { creates++; const fresh = quiz(`repeat-${creates}`); fresh.draft_id = current.draft_id; items.unshift(fresh); return json(fresh, 201); }
    if (path.endsWith("/favorite")) { current.is_favorite = method === "PUT"; return json({ is_favorite: current.is_favorite }); }
    if (path.endsWith("/review")) return json({ session_id: id, items: [], notice: "合成测试", thresholds_version: "synthetic", scoring_version: "synthetic" });
    if (path.endsWith("/result")) return json({ session_id: id, status: "COMPLETED", total: current.question_count, correct: current.progress.correct, first_correct: current.progress.correct, score_percent: 100, completed_at: date, scoring_version: "synthetic", questions: current.questions.map(item => ({ ...item, first_answer: true, last_answer: true, first_correct: true, is_correct: true, correct_answer: true, explanation: "石子占据了原本由水占据的空间。", code_result: null })) });
    if (path.endsWith("/position")) { current.current_position = route.request().postDataJSON().position; return json({ position: current.current_position }); }
    if (path.endsWith("/draft")) {
      if (failDraft) return json({ error: { code: "SAVE_FAILED", message: "草稿保存失败，请重试" } }, 503);
      const payload = route.request().postDataJSON();
      const questionId = path.split("/")[3];
      const draft = { answer: payload.answer, revision: payload.base_revision + 1, updated_at: date };
      current.drafts = { ...current.drafts, [questionId]: draft }; return json({ draft });
    }
    return json(current);
  });
  await mkdir("test-results/page-density", { recursive: true });
  return { state, items, errors, creates: () => creates, historyReads: () => historyReads, failDraft: () => { failDraft = true; } };
}
