import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { InteractiveCatalogPage } from "./InteractiveCatalogPage";
import * as interactiveApi from "./api";
import * as resourceApi from "../resources/api";
import type { ResourceSummary } from "../resources/types";

const account = vi.hoisted(() => ({ user: { id: "student" }, profile: { stage: "SENIOR" } }));
vi.mock("../identity/AccountContext", () => ({ useAccount: () => account }));
vi.mock("../../app/layout/pageChrome", () => ({ PageHeading: ({ title }: { title: string }) => <h1>{title}</h1> }));
vi.mock("./api", () => ({ listInteractive: vi.fn() }));
vi.mock("../resources/api", async original => ({ ...await original<typeof resourceApi>(), listResources: vi.fn() }));

const lesson: interactiveApi.InteractiveItem = {
  id: "html-lesson", title: "梯度下降讲解", description: "HTML 互动教学", purpose: "LESSON", subject: "计算机与人工智能",
  stage: "SENIOR", grade_min: null, grade_max: null, knowledge_points: ["梯度下降"], cover: null, revision: 1,
  capabilities: [], is_test_fixture: false, local_demo_visible: true, activity_status: "ACTIVE", can_resume: true, session_id: "saved-session",
};
const video: ResourceSummary = {
  id: "video", slug: "ai-literacy-video-07", title: "07 参数怎样一步步改好——梯度下降", description: "人工智能通识课 · 梯度下降视频。",
  kind: "VIDEO", stage: "SENIOR", grade_min: null, grade_max: null, source_kind: "NEW_SOURCE", source_note: "用户上传",
  license_code: "UNKNOWN", license_note: "", review_status: "AUTO_VALIDATED", publication_status: "DRAFT", is_test_fixture: false,
  local_demo_visible: true, content_notice: null, chapter_revision_ids: [], knowledge_point_slugs: [],
  variants: [{ variant: "SOURCE", filename: "lesson.mp4", mime: "video/mp4", size_bytes: 1234, sha256: "sha", available: true, inline_ok: true, unavailable_reason: null }],
};

function page() { return <MemoryRouter initialEntries={["/animations"]}><InteractiveCatalogPage purposeOverride="LESSON" /></MemoryRouter>; }
beforeEach(() => {
  account.user.id = "student"; account.profile.stage = "SENIOR";
  vi.mocked(interactiveApi.listInteractive).mockResolvedValue({ stage: "SENIOR", items: [lesson] });
  vi.mocked(resourceApi.listResources).mockResolvedValue({ profile: "DEVELOPMENT", items: [video] });
});
afterEach(() => { cleanup(); vi.resetAllMocks(); });

describe("animation catalogue formats", () => {
  it("shows current-stage videos beside HTML lessons without advertising unavailable files", async () => {
    vi.mocked(resourceApi.listResources).mockResolvedValueOnce({ profile: "DEVELOPMENT", items: [
      video, { ...video, id: "junior", stage: "JUNIOR", title: "跨学段视频" },
      { ...video, id: "missing", title: "文件缺失视频", variants: [{ ...video.variants[0], available: false }] },
      { ...video, id: "preview-only", title: "只有预览的视频", variants: [{ ...video.variants[0], variant: "PREVIEW" }] },
    ] });
    render(page());
    const heading = await screen.findByRole("heading", { name: video.title });
    expect(screen.getByRole("heading", { name: "（html）梯度下降讲解" })).toBeTruthy();
    expect(heading.textContent).not.toContain("html");
    expect(heading.querySelector("a")?.getAttribute("href")).toBe("/resources/video?from=animations");
    expect(screen.queryByText("跨学段视频")).toBeNull();
    expect(screen.queryByText("文件缺失视频")).toBeNull();
    expect(screen.queryByText("只有预览的视频")).toBeNull();
    expect(resourceApi.listResources).toHaveBeenCalledWith({ kind: "VIDEO" }, expect.any(AbortSignal));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "参数" } });
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));
    await waitFor(() => expect(resourceApi.listResources).toHaveBeenCalledTimes(2));
    await screen.findByRole("heading", { name: video.title });
  });

  it("keeps videos visible and reports an HTML catalogue failure", async () => {
    vi.mocked(interactiveApi.listInteractive).mockRejectedValueOnce(new Error("HTML 接口暂不可用"));
    render(page());
    await screen.findByRole("heading", { name: video.title });
    expect(screen.getByRole("alert").textContent).toContain("HTML 接口暂不可用");
  });

  it("keeps HTML lessons visible when the video request fails", async () => {
    vi.mocked(resourceApi.listResources).mockRejectedValueOnce(new Error("视频接口暂不可用"));
    render(page());
    await screen.findByRole("heading", { name: "（html）梯度下降讲解" });
    expect(screen.getByRole("alert").textContent).toContain("视频接口暂不可用");
  });

  it("clears the previous account's videos while a new account is loading", async () => {
    const mounted = render(page());
    await screen.findByRole("heading", { name: video.title });
    let resolveVideos!: (value: Awaited<ReturnType<typeof resourceApi.listResources>>) => void;
    vi.mocked(resourceApi.listResources).mockImplementationOnce(() => new Promise(resolve => { resolveVideos = resolve; }));
    vi.mocked(interactiveApi.listInteractive).mockResolvedValueOnce({ stage: "PRIMARY_UPPER", items: [] });
    account.user.id = "other-student"; account.profile.stage = "PRIMARY_UPPER";
    mounted.rerender(page());
    expect(screen.queryByRole("heading", { name: video.title })).toBeNull();
    resolveVideos({ profile: "DEVELOPMENT", items: [video] });
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
    expect(screen.queryByRole("heading", { name: video.title })).toBeNull();
  });

  it("does not put passive videos into experiment or game catalogues", async () => {
    vi.mocked(interactiveApi.listInteractive).mockResolvedValueOnce({ stage: "SENIOR", items: [{ ...lesson, purpose: "EXPERIMENT" }] });
    render(<MemoryRouter><InteractiveCatalogPage purposeOverride="EXPERIMENT" /></MemoryRouter>);
    await screen.findByRole("heading", { name: lesson.title });
    expect(resourceApi.listResources).not.toHaveBeenCalled();
  });
});
