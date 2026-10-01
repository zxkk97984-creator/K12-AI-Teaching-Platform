import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ResourceLibraryPage } from "./ResourceLibraryPage";
import * as api from "../study/api";

vi.mock("../identity/AccountContext", () => ({ useAccount: () => ({ user: { id: "reader" }, profile: { stage: "SENIOR" } }) }));
vi.mock("../study/api", async (original) => ({
  ...await original<typeof api>(), listCatalog: vi.fn(), getStudentContent: vi.fn(), addBookmark: vi.fn(), removeBookmark: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(api.listCatalog).mockResolvedValue({ items: [
    { kind: "COURSE", id: "course", title: "数据结构讲义", description: "连续阅读算法。", route: "/courses/course", chapter_count: 12, is_test_fixture: false },
    { kind: "COURSE", id: "demo", title: "AI 演示课程", description: "只用来演示流程。", route: "/courses/demo", chapter_count: 1, is_test_fixture: true },
  ], total: 2, limit: 100, offset: 0 });
  vi.mocked(api.getStudentContent).mockResolvedValue({ stage: "SENIOR", picturebooks: [], guided_animation: null });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("reading library", () => {
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
