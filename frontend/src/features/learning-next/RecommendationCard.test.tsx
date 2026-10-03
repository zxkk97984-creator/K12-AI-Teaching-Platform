import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getNextStep, refreshNextStep } from "./api";
import { RecommendationCard } from "./RecommendationCard";
import { actionHref, type NextStepDTO } from "./types";

vi.mock("./api", () => ({ getNextStep: vi.fn(), refreshNextStep: vi.fn() }));
const advice: NextStepDTO = {
  primary: { kind: "REVIEW_MISTAKE", subject_key: "objective:loop", title: "先复盘错题，再练一次",
    reason: "这个目标有 1 道题最近一次仍答错，先看解析再练习。", source: { type: "OBJECTIVE" },
    evidence_ids: ["evidence-1"], action: { type: "OPEN_PRACTICE", quiz_session_id: "quiz-1", question_position: 2, quiz_status: "COMPLETED", quiz_title: "条件与循环" },
    rule_version: "v2", thresholds_version: "v1", effect_verified: false },
  alternatives: [], basis: { stage: "JUNIOR", grade: 8, active_lesson_id: null, active_phase: null,
    real_answers: 1, hints_or_skips_only: false, evidence_ids: ["evidence-1"], active_memory_ids: [],
    ignored_subjects: [], rule_version: "v2", thresholds_version: "v1", effect_verified: false },
  rule_version: "v2", thresholds_version: "v1", effect_verified: false, honest_notes: [],
  inputs_hash: "hash", snapshot_state: "CURRENT", needs_projection: false, needs_refresh: false,
  snapshot: null, ignored_subjects: [], cold_start: false, feedback: [],
};
beforeEach(() => { vi.resetAllMocks(); vi.mocked(getNextStep).mockResolvedValue(advice); });
afterEach(cleanup);

describe("home learning recommendation", () => {
  it("opens the exact owned question and keeps reads side-effect free", async () => {
    render(<RecommendationCard />);
    expect((await screen.findByRole("link", { name: "查看结果与解析 →" })).getAttribute("href"))
      .toBe("/practice/sessions/quiz-1?q=2&returnTo=%2Fworkbench");
    expect(screen.getByText(advice.primary.reason)).toBeTruthy();
    expect(refreshNextStep).not.toHaveBeenCalled();
    expect(actionHref({ ...advice.primary, action: { type: "OPEN_PRACTICE", objective_id: "unknown" } })).toBeNull();
  });

  it("uses the real active state for start versus resume", async () => {
    vi.mocked(getNextStep).mockResolvedValue({ ...advice, primary: { ...advice.primary, action: { ...advice.primary.action, quiz_status: "ACTIVE", quiz_answered: 1 } } });
    render(<RecommendationCard />);
    expect(await screen.findByRole("link", { name: "继续练习 →" })).toBeTruthy();
    expect(screen.getByText("练习：条件与循环")).toBeTruthy();
  });

  it("does not present unprojected history as current and refreshes explicitly", async () => {
    vi.mocked(getNextStep).mockResolvedValue({ ...advice, needs_projection: true });
    vi.mocked(refreshNextStep).mockResolvedValue(advice);
    render(<RecommendationCard />);
    await screen.findByText(/有学习记录尚未整理/);
    expect(screen.queryByRole("link", { name: "查看结果与解析 →" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "更新建议" }));
    await screen.findByRole("link", { name: "查看结果与解析 →" });
    expect(refreshNextStep).toHaveBeenCalledTimes(1);
  });

  it("keeps unavailable recommendations honest and retryable", async () => {
    vi.mocked(getNextStep).mockRejectedValue(new Error("offline"));
    vi.mocked(refreshNextStep).mockResolvedValue(advice);
    render(<RecommendationCard />);
    expect((await screen.findByRole("alert")).textContent).toContain("仍可以继续");
    fireEvent.click(screen.getByRole("button", { name: "重试建议" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    await screen.findByRole("link", { name: "查看结果与解析 →" });
  });
});
