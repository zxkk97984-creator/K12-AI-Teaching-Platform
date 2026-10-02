import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, getMe } from "../identity/api";
import { getContinue, getHistory, getStudentContent, listCatalog } from "../study/api";
import { listQuizSummaries } from "../quiz/api";
import { listInteractive } from "../interactive/api";
import { listCodeTasks } from "../codelab/api";
import { WorkbenchShell } from "./WorkbenchShell";
import { WorkbenchPage } from "../../pages/workbench/WorkbenchPage";
import type { MeResponse, Stage } from "../identity/types";

vi.mock("../identity/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../identity/api")>();
  return { ...actual, getMe: vi.fn(), logout: vi.fn() };
});
vi.mock("../study/api", () => ({
  getContinue: vi.fn(), getHistory: vi.fn(), getStudentContent: vi.fn(), listCatalog: vi.fn(),
}));
vi.mock("../quiz/api", () => ({ listQuizSummaries: vi.fn() }));
vi.mock("../interactive/api", () => ({ listInteractive: vi.fn() }));
vi.mock("../codelab/api", () => ({ listCodeTasks: vi.fn() }));

function studentMe(stage: Stage | null = "JUNIOR"): MeResponse {
  return {
    user: { id: "00000000-0000-0000-0000-000000000001", username: "student", role: "student", is_active: true },
    profile: { stage, grade: null, revision: 3, onboarding_completed: !!stage },
    preferences: { preferred_style: "AUTO", teacher_style: "AUTO", companion_pet_id: "shuangling", interests: [], proactive_guidance_enabled: true, voice_preference: "DISABLED", auto_read_replies: false, profile_revision: 3 },
  };
}

beforeEach(() => {
  vi.mocked(getMe).mockReset();
  vi.mocked(listCatalog).mockReset().mockResolvedValue({ items: [], total: 0, limit: 12, offset: 0 });
  vi.mocked(getHistory).mockReset().mockResolvedValue({ items: [], total: 0 } as never);
  vi.mocked(getContinue).mockReset().mockResolvedValue({ item: null });
  vi.mocked(listQuizSummaries).mockReset().mockResolvedValue({ items: [], total: 0 });
  vi.mocked(getStudentContent).mockReset().mockResolvedValue({ stage: "JUNIOR", picturebooks: [], guided_animation: null });
  vi.mocked(listInteractive).mockReset().mockResolvedValue({ stage: "JUNIOR", items: [] });
  vi.mocked(listCodeTasks).mockReset().mockResolvedValue({
    items: [], total: 0, limit: 10, offset: 0, facets: { categories: [], difficulties: [] },
  });
});
afterEach(() => { cleanup(); document.title = ""; });

function renderHome(me = studentMe()) {
  return render(<MemoryRouter><WorkbenchShell me={me} /></MemoryRouter>);
}

describe("new student home", () => {
  it("uses its own layout and honest empty state", async () => {
    renderHome();
    expect(await screen.findByRole("heading", { name: "理解之后，再向前一步" })).toBeTruthy();
    expect(screen.getByText(/从一次小尝试开始/)).toBeTruthy();
    expect(screen.getByTestId("workbench-shell").classList.contains("study-page")).toBe(false);
    expect(screen.queryByText("在线编程")).toBeNull();
  });

  it("uses a server quiz summary as the continue target", async () => {
    vi.mocked(listQuizSummaries).mockResolvedValue({ items: [{ id: "quiz-1", chapter_id: null, source_conversation_id: "conv-1", title: "食物链 · 趣味练习", status: "ACTIVE", progress: { answered: 1, correct: 0, total: 3 }, created_at: "2026-09-23T10:00:00Z", completed_at: null }], total: 1 });
    renderHome();
    expect((await screen.findAllByRole("link", { name: /继续练习/ }))[0]).toHaveProperty("href", expect.stringContaining("/practice/sessions/quiz-1"));
    expect(screen.getAllByText(/已作答 1 \/ 3 题/).length).toBeGreaterThan(0);
  });

  it("renders stage-matched versioned picturebooks from the server", async () => {
    vi.mocked(getStudentContent).mockResolvedValue({ stage: "PRIMARY_LOWER", picturebooks: [{ id: "crow", title: "乌鸦喝水", subtitle: "换个办法", image: "/picturebooks/crow-pitcher.jpg", topic: "观察", question: "水面为什么升高？", version: "v1", is_test_fixture: true, pages: [] }], guided_animation: null });
    vi.mocked(listInteractive).mockResolvedValue({ stage: "PRIMARY_LOWER", items: [] });
    renderHome(studentMe("PRIMARY_LOWER"));
    expect(await screen.findByRole("heading", { name: "乌鸦喝水" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "开始阅读 →" }).getAttribute("href")).toBe("/picturebooks/crow");
  });

  it.each([
    ["PRIMARY_UPPER", "知识点与练习"],
    ["JUNIOR", "概念资料与专项练习"],
    ["SENIOR", "专题资料与推理巩固"],
  ] as const)("shows a distinct %s learning path", async (stage, heading) => {
    vi.mocked(getStudentContent).mockResolvedValue({ stage, picturebooks: [], guided_animation: null });
    vi.mocked(listInteractive).mockResolvedValue({ stage, items: [] });
    renderHome(studentMe(stage));
    expect(await screen.findByRole("region", { name: heading })).toBeTruthy();
    expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
  });

  it("reports an unavailable backend and retries", async () => {
    vi.mocked(listCatalog).mockRejectedValueOnce(new Error("offline"));
    renderHome();
    expect((await screen.findByRole("alert")).textContent).toContain("offline");
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });
});

describe("workbench page access", () => {
  it("shows the real home to a student", async () => {
    vi.mocked(getMe).mockResolvedValue(studentMe());
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>);
    expect(await screen.findByTestId("workbench-shell")).toBeTruthy();
  });
  it("shows a real 503 error and retries", async () => {
    vi.mocked(getMe).mockRejectedValueOnce(new ApiError(503, "SERVICE_UNAVAILABLE", "数据库尚未就绪", "req-503"));
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>);
    expect((await screen.findByRole("alert")).textContent).toContain("req-503");
    vi.mocked(getMe).mockResolvedValueOnce(studentMe());
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
    expect(await screen.findByTestId("workbench-shell")).toBeTruthy();
  });
  it("requires a stage and keeps administrators outside the student home", async () => {
    vi.mocked(getMe).mockResolvedValueOnce(studentMe(null));
    const first = render(<MemoryRouter><WorkbenchPage /></MemoryRouter>);
    expect(await screen.findByTestId("needs-stage")).toBeTruthy();
    first.unmount();
    vi.mocked(getMe).mockResolvedValueOnce({ ...studentMe(), user: { ...studentMe().user, role: "admin" } });
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>);
    expect(await screen.findByTestId("admin-notice")).toBeTruthy();
  });
});
