import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ResourceLibraryPage } from "./ResourceLibraryPage";
import * as api from "../study/api";
import * as interactiveApi from "../interactive/api";

vi.mock("../interactive/api", () => ({ listInteractive: vi.fn() }));
vi.mock("../identity/AccountContext", () => ({ useAccount: () => ({ user: { id: "reader" }, profile: { stage: "SENIOR" } }) }));
vi.mock("../study/api", async (original) => ({
  ...await original<typeof api>(), listCatalog: vi.fn(), getStudentContent: vi.fn(), addBookmark: vi.fn(), removeBookmark: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(interactiveApi.listInteractive).mockResolvedValue({ stage: "SENIOR", items: [] });
  vi.mocked(api.listCatalog).mockResolvedValue({ items: [
    { kind: "COURSE", id: "course", title: "数据结构讲义", description: "连续阅读算法。", route: "/courses/course", chapter_count: 12, is_test_fixture: false },
    { kind: "COURSE", id: "demo", title: "AI 演示课程", description: "只用来演示流程。", route: "/courses/demo", chapter_count: 1, is_test_fixture: true },
  ], total: 2, limit: 100, offset: 0 });
  vi.mocked(api.getStudentContent).mockResolvedValue({ stage: "SENIOR", picturebooks: [], guided_animation: null });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("reading library", () => {
  it("labels interactive lesson formats by matching ID and includes them in the animation filter", async () => {
    vi.mocked(api.listCatalog).mockResolvedValueOnce({ items: [
      { kind: "RESOURCE", id: "lesson", title: "样例与测试", description: "动画与操作。", route: "/interactive/lesson", resource_type: "INTERACTIVE" },
      { kind: "RESOURCE", id: "experiment", title: "样例与测试", description: "另一种形式。", route: "/interactive/experiment", resource_type: "INTERACTIVE" },
      { kind: "RESOURCE", id: "video", title: "动画的录制视频", description: "教学视频。", route: "/resources/video", resource_type: "VIDEO" },
      { kind: "RESOURCE", id: "word", title: "文档资料", description: "Word 文件。", route: "/resources/word", resource_type: "WORD" },
    ], total: 4, limit: 100, offset: 0 });
    const base: interactiveApi.InteractiveItem = { id: "lesson", title: "样例与测试", description: "", purpose: "LESSON", subject: "计算思维", stage: "SENIOR", grade_min: null, grade_max: null, knowledge_points: [], cover: null, revision: 1, capabilities: [], is_test_fixture: false, local_demo_visible: true, activity_status: "ACTIVE", can_resume: true, session_id: "saved-lesson" };
    vi.mocked(interactiveApi.listInteractive).mockResolvedValueOnce({ stage: "SENIOR", items: [base, { ...base, id: "experiment", purpose: "EXPERIMENT" }] });
    render(<ResourceLibraryPage />);
    await screen.findByText("互动实验", { selector: ".library-format-tag" });
    expect(screen.getByText("动画讲解", { selector: ".library-format-tag" })).toBeTruthy();
    expect(screen.getByText("视频", { selector: ".library-format-tag" })).toBeTruthy();
    expect(screen.getByText("Word 文档", { selector: ".library-format-tag" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "打开动画讲解：样例与测试" }).getAttribute("href")).toContain("returnTo=%2Fresources");
    fireEvent.click(screen.getByRole("button", { name: "动画讲解" }));
    expect(screen.getAllByRole("heading", { name: "样例与测试" })).toHaveLength(1);
    expect(screen.queryByRole("heading", { name: "动画的录制视频" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "收藏样例与测试" }));
    await waitFor(() => expect(api.addBookmark).toHaveBeenCalledWith("RESOURCE", "lesson"));
  });

  it("retains books and uses an honest format fallback when supplementary metadata fails", async () => {
    vi.mocked(interactiveApi.listInteractive).mockRejectedValueOnce(new Error("metadata unavailable"));
    vi.mocked(api.listCatalog).mockResolvedValueOnce({ items: [
      { kind: "RESOURCE", id: "unknown", title: "待分类课件", description: "", route: "/interactive/unknown", resource_type: "INTERACTIVE" },
    ], total: 1, limit: 100, offset: 0 });
    render(<ResourceLibraryPage />);
    await screen.findByText("互动课件", { selector: ".library-format-tag" });
    expect(screen.getByRole("heading", { name: "Python 3：从基础到项目" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("classifies imported textbooks separately from lectures and keeps their real chapter counts", async () => {
    vi.mocked(api.listCatalog).mockResolvedValueOnce({ items: [
      { kind: "COURSE", id: "book", title: "数据结构与算法实践", description: "一部完整教材。", route: "/courses/book", chapter_count: 12, is_textbook: true, body_han_chars: 44551 },
      { kind: "COURSE", id: "lecture", title: "算法课堂讲义", description: "课堂阅读材料。", route: "/courses/lecture", chapter_count: 6 },
    ], total: 2, limit: 100, offset: 0 });
    render(<ResourceLibraryPage />);
    const bookHeading = await screen.findByRole("heading", { name: "数据结构与算法实践" });
    expect(bookHeading.closest("section")?.getAttribute("aria-label")).toBe("专题教材");
    expect(screen.getByText(/12 个可读章节 · 正文 4.5 万字/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "课程讲义" }));
    expect(screen.queryByRole("heading", { name: "数据结构与算法实践" })).toBeNull();
    expect(screen.getByRole("heading", { name: "算法课堂讲义" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "专题教材" }));
    expect(screen.queryByRole("heading", { name: "算法课堂讲义" })).toBeNull();
    expect(screen.getByRole("heading", { name: "数据结构与算法实践" })).toBeTruthy();
  });
  it("never advertises a missing file as an openable teaching material", async () => {
    vi.mocked(api.listCatalog).mockResolvedValueOnce({ items: [
      { kind: "RESOURCE", id: "missing", title: "缺失的资料", description: "文件已不存在", route: "/resources/missing", available: false, unavailable_reason: "RESOURCE_FILE_MISSING", is_test_fixture: false },
    ], total: 1, limit: 100, offset: 0 });
    render(<ResourceLibraryPage />);
    await screen.findByRole("region", { name: "专题教材" });
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
    expect(screen.queryByRole("heading", { name: "缺失的资料" })).toBeNull();
    expect(screen.getByText(/1 项资料暂不可用/)).toBeTruthy();
  });

  it("keeps real lecture counts visible and puts synthetic courses behind an explicit switch", async () => {
    render(<ResourceLibraryPage />);
    await screen.findByRole("heading", { name: "课程讲义" });
    expect(screen.getByText(/12 个可读章节/)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "AI 演示课程" })).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: "显示演示内容" }));
    expect(screen.getByRole("heading", { name: "AI 演示课程" })).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: "显示演示内容" }));
    expect(screen.queryByRole("heading", { name: "AI 演示课程" })).toBeNull();
  });

  it("filters built-in books separately and preserves the catalogue after a bookmark failure", async () => {
    vi.mocked(api.addBookmark).mockRejectedValueOnce(new Error("收藏未保存"));
    render(<ResourceLibraryPage />);
    await screen.findByRole("heading", { name: "课程讲义" });
    fireEvent.click(screen.getByRole("button", { name: "收藏数据结构讲义" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("收藏未保存"));
    expect(screen.getByRole("heading", { name: "数据结构讲义" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "专题教材" }));
    expect(screen.queryByRole("heading", { name: "数据结构讲义" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Python 3：从基础到项目" })).toBeTruthy();
  });
});
