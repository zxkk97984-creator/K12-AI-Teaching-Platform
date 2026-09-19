import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const navigate = vi.fn();

vi.mock("../identity/session", () => ({ navigate: (path: string) => navigate(path) }));
vi.mock("./api", () => ({
  getGrowthOverview: vi.fn(),
  reprojectGrowth: vi.fn(),
  getEvidenceDetail: vi.fn(),
  listMemories: vi.fn(),
  getMemory: vi.fn(),
  postMemoryAction: vi.fn(),
}));

import { ApiError } from "../identity/api";
import * as api from "./api";
import { GrowthPage } from "./GrowthPage";
import type { GrowthOverviewDTO, MemoryDTO, ObservationDTO } from "./types";

const MEMORY_ID = "11111111-1111-1111-1111-111111111111";
const EVIDENCE_ID = "22222222-2222-2222-2222-222222222222";

function observation(overrides: Partial<ObservationDTO> = {}): ObservationDTO {
  return {
    id: "33333333-3333-3333-3333-333333333333",
    subject_kind: "OBJECTIVE",
    subject_key: "确认只填学段时仍能匹配章节",
    level: "EMERGING",
    statement: "目标「确认只填学段时仍能匹配章节」：已看到 2 次真实作答（1 次答对）。",
    basis: {
      evidence_ids: [EVIDENCE_ID],
      hint_evidence_ids: [],
      answered: 2,
      correct: 1,
      distinct_questions: 2,
      hints_viewed: 0,
      rule_version: "k12.observation.rule.v1",
      thresholds_version: "k12.observation.thresholds.v1",
      effect_verified: false,
    },
    rule_version: "k12.observation.rule.v1",
    projection_revision: 1,
    superseded_at: null,
    created_at: "2026-09-19T12:00:00+00:00",
    notice: "本地定性观察；不是掌握度百分比，也未验证教学效果。",
    ...overrides,
  };
}

function memory(overrides: Partial<MemoryDTO> = {}): MemoryDTO {
  return {
    id: MEMORY_ID,
    kind: "STUDY_STRATEGY",
    status: "CANDIDATE",
    statement: "答错后愿意再试一次：你在同一道题上从答错改到了答对。",
    content: {},
    basis_evidence_ids: [EVIDENCE_ID],
    basis_counts: { attempts_on_question: 2 },
    rule_version: "k12.memory.rule.v1",
    origin: "RULE_DERIVED",
    revision: 1,
    injection_status: "EXCLUDED",
    injection_note: "这是系统建议的候选记忆，只有你确认后才会作为教学参考。",
    local_withdrawal_notice: null,
    remote_residue: "NONE_LOCAL_ONLY",
    decided_at: null,
    removed_at: null,
    created_at: "2026-09-19T12:00:00+00:00",
    updated_at: "2026-09-19T12:00:00+00:00",
    history: [
      {
        id: "44444444-4444-4444-4444-444444444444",
        action: "CREATE",
        from_status: "NONE",
        to_status: "CANDIDATE",
        from_revision: 0,
        to_revision: 1,
        statement_before: null,
        statement_after: "答错后愿意再试一次：你在同一道题上从答错改到了答对。",
        reason: null,
        actor: "STUDENT",
        created_at: "2026-09-19T12:00:00+00:00",
      },
    ],
    ...overrides,
  };
}

