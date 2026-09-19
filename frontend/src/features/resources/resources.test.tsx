import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const navigate = vi.fn();

vi.mock("../identity/session", () => ({ navigate: (path: string) => navigate(path) }));
vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    listResources: vi.fn(),
    createTicket: vi.fn(),
  };
});

import { ApiError } from "../identity/api";
import * as api from "./api";
import { ResourceLibraryPage } from "./ResourceLibraryPage";
import type { ResourceList, ResourceSummary, ResourceVariant } from "./types";

function variant(overrides: Partial<ResourceVariant> = {}): ResourceVariant {
  return {
    variant: "SOURCE",
    filename: "synthetic-lesson.docx",
    mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size_bytes: 1051,
    sha256: "0".repeat(64),
    inline_ok: false,
    available: true,
    unavailable_reason: null,
    ...overrides,
  };
}

function resource(overrides: Partial<ResourceSummary> = {}): ResourceSummary {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    slug: "t20-lesson",
    title: "合成测试资源",
    description: "用于测试",
    kind: "WORD",
    stage: "JUNIOR",
    grade_min: 7,
    grade_max: 9,
    source_kind: "NEW_SOURCE",
    source_note: "",
    license_code: "PROJECT-ORIGINAL",
    license_note: "",
    review_status: "HUMAN_APPROVED",
    publication_status: "PUBLISHED",
    is_test_fixture: false,
    content_notice: null,
    chapter_revision_ids: [],
    knowledge_point_slugs: [],
    variants: [variant()],
    ...overrides,
  };
}

function listOf(items: ResourceSummary[]): ResourceList {
  return { items, profile: "development" };
}

beforeEach(() => {
  navigate.mockReset();
  vi.mocked(api.listResources).mockReset();
  vi.mocked(api.createTicket).mockReset();
});

afterEach(cleanup);

