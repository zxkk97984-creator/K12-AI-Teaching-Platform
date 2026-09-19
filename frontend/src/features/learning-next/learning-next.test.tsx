import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const navigate = vi.fn();

vi.mock("../identity/session", () => ({ navigate: (path: string) => navigate(path) }));
vi.mock("./api", () => ({
  getNextStep: vi.fn(),
  refreshNextStep: vi.fn(),
  postFeedback: vi.fn(),
  getEvidenceDetail: vi.fn(),
}));

import { ApiError } from "../identity/api";
import * as api from "./api";
import { NextStepPage } from "./NextStepPage";
import type { FeedbackDTO, NextStepDTO, NextStepItem } from "./types";

const EVIDENCE_ID = "11111111-1111-1111-1111-111111111111";

function item(overrides: Partial<NextStepItem> = {}): NextStepItem {
  return {
    kind: "REVIEW_MISTAKE",
    subject_key: "objective:fixture-objective",
    title: "先复盘错题，再做一组同类练习",
    reason: "这个目标有 1 次真实答错、还没有完全改正；下一步先看解析再练，不会直接加难度。",
    source: { type: "OBJECTIVE", objective_id: "fixture-objective" },
    evidence_ids: [EVIDENCE_ID],
    action: { type: "OPEN_PRACTICE", objective_id: "fixture-objective" },
    rule_version: "k12.recommendation.rule.v1",
    thresholds_version: "k12.recommendation.thresholds.v1",
    effect_verified: false,
    ...overrides,
  };
}

function body(overrides: Partial<NextStepDTO> = {}): NextStepDTO {
  return {
    primary: item(),
    alternatives: [],
    basis: {
      stage: "PRIMARY_LOWER",
      grade: 2,
      active_lesson_id: null,
      active_phase: null,
      real_answers: 1,
      hints_or_skips_only: false,
      evidence_ids: [EVIDENCE_ID],
      active_memory_ids: [],
      ignored_subjects: [],
      rule_version: "k12.recommendation.rule.v1",
      thresholds_version: "k12.recommendation.thresholds.v1",
      effect_verified: false,
    },
    rule_version: "k12.recommendation.rule.v1",
    thresholds_version: "k12.recommendation.thresholds.v1",
    effect_verified: false,
    honest_notes: [
      "这是按设计规则给出的下一步，不是经过实证验证的教学效果。",
      "提示、跳过和阅读时长都不算掌握；证据不足时会直接说明。",
      "没有排行榜，也不会给出掌握度百分比或人格/智力推断。",
    ],
    inputs_hash: "abc",
    snapshot_state: "CURRENT",
    needs_projection: false,
    needs_refresh: false,
    snapshot: { id: "22222222-2222-2222-2222-222222222222", source_revision: 1, created_at: "now" },
    ignored_subjects: [],
    cold_start: false,
    feedback: [],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getNextStep).mockResolvedValue(body());
  vi.mocked(api.getEvidenceDetail).mockResolvedValue({
    id: EVIDENCE_ID,
    source_kind: "QUIZ_ANSWERED",
    outcome: "INCORRECT",
    objective_id: "fixture-objective",
    source_ref: { question_id: "33333333-3333-3333-3333-333333333333", quiz_session_id: "quiz" },
    observed_at: "2026-09-19T12:00:00+00:00",
    summary: "题目作答：答错 · 目标「fixture-objective」 · 题目 33333333",
    rule_version: "k12.evidence.projection.v1",
  });
});

afterEach(() => {
  cleanup();
});

