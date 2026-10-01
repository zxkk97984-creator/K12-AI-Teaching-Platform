/** Student resource types (T20).
 *
 * Hand-written to mirror the FastAPI DTOs in
 * `backend/app/modules/resources/schemas.py`; T20 adds no frozen contract, so
 * there is no generated file to import. The student payload never contains a
 * storage key, a filesystem path or a signed link.
 */

export type ResourceKind = "WORD" | "SLIDES" | "VIDEO" | "PDF" | "IMAGE" | "INTERACTIVE";
export type ResourceVariantKind = "SOURCE" | "PREVIEW";

export type ResourceVariant = {
  variant: ResourceVariantKind;
  filename: string;
  mime: string;
  size_bytes: number;
  sha256: string;
  inline_ok: boolean;
  available: boolean;
  unavailable_reason: string | null;
};

export type ResourceSummary = {
  id: string;
  slug: string;
  title: string;
  description: string;
  kind: ResourceKind;
  interactive_purpose?: "LESSON" | "GAME" | "EXPERIMENT" | null;
  interactive_subject?: string | null;
  active_interactive_revision_id?: string | null;
  stage: string;
  grade_min: number | null;
  grade_max: number | null;
  source_kind: string;
  source_note: string;
  license_code: string;
  license_note: string;
  review_status: string;
  publication_status: string;
  is_test_fixture: boolean;
  local_demo_visible: boolean;
  content_notice: string | null;
  chapter_revision_ids: string[];
  knowledge_point_slugs: string[];
  variants: ResourceVariant[];
};

export type ResourceList = {
  items: ResourceSummary[];
  profile: string;
  /** Pagination is included by the admin endpoint; student lists may omit it. */
  total?: number;
  limit?: number;
  offset?: number;
};

export type ResourceTicket = {
  url: string;
  expires_at: string;
  variant: ResourceVariantKind;
  notice: string;
};

export const KIND_LABEL: Record<ResourceKind, string> = {
  WORD: "Word 文档",
  SLIDES: "PPT 演示",
  VIDEO: "教学视频",
  PDF: "PDF",
  IMAGE: "图片",
  INTERACTIVE: "互动内容",
};

export const VARIANT_LABEL: Record<ResourceVariantKind, string> = {
  SOURCE: "源文件",
  PREVIEW: "预览文件",
};

export function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

/** A resource is only "openable" when the server says the bytes exist. */
export function usableVariants(resource: ResourceSummary): ResourceVariant[] {
  return resource.variants.filter((item) => item.available);
}

export function hasPlayableVideo(resource: ResourceSummary): boolean {
  return (
    resource.kind === "VIDEO" &&
    usableVariants(resource).some((item) => item.mime.startsWith("video/"))
  );
}