describe("ResourceLibraryPage", () => {
  it("shows a real empty state instead of placeholder cards", async () => {
    vi.mocked(api.listResources).mockResolvedValue(listOf([]));
    render(<ResourceLibraryPage />);
    await waitFor(() => expect(screen.getByTestId("resource-empty")).toBeTruthy());
    expect(screen.queryByTestId("resource-grid")).toBeNull();
  });

  it("renders only server-provided resources, with kind and variants", async () => {
    vi.mocked(api.listResources).mockResolvedValue(listOf([resource()]));
    render(<ResourceLibraryPage />);
    await waitFor(() => expect(screen.getByTestId("resource-grid")).toBeTruthy());
    expect(screen.getByTestId("resource-kind").textContent).toContain("Word 文档");
    expect(screen.getByTestId("variant-SOURCE").textContent).toContain("源文件");
    expect(screen.getByTestId("download-SOURCE").getAttribute("href")).toContain(
      "/api/v1/resources/11111111-1111-1111-1111-111111111111/content",
    );
  });

  it("never fabricates a file URL from a resource title or a model string", async () => {
    vi.mocked(api.listResources).mockResolvedValue(
      listOf([
        resource({
          title: "https://evil.example/payload.mp4",
          kind: "VIDEO",
          variants: [variant({ mime: "video/mp4", inline_ok: true })],
        }),
      ]),
    );
    render(<ResourceLibraryPage />);
    await waitFor(() => expect(screen.getByTestId("resource-player")).toBeTruthy());
    const video = screen.getByTestId(
      "resource-video-11111111-1111-1111-1111-111111111111",
    ) as HTMLVideoElement;
    expect(video.getAttribute("src")).toBe(
      "/api/v1/resources/11111111-1111-1111-1111-111111111111/content?variant=SOURCE&disposition=inline",
    );
    // No URL-bearing attribute may be derived from the (untrusted) title text.
    const urls = Array.from(document.querySelectorAll("[href], [src]")).map(
      (node) => node.getAttribute("href") ?? node.getAttribute("src") ?? "",
    );
    expect(urls.length).toBeGreaterThan(0);
    for (const url of urls) {
      expect(url).not.toContain("evil.example");
      expect(url.startsWith("/api/v1/resources/")).toBe(true);
    }
  });

  it("reports a readable failure and caches no fake suggestion", async () => {
    vi.mocked(api.listResources).mockRejectedValue(
      new ApiError(503, "SERVICE_UNAVAILABLE", "资源服务暂不可用", null),
    );
    render(<ResourceLibraryPage />);
    await waitFor(() => expect(screen.getByTestId("resource-error")).toBeTruthy());
    expect(screen.getByTestId("resource-error").textContent).toContain("资源服务暂不可用");
    expect(screen.queryByTestId("resource-grid")).toBeNull();
  });

  it("redirects to login when the session is gone", async () => {
    vi.mocked(api.listResources).mockRejectedValue(
      new ApiError(401, "UNAUTHORIZED", "登录已失效", null),
    );
    render(<ResourceLibraryPage />);
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/login"));
  });

  it("marks a resource whose file is missing as unavailable, not ready", async () => {
    vi.mocked(api.listResources).mockResolvedValue(
      listOf([
        resource({
          variants: [
            variant({ available: false, unavailable_reason: "RESOURCE_FILE_MISSING" }),
          ],
        }),
      ]),
    );
    render(<ResourceLibraryPage />);
    await waitFor(() => expect(screen.getByTestId("resource-unavailable")).toBeTruthy());
    expect(screen.queryByTestId("download-SOURCE")).toBeNull();
    expect(screen.getByTestId("variant-SOURCE").textContent).toContain("RESOURCE_FILE_MISSING");
  });

  it("asks the server for a short-lived ticket and surfaces the notice", async () => {
    vi.mocked(api.listResources).mockResolvedValue(listOf([resource()]));
    vi.mocked(api.createTicket).mockResolvedValue({
      url: "/api/v1/resources/content/abc.def",
      expires_at: "2026-09-19T13:00:00Z",
      variant: "SOURCE",
      notice: "临时链接：仅本人当次会话可用，不是教材资源 ID",
    });
    render(<ResourceLibraryPage />);
    await waitFor(() => expect(screen.getByTestId("resource-ticket")).toBeTruthy());
    fireEvent.click(screen.getByTestId("resource-ticket"));
    await waitFor(() => expect(screen.getByTestId("resource-ticket-result")).toBeTruthy());
    expect(screen.getByTestId("resource-ticket-result").textContent).toContain("不是教材资源 ID");
  });

  it("shows a readable error when the ticket request is refused", async () => {
    vi.mocked(api.listResources).mockResolvedValue(listOf([resource()]));
    vi.mocked(api.createTicket).mockRejectedValue(
      new ApiError(404, "NOT_FOUND", "RESOURCE_NOT_VISIBLE: 资源不可用", null),
    );
    render(<ResourceLibraryPage />);
    await waitFor(() => expect(screen.getByTestId("resource-ticket")).toBeTruthy());
    fireEvent.click(screen.getByTestId("resource-ticket"));
    await waitFor(() =>
      expect(screen.getByTestId("resource-ticket-error").textContent).toContain("资源不可用"),
    );
  });

  it("shows the fixture notice when the server marks test content", async () => {
    vi.mocked(api.listResources).mockResolvedValue(
      listOf([
        resource({
          is_test_fixture: true,
          content_notice: "测试内容，未作人工教学审校",
        }),
      ]),
    );
    render(<ResourceLibraryPage />);
    await waitFor(() => expect(screen.getByTestId("resource-notice")).toBeTruthy());
    expect(screen.getByTestId("resource-notice").textContent).toContain("未作人工教学审校");
  });

  it("handles video load and error events truthfully", async () => {
    vi.mocked(api.listResources).mockResolvedValue(
      listOf([
        resource({
          kind: "VIDEO",
          variants: [variant({ mime: "video/mp4", inline_ok: true, filename: "clip.mp4" })],
        }),
      ]),
    );
    render(<ResourceLibraryPage />);
    await waitFor(() => expect(screen.getByTestId("resource-player")).toBeTruthy());
    const video = screen.getByTestId("resource-video-11111111-1111-1111-1111-111111111111");

    fireEvent.loadedData(video);
    expect(screen.getByTestId("resource-player-state").textContent).toContain("正在播放");

    fireEvent.ended(video);
    expect(screen.getByTestId("resource-player-state").textContent).toContain("已播放完");

    fireEvent.error(video);
    expect(screen.getByTestId("resource-player-state").textContent).toContain("视频无法播放");
  });

  it("does not claim mastery, ranking or percentages anywhere", async () => {
    vi.mocked(api.listResources).mockResolvedValue(listOf([resource()]));
    const { container } = render(<ResourceLibraryPage />);
    await waitFor(() => expect(screen.getByTestId("resource-grid")).toBeTruthy());
    const text = container.textContent ?? "";
    for (const word of ["掌握度", "排名", "排行榜", "%", "正确率"]) {
      expect(text).not.toContain(word);
    }
  });
});