function overview(overrides: Partial<GrowthOverviewDTO> = {}): GrowthOverviewDTO {
  return {
    owner_scoped: true,
    evidence_total: 2,
    evidence_by_kind: { QUIZ_ANSWERED: 2 },
    real_answers: 2,
    correct_answers: 1,
    observations: [observation()],
    memories: [memory()],
    insufficient_evidence: false,
    counts_not_effect_notice:
      "记录条数只是本地记录，不代表学习效果；证据不足时会明确写「仍需观察」。",
    no_percentage_notice: "本页不生成掌握度百分比，也不推断智力或性格。",
    needs_projection: false,
    projection_rule_version: "k12.evidence.projection.v1",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getGrowthOverview).mockResolvedValue(overview());
  vi.mocked(api.listMemories).mockResolvedValue({
    items: [memory()],
    notice: "记忆由你掌控。",
  });
  vi.mocked(api.getEvidenceDetail).mockResolvedValue({
    id: EVIDENCE_ID,
    source_kind: "QUIZ_ANSWERED",
    outcome: "CORRECT",
    objective_id: "obj-1",
    knowledge_point_slugs: ["fixture-notice"],
    source_ref: { question_id: "55555555-5555-5555-5555-555555555555", quiz_session_id: "quiz" },
    rule_version: "k12.evidence.projection.v1",
    observed_at: "2026-09-19T12:00:00+00:00",
    projected_at: "2026-09-19T12:00:05+00:00",
    summary: "题目作答：答对 · 目标「obj-1」 · 题目 55555555",
  });
  vi.mocked(api.postMemoryAction).mockImplementation(async (_id, action) =>
    memory({ status: action === "CONFIRM" ? "ACTIVE" : action === "DISPUTE" ? "DISPUTED" : "REMOVED", revision: 2 }),
  );
});

afterEach(() => {
  cleanup();
});

