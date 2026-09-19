/**
 * Build-time capability declarations.
 *
 * These are not business data: they state which product capabilities exist in
 * this build. Everything here is currently unavailable for a concrete reason
 * with an owning task, so the workbench can say "not connected yet" instead of
 * showing demo courses, statistics or simulated teacher replies.
 */
export type Capability = {
  id: "content-catalog" | "teacher" | "activity" | "practice" | "growth";
  label: string;
  ownerTask: string;
  reason: string;
};

export const CAPABILITIES: Record<Capability["id"], Capability> = {
  "content-catalog": {
    id: "content-catalog",
    label: "课程目录与章节内容",
    ownerTask: "T08",
    reason: "课程与章节读取接口将在 T08 接通，本页不展示任何占位课程或假章节。",
  },
  teacher: {
    id: "teacher",
    label: "教学 Agent（Knodo）",
    ownerTask: "T10/T12",
    reason: "Knodo 网关与教学回合尚未接通，教师区不显示模拟回复，也不显示假的生成状态。",
  },
  activity: {
    id: "activity",
    label: "当前活动（动画/测验/代码）",
    ownerTask: "T14",
    reason: "教学活动由课程步骤驱动，T14 起接入；本卡不生成任何活动。",
  },
  practice: {
    id: "practice",
    label: "练习",
    ownerTask: "T15",
    reason: "练习与判分属于 T15–T18，本卡不提供入口。",
  },
  growth: {
    id: "growth",
    label: "成长记录",
    ownerTask: "T18",
    reason: "学习证据与成长视图属于 T18/T19；没有证据前不显示任何统计。",
  },
};

export function capability(id: Capability["id"]): Capability {
  return CAPABILITIES[id];
}
