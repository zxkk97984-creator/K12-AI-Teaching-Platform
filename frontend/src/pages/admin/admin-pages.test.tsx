import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as resourceApi from "../../features/resources/api";
import type { ResourceSummary } from "../../features/resources/types";
import * as authoringApi from "./authoring-api";
import { AdminResourcesPage } from "./AdminResourcesPage";
import { AdminAuthoringPage } from "./AdminAuthoringPage";

vi.mock("../../features/resources/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../features/resources/api")>();
  return {
    ...actual,
    adminListResources: vi.fn(),
    adminCreateResource: vi.fn(),
    adminPatchResource: vi.fn(),
    adminUploadResource: vi.fn(),
  };
});
vi.mock("./authoring-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./authoring-api")>();
  return {
    ...actual,
    listAuthoringRevisions: vi.fn(),
    listAuthoringJobs: vi.fn(),
    getAuthoringJob: vi.fn(),
    getAuthoringPackage: vi.fn(),
  };
});

const resource: ResourceSummary = {
  id: "11111111-1111-1111-1111-111111111111",
  slug: "course-resource",
  title: "课程资料",
  description: "",
  kind: "WORD",
  stage: "JUNIOR",
  grade_min: null,
  grade_max: null,
  source_kind: "NEW_SOURCE",
  source_note: "管理端登记",
  license_code: "PROJECT-ORIGINAL",
  license_note: "",
  review_status: "UNREVIEWED",
  publication_status: "DRAFT",
  is_test_fixture: false, local_demo_visible: false,
  content_notice: null,
  chapter_revision_ids: [],
  knowledge_point_slugs: [],
  variants: [],
};

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="current-location">{location.pathname + location.search}</span>;
}

beforeEach(() => {
  vi.mocked(resourceApi.adminListResources).mockReset().mockImplementation(async (options) => ({
    items: options?.q === "course-resource" ? [resource] : [],
    profile: "test",
    total: options?.q === "course-resource" ? 1 : 0,
    limit: 12,
    offset: 0,
  }));
  vi.mocked(resourceApi.adminCreateResource).mockReset().mockResolvedValue(resource);
  vi.mocked(resourceApi.adminPatchResource).mockReset().mockResolvedValue(resource);
  vi.mocked(resourceApi.adminUploadResource).mockReset();

  vi.mocked(authoringApi.listAuthoringRevisions).mockReset().mockResolvedValue({
    items: [], total: 0, limit: 200, offset: 0,
  });
  vi.mocked(authoringApi.listAuthoringJobs).mockReset().mockResolvedValue({
    items: [], total: 0, limit: 10, offset: 0,
  });
  vi.mocked(authoringApi.getAuthoringJob).mockReset();
  vi.mocked(authoringApi.getAuthoringPackage).mockReset();
});
afterEach(cleanup);

describe("admin resources", () => {
  it("keeps the created record and original file available after upload fails", async () => {
    vi.mocked(resourceApi.adminUploadResource)
      .mockRejectedValueOnce(new Error("连接中断"))
      .mockResolvedValueOnce({ sha256: "a".repeat(64), size_bytes: 3, mime: "application/octet-stream" });
    render(<AdminResourcesPage />);
    fireEvent.click(screen.getByRole("button", { name: "新增资源" }));
    fireEvent.change(screen.getByTestId("admin-slug"), { target: { value: resource.slug } });
    fireEvent.change(screen.getByTestId("admin-title"), { target: { value: resource.title } });
    fireEvent.change(screen.getByTestId("admin-file"), { target: { files: [new File(["abc"], "lesson.docx")] } });
    fireEvent.click(screen.getByTestId("admin-submit"));

    expect(await screen.findByText(/资源已登记：课程资料/)).toBeTruthy();
    expect(await screen.findByRole("button", { name: "重试上传" })).toBeTruthy();
    expect(resourceApi.adminCreateResource).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "重试上传" }));
    await waitFor(() => expect(resourceApi.adminUploadResource).toHaveBeenCalledTimes(2));
    expect(resourceApi.adminCreateResource).toHaveBeenCalledTimes(1);
  });

  it("sends filters and pagination to the admin endpoint", async () => {
    render(<AdminResourcesPage />);
    fireEvent.change(screen.getByPlaceholderText("标题或 slug"), { target: { value: "course" } });
    fireEvent.change(screen.getByLabelText("状态"), { target: { value: "PUBLISHED" } });
    fireEvent.click(screen.getByRole("button", { name: "筛选" }));
    await waitFor(() => expect(resourceApi.adminListResources).toHaveBeenCalledWith({
      q: "course", kind: undefined, stage: "", status: "PUBLISHED", limit: 12, offset: 0,
    }));
  });
});

describe("admin authoring", () => {
  it("restores a selected task and package from the URL after a refresh", async () => {
    const jobId = "22222222-2222-2222-2222-222222222222";
    const packageId = "33333333-3333-3333-3333-333333333333";
    vi.mocked(authoringApi.getAuthoringJob).mockResolvedValue({
      id: jobId, chapter_revision_id: "revision-1", operation: "GENERATE",
      status: "SUCCEEDED", attempt: 1, max_attempts: 3, run_ref: "run",
      error_code: null, gateway_mode: "FIXTURE", idempotency_key: "key",
      package_id: packageId,
    });
    vi.mocked(authoringApi.getAuthoringPackage).mockResolvedValue({
      id: packageId, job_id: jobId, chapter_revision_id: "revision-1",
      title: "教学包", status: "HUMAN_APPROVED", revision: 1,
      published_revision: null, spec: {}, asset_requests: [], artifacts: [],
      reviews: [], publications: [], notice: "",
    });
    render(<MemoryRouter initialEntries={["/admin/authoring?job=" + jobId]}><AdminAuthoringPage /><LocationProbe /></MemoryRouter>);
    expect(await screen.findByTestId("authoring-package")).toBeTruthy();
    expect(screen.getByTestId("authoring-job-status").textContent).toBe("生成完成");
    expect(screen.getByTestId("authoring-package-status").textContent).toBe("人工审校通过");
    expect(screen.getByTestId("current-location").textContent).toContain("?job=" + jobId);
    expect(authoringApi.getAuthoringJob).toHaveBeenCalledWith(jobId);
    expect(authoringApi.getAuthoringPackage).toHaveBeenCalledWith(packageId);
  });
});