describe("growth page (T18 K4/K6/K7/K11)", () => {
  it("renders only server facts and never invents a statistic", async () => {
    render(<GrowthPage />);
    await screen.findByTestId("growth-summary");
    expect(screen.getByTestId("growth-real-answers").textContent).toContain("2");
    expect(screen.getByTestId("growth-correct-answers").textContent).toContain("1");
    expect(screen.getByTestId("growth-notice").textContent).toContain("记录条数不是学习效果");

    // No numeric mastery/percentage/trait claim may be rendered; the page is
    // required to say out loud that it does not produce one. (The words
    // themselves appear only inside those honest disclaimers.)
    const body = document.body.textContent ?? "";
    const claimPatterns = [
      /掌握度[：:]\s*\d/,
      /正确率[：:]\s*\d/,
      /智商\s*\d+/,
      /性格[\u4e00-\u9fa5]{0,6}[：:]\s*\d/,
      /学习天数/,
      /连续打卡/,
      /积分/,
      /排行榜/,
    ];
    for (const pattern of claimPatterns) {
      expect(body).not.toMatch(pattern);
    }
    expect(body).not.toContain("%");
    expect(body).toContain("不会生成掌握度百分比");
    expect(body).toContain("不代表学习效果");
  });

  it("shows an honest empty state instead of fake activity", async () => {
    vi.mocked(api.getGrowthOverview).mockResolvedValue(
      overview({
        evidence_total: 0,
        evidence_by_kind: {},
        real_answers: 0,
        correct_answers: 0,
        observations: [],
        memories: [],
        insufficient_evidence: true,
        needs_projection: true,
      }),
    );
    vi.mocked(api.listMemories).mockResolvedValue({ items: [], notice: "记忆由你掌控。" });
    render(<GrowthPage />);
    await screen.findByTestId("growth-observations-empty");
    expect(screen.getByTestId("growth-insufficient").textContent).toContain("仍需观察");
    expect(screen.getByTestId("growth-memories-empty")).toBeTruthy();
    expect(screen.getByTestId("growth-needs-projection")).toBeTruthy();
  });

  it("loads the real source behind an observation on demand", async () => {
    render(<GrowthPage />);
    await screen.findByTestId("growth-observation");
    fireEvent.click(screen.getByTestId(`growth-evidence-open-${EVIDENCE_ID}`));
    const detail = await screen.findByTestId("growth-evidence-detail");
    expect(api.getEvidenceDetail).toHaveBeenCalledWith(EVIDENCE_ID);
    expect(detail.textContent).toContain("题目作答：答对");
    expect(detail.textContent).toContain("题目 55555555");
  });

  it("sends the student's revision with every memory action", async () => {
    render(<GrowthPage />);
    fireEvent.click(await screen.findByTestId("growth-memory-confirm"));
    await waitFor(() => expect(api.postMemoryAction).toHaveBeenCalled());
    expect(api.postMemoryAction).toHaveBeenCalledWith(MEMORY_ID, "CONFIRM", 1, {});
  });

  it("keeps the previous version visible after an edit", async () => {
    vi.mocked(api.postMemoryAction).mockResolvedValue(
      memory({
        status: "ACTIVE",
        revision: 3,
        statement: "我会先看提示，然后再自己作答。",
        history: [
          ...memory().history,
          {
            id: "66666666-6666-6666-6666-666666666666",
            action: "EDIT",
            from_status: "ACTIVE",
            to_status: "ACTIVE",
            from_revision: 2,
            to_revision: 3,
            statement_before: "答错后愿意再试一次：你在同一道题上从答错改到了答对。",
            statement_after: "我会先看提示，然后再自己作答。",
            reason: null,
            actor: "STUDENT",
            created_at: "2026-09-19T12:10:00+00:00",
          },
        ],
      }),
    );
    render(<GrowthPage />);
    fireEvent.click(await screen.findByTestId("growth-memory-edit"));
    fireEvent.change(screen.getByTestId("growth-memory-edit-input"), {
      target: { value: "我会先看提示，然后再自己作答。" },
    });
    fireEvent.click(screen.getByTestId("growth-memory-edit-save"));
    await waitFor(() =>
      expect(api.postMemoryAction).toHaveBeenCalledWith(MEMORY_ID, "EDIT", 1, {
        statement: "我会先看提示，然后再自己作答。",
      }),
    );
    expect((await screen.findByTestId("growth-memory-statement")).textContent).toContain(
      "我会先看提示",
    );
    expect(screen.getByTestId("growth-memory").textContent).toContain("修订 3");
  });

  it("surfaces a real conflict when the revision is stale", async () => {
    vi.mocked(api.postMemoryAction).mockRejectedValue(
      new ApiError(409, "REVISION_CONFLICT", "MEMORY_REVISION_CONFLICT: 这条记忆已被更新，请刷新后重试", null),
    );
    render(<GrowthPage />);
    fireEvent.click(await screen.findByTestId("growth-memory-confirm"));
    const error = await screen.findByTestId("growth-error");
    expect(error.textContent).toContain("已经被更新过，请刷新后再操作");
    expect(error.textContent).toContain("这条记忆已被更新");
  });

  it("explains the local withdrawal scope after forgetting", async () => {
    vi.mocked(api.postMemoryAction).mockResolvedValue(
      memory({
        status: "REMOVED",
        revision: 2,
        injection_status: "EXCLUDED",
        injection_note: "本地已遗忘：不再注入教学上下文。",
        local_withdrawal_notice:
          "本地已遗忘：不再注入教学上下文。当前版本没有远端记忆同步，因此不存在远端副本；若将来接入平台侧记忆，需要按平台能力单独发起撤回，本状态不宣称物理清除了其它系统里的记录。",
        remote_residue: "NONE_LOCAL_ONLY",
      }),
    );
    render(<GrowthPage />);
    fireEvent.click(await screen.findByTestId("growth-memory-forget"));
    const withdrawal = await screen.findByTestId("growth-memory-withdrawal");
    expect(withdrawal.textContent).toContain("不再注入教学上下文");
    expect(withdrawal.textContent).toContain("不宣称物理清除了其它系统里的记录");
    expect(screen.queryByTestId("growth-memory-confirm")).toBeNull();
    expect(screen.queryByTestId("growth-memory-forget")).toBeNull();
  });

  it("reprojects only on an explicit click and reports the idempotent result", async () => {
    vi.mocked(api.getGrowthOverview).mockResolvedValue(overview({ needs_projection: true }));
    vi.mocked(api.reprojectGrowth).mockResolvedValue(
      overview({
        needs_projection: false,
        projection: {
          evidence: { scanned: 3, inserted: 1, rule_version: "k12.evidence.projection.v1" },
          observations: {
            objectives: 1,
            created: 1,
            reused: 0,
            rule_version: "k12.observation.rule.v1",
          },
          memories: { created: 1, skipped: 0, rule_version: "k12.memory.rule.v1" },
        },
      }),
    );
    render(<GrowthPage />);
    expect(api.reprojectGrowth).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId("growth-reproject"));
    await waitFor(() => expect(api.reprojectGrowth).toHaveBeenCalledTimes(1));
    const notice = await screen.findByTestId("growth-notice-last");
    expect(notice.textContent).toContain("新增依据 1 条");
    expect(notice.textContent).toContain("重复整理不会重复计数");
  });
});
