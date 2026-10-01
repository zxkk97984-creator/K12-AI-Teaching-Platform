export const REVIEW_LABEL: Record<string, string> = {
  UNREVIEWED: "待人工审校",
  AUTO_VALIDATED: "结构校验通过",
  HUMAN_APPROVED: "人工审校通过",
};
export const PUBLICATION_LABEL: Record<string, string> = {
  DRAFT: "草稿",
  PUBLISHED: "已发布",
  WITHDRAWN: "已撤回",
};
export const STAGE_LABEL: Record<string, string> = {
  PRIMARY_LOWER: "小学低年级",
  PRIMARY_UPPER: "小学高年级",
  JUNIOR: "初中",
  SENIOR: "高中",
  "*": "全部学段（默认）",
};
export const PURPOSE_LABEL: Record<string, string> = {
  LESSON: "互动讲解",
  GAME: "互动小游戏",
  EXPERIMENT: "互动实验",
};
export function StatusBadge({
  value,
  children,
}: {
  value?: string;
  children: React.ReactNode;
}) {
  const tone =
    value &&
    ["HUMAN_APPROVED", "PUBLISHED", "PASSED", "SUCCEEDED", "PASS"].includes(
      value,
    )
      ? "success"
      : value && ["FAILED", "ERROR", "WITHDRAWN"].includes(value)
        ? "danger"
        : value && ["RUNNING", "QUEUED", "STALE", "UNREVIEWED"].includes(value)
          ? "warning"
          : "neutral";
  return <span className={`admin-badge admin-badge--${tone}`}>{children}</span>;
}
export function resourcePublishReason(item: {
  kind: string;
  review_status: string;
  publication_status: string;
  is_test_fixture: boolean;
  source_kind: string;
  variants: { available: boolean }[];
}) {
  if (item.kind === "INTERACTIVE") return "请在互动内容详情中检查版本并发布";
  if (item.publication_status === "PUBLISHED") return "此资源已经发布";
  if (item.is_test_fixture || item.source_kind === "SYNTHETIC_FIXTURE")
    return "合成测试资源只能用于本地演示";
  if (item.review_status !== "HUMAN_APPROVED")
    return "需要先检查真实内容并完成人工审校";
  if (!item.variants.some((entry) => entry.available))
    return "需要先补传可用文件";
  return "";
}