describe("next step page (T19 L2/L3/L9/L11)", () => {
  it("renders the server decision with reason, source and rule version", async () => {
    render(<NextStepPage />);
    await screen.findByTestId("next-primary");
    expect(screen.getByTestId("next-kind").textContent).toContain("错题复习");
    expect(screen.getByTestId("next-reason").textContent).toContain("真实答错");
    expect(screen.getByTestId("next-source").textContent).toContain("fixture-objective");
    expect(screen.getByTestId("next-not-verified").textContent).toContain("未验证教学效果");
  });

  it("shows the evidence behind the advice through the shared evidence API", async () => {
    render(<NextStepPage />);
    await screen.findByTestId("next-primary");
    fireEvent.click(screen.getByTestId(`next-evidence-open-${EVIDENCE_ID}`));
    const summary = await screen.findByTestId("next-evidence-summary");
    expect(api.getEvidenceDetail).toHaveBeenCalledWith(EVIDENCE_ID);
    expect(summary.textContent).toContain("题目作答：答错");
  });

  it("says out loud when the projection is behind instead of pretending it is current", async () => {
    vi.mocked(api.getNextStep).mockResolvedValue(
      body({ snapshot_state: "STALE", needs_refresh: true, needs_projection: true, cold_start: true }),
    );
    render(<NextStepPage />);
    await screen.findByTestId("next-needs-refresh");
    expect(screen.getByTestId("next-state").textContent).toContain("还没跟上");
    expect(screen.getByTestId("next-state").textContent).toContain("还没有你的真实学习记录");
  });

  it("refreshes only on an explicit click and reports the idempotent result", async () => {
    vi.mocked(api.getNextStep).mockResolvedValue(
      body({ snapshot_state: "NOT_PROJECTED", needs_refresh: true }),
    );
    vi.mocked(api.refreshNextStep).mockResolvedValue(
      body({ projection: { created: false, inputs_hash: "abc", source_revision: 1 } }),
    );
    render(<NextStepPage />);
    expect(api.refreshNextStep).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId("next-refresh"));
    await waitFor(() => expect(api.refreshNextStep).toHaveBeenCalledTimes(1));
    expect((await screen.findByTestId("next-notice-last")).textContent).toContain(
      "重复整理不会重复创建",
    );
  });

  it("ignores and restores the suggestion through the real API with its revision", async () => {
    vi.mocked(api.postFeedback).mockResolvedValue({
      subject_key: "objective:fixture-objective",
      state: "IGNORED",
      revision: 1,
      reason: null,
      updated_at: "now",
    } as FeedbackDTO);
    render(<NextStepPage />);
    fireEvent.click(await screen.findByTestId("next-ignore"));
    await waitFor(() =>
      expect(api.postFeedback).toHaveBeenCalledWith("objective:fixture-objective", "IGNORE", 0),
    );
  });

  it("restores an ignored suggestion from the feedback list", async () => {
    vi.mocked(api.getNextStep).mockResolvedValue(
      body({
        primary: item({
          kind: "ALL_IGNORED",
          subject_key: "recommendation:all-ignored",
          title: "你已经忽略了目前的建议",
          reason: "这里没有其它可推荐的下一步了；可以在下面恢复被忽略的建议。",
          source: { type: "STUDENT_FEEDBACK" },
          evidence_ids: [],
          action: {},
        }),
        ignored_subjects: ["objective:fixture-objective"],
        feedback: [
          {
            subject_key: "objective:fixture-objective",
            state: "IGNORED",
            revision: 2,
            reason: null,
            updated_at: "now",
          },
        ],
      }),
    );
    vi.mocked(api.postFeedback).mockResolvedValue({
      subject_key: "objective:fixture-objective",
      state: "ACTIVE",
      revision: 3,
      reason: null,
      updated_at: "now",
    } as FeedbackDTO);
    render(<NextStepPage />);
    fireEvent.click(await screen.findByTestId("next-feedback-restore"));
    await waitFor(() =>
      expect(api.postFeedback).toHaveBeenCalledWith("objective:fixture-objective", "RESTORE", 2),
    );
  });

  it("surfaces a real conflict when the feedback revision is stale", async () => {
    vi.mocked(api.postFeedback).mockRejectedValue(
      new ApiError(
        409,
        "REVISION_CONFLICT",
        "RECOMMENDATION_FEEDBACK_CONFLICT: 推荐状态已被更新，请刷新后重试",
        null,
      ),
    );
    render(<NextStepPage />);
    fireEvent.click(await screen.findByTestId("next-ignore"));
    const error = await screen.findByTestId("next-error");
    expect(error.textContent).toContain("建议状态已经更新");
    expect(error.textContent).toContain("推荐状态已被更新");
  });

  it("shows a readable error and no invented advice when the API fails", async () => {
    vi.mocked(api.getNextStep).mockRejectedValue(
      new ApiError(503, "SERVICE_UNAVAILABLE", "建议服务暂时不可用", null),
    );
    render(<NextStepPage />);
    expect((await screen.findByTestId("next-error")).textContent).toContain("建议服务暂时不可用");
    expect(screen.queryByTestId("next-primary")).toBeNull();
    expect(screen.queryByTestId("next-title")).toBeNull();
  });

  it("keeps the page free of rankings, percentages and personality claims", async () => {
    render(<NextStepPage />);
    await screen.findByTestId("next-primary");
    // No numeric mastery/rank/trait claim; the page must also say so out loud
    // (the words only appear inside those honest disclaimers).
    const text = document.body.textContent ?? "";
    expect(text).not.toContain("%");
    for (const pattern of [
      /排行榜[：:]?\s*第?\s*\d/,
      /正确率[：:]\s*\d/,
      /掌握度[：:]\s*\d/,
      /智商\s*\d+/,
      /性格[\u4e00-\u9fa5]{0,6}[：:]\s*\d/,
      /学习天数/,
      /连续打卡/,
    ]) {
      expect(text).not.toMatch(pattern);
    }
    expect(text).toContain("不是经过实证验证的教学效果");
    expect(text).toContain("没有排行榜");
  });

  it("keeps an honest empty state when there is no content to recommend", async () => {
    vi.mocked(api.getNextStep).mockResolvedValue(
      body({
        cold_start: true,
        primary: item({
          kind: "NO_CONTENT",
          subject_key: "content:none",
          title: "当前没有可用的已发布章节",
          reason: "你的学段暂时没有已发布且适龄的章节，老师会在内容发布后再推荐。",
          source: { type: "CATALOGUE", stage: "PRIMARY_LOWER" },
          evidence_ids: [],
          action: {},
        }),
      }),
    );
    render(<NextStepPage />);
    await screen.findByTestId("next-primary");
    expect(screen.getByTestId("next-no-evidence").textContent).toContain("来自课程目录");
    expect(screen.queryByTestId("next-action")).toBeNull();
  });
});
