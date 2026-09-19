import type { components } from "../../shared/types/generated/identity";

export type Stage = components["schemas"]["Stage"];
export type UserRole = components["schemas"]["UserRole"];
export type PreferredStyle = components["schemas"]["PreferredStyle"];
export type VoicePreference = components["schemas"]["VoicePreference"];
export type ProfilePatch = components["schemas"]["ProfilePatch"];
export type PreferencesPatch = components["schemas"]["PreferencesPatch"];
export type LoginRequest = components["schemas"]["LoginRequest"];
export type MeResponse = components["schemas"]["MeResponse"];
export type AuthResponse = components["schemas"]["AuthResponse"];

export const STAGES: Array<{ value: Stage; label: string }> = [
  { value: "PRIMARY_LOWER", label: "小学低年级（1–3年级）" },
  { value: "PRIMARY_UPPER", label: "小学高年级（4–6年级）" },
  { value: "JUNIOR", label: "初中（7–9年级）" },
  { value: "SENIOR", label: "高中（10–12年级）" },
];

export const STYLES: Array<{ value: PreferredStyle; label: string }> = [
  { value: "AUTO", label: "自动匹配" },
  { value: "EXAMPLE", label: "生活例子" },
  { value: "VISUAL", label: "图示讲解" },
  { value: "STORY", label: "故事讲解" },
  { value: "STEP_BY_STEP", label: "分步骤" },
  { value: "CODE", label: "代码实践" },
];

export const VOICE_OPTIONS: Array<{ value: VoicePreference; label: string }> = [
  { value: "DISABLED", label: "关闭（当前功能也会如实显示不可用）" },
  { value: "INPUT_ONLY", label: "只偏好语音输入" },
  { value: "OUTPUT_ONLY", label: "只偏好语音播报" },
  { value: "INPUT_AND_OUTPUT", label: "输入和播报都偏好" },
];

export function stageLabel(stage: Stage | null | undefined): string {
  return STAGES.find((item) => item.value === stage)?.label ?? "尚未选择学段";
}
