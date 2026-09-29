import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, getResource: vi.fn(), createTicket: vi.fn() };
});
vi.mock("../study/api", async () => {
  const actual = await vi.importActual<typeof import("../study/api")>("../study/api");
  return { ...actual, recordOpen: vi.fn(), newOpenEventId: vi.fn(() => "open-resource-test") };
});

import { ApiError } from "../identity/api";
import { recordOpen } from "../study/api";
import * as api from "./api";
import { ResourceCard } from "./ResourceCard";
import { ResourceDetailPage } from "./ResourceDetailPage";
import type { ResourceSummary, ResourceVariant } from "./types";

const resourceId = "11111111-1111-1111-1111-111111111111";

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
    id: resourceId,
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

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}</span>;
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={[`/resources/${resourceId}`]}>
      <Routes>
        <Route path="/resources/:resourceId" element={<ResourceDetailPage />} />
        <Route path="/resources" element={<p>学习书库</p>} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(api.getResource).mockReset();
  vi.mocked(api.createTicket).mockReset();
  vi.mocked(recordOpen).mockReset().mockResolvedValue({});
});
afterEach(cleanup);

describe("resource detail and card used by the student route", () => {
  it("opens the server resource and records an explicit, idempotent open fact", async () => {
    vi.mocked(api.getResource).mockResolvedValue(resource());
    renderDetail();
    expect(await screen.findByTestId(`resource-card-${resourceId}`)).toBeTruthy();
    expect(api.getResource).toHaveBeenCalledWith(resourceId);
    await waitFor(() => expect(recordOpen).toHaveBeenCalledWith("RESOURCE", resourceId, "open-resource-test"));
    expect(screen.getByTestId("resource-kind").textContent).toContain("Word 文档");
    expect(screen.getByTestId("variant-SOURCE").textContent).toContain("源文件");
    expect(screen.getByTestId("download-SOURCE").getAttribute("href")).toBe(
      `/api/v1/resources/${resourceId}/content?variant=SOURCE&disposition=attachment`,
    );
    fireEvent.click(screen.getByRole("button", { name: /返回资源中心/ }));
    expect(screen.getByTestId("location").textContent).toBe("/resources");
  });

  it("shows server failure without inventing a resource card", async () => {
    vi.mocked(api.getResource).mockRejectedValue(new ApiError(503, "SERVICE_UNAVAILABLE", "资源服务暂不可用", null));
    renderDetail();
    expect((await screen.findByRole("alert")).textContent).toContain("资源服务暂不可用");
    expect(screen.queryByTestId(`resource-card-${resourceId}`)).toBeNull();
    expect(recordOpen).not.toHaveBeenCalled();
  });

  it("still shows an authorized resource when history recording fails", async () => {
    vi.mocked(api.getResource).mockResolvedValue(resource());
    vi.mocked(recordOpen).mockRejectedValue(new Error("history unavailable"));
    renderDetail();
    expect(await screen.findByTestId(`resource-card-${resourceId}`)).toBeTruthy();
  });

  it("never derives a playable or download URL from an untrusted title", () => {
    render(<ResourceCard resource={resource({
      title: "https://evil.example/payload.mp4",
      kind: "VIDEO",
      variants: [variant({ mime: "video/mp4", inline_ok: true })],
    })} />);
    const video = screen.getByTestId(`resource-video-${resourceId}`) as HTMLVideoElement;
    expect(video.getAttribute("src")).toBe(
      `/api/v1/resources/${resourceId}/content?variant=SOURCE&disposition=inline`,
    );
    const urls = Array.from(document.querySelectorAll("[href], [src]")).map(
      (node) => node.getAttribute("href") ?? node.getAttribute("src") ?? "",
    );
    expect(urls.length).toBeGreaterThan(0);
    for (const url of urls) {
      expect(url).not.toContain("evil.example");
      expect(url.startsWith("/api/v1/resources/")).toBe(true);
    }
  });

  it("marks a missing file unavailable and preserves the fixture notice", () => {
    render(<ResourceCard resource={resource({
      is_test_fixture: true,
      content_notice: "测试内容，未作人工教学审校",
      variants: [variant({ available: false, unavailable_reason: "RESOURCE_FILE_MISSING" })],
    })} />);
    expect(screen.getByTestId("resource-unavailable").textContent).toContain("文件当前缺失");
    expect(screen.queryByTestId("download-SOURCE")).toBeNull();
    expect(screen.getByTestId("resource-ticket").hasAttribute("disabled")).toBe(true);
    expect(screen.getByTestId("variant-SOURCE").textContent).toContain("RESOURCE_FILE_MISSING");
    expect(screen.getByTestId("resource-notice").textContent).toContain("未作人工教学审校");
  });

  it("uses a server-issued temporary ticket and reports refusal", async () => {
    vi.mocked(api.createTicket).mockResolvedValueOnce({
      url: "/api/v1/resources/content/abc.def",
      expires_at: "2026-09-19T13:00:00Z",
      variant: "SOURCE",
      notice: "临时链接：仅本人当次会话可用，不是教材资源 ID",
    }).mockRejectedValueOnce(new ApiError(404, "NOT_FOUND", "RESOURCE_NOT_VISIBLE: 资源不可用", null));
    render(<ResourceCard resource={resource()} />);
    fireEvent.click(screen.getByTestId("resource-ticket"));
    expect((await screen.findByTestId("resource-ticket-result")).textContent).toContain("不是教材资源 ID");
    expect(api.createTicket).toHaveBeenCalledWith(resourceId, "SOURCE");
    fireEvent.click(screen.getByTestId("resource-ticket"));
    await waitFor(() => expect(screen.getByTestId("resource-ticket-error").textContent).toContain("资源不可用"));
  });

  it("shows video loading, completion and failure honestly", () => {
    render(<ResourceCard resource={resource({
      kind: "VIDEO",
      variants: [variant({ mime: "video/mp4", inline_ok: true, filename: "clip.mp4" })],
    })} />);
    const video = screen.getByTestId(`resource-video-${resourceId}`);
    fireEvent.loadedData(video);
    expect(screen.getByTestId("resource-player-state").textContent).toContain("正在播放");
    fireEvent.ended(video);
    expect(screen.getByTestId("resource-player-state").textContent).toContain("已播放完");
    fireEvent.error(video);
    expect(screen.getByTestId("resource-player-state").textContent).toContain("视频无法播放");
  });
});
