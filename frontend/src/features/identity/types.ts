import type { components } from "../../shared/types/generated/identity";

export type Stage = components["schemas"]["Stage"];
export type UserRole = components["schemas"]["UserRole"];
export type PreferredStyle = components["schemas"]["PreferredStyle"];
export type TeacherStyle = components["schemas"]["TeacherStyle"];
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

export const GRADE_OPTIONS: Array<{ value: number; label: string; stage: Stage; group: "小学" | "初中" | "高中" }> = [
  { value: 1, label: "一年级", stage: "PRIMARY_LOWER", group: "小学" },
  { value: 2, label: "二年级", stage: "PRIMARY_LOWER", group: "小学" },
  { value: 3, label: "三年级", stage: "PRIMARY_LOWER", group: "小学" },
  { value: 4, label: "四年级", stage: "PRIMARY_UPPER", group: "小学" },
  { value: 5, label: "五年级", stage: "PRIMARY_UPPER", group: "小学" },
  { value: 6, label: "六年级", stage: "PRIMARY_UPPER", group: "小学" },
  { value: 7, label: "初一", stage: "JUNIOR", group: "初中" },
  { value: 8, label: "初二", stage: "JUNIOR", group: "初中" },
  { value: 9, label: "初三", stage: "JUNIOR", group: "初中" },
  { value: 10, label: "高一", stage: "SENIOR", group: "高中" },
  { value: 11, label: "高二", stage: "SENIOR", group: "高中" },
  { value: 12, label: "高三", stage: "SENIOR", group: "高中" },
];

export function gradeOption(grade: number | null | undefined) {
  return GRADE_OPTIONS.find((option) => option.value === grade);
}

export function gradeLabel(grade: number | null | undefined): string {
  return gradeOption(grade)?.label ?? "年级待设置";
}

export const STYLES: Array<{ value: PreferredStyle; label: string }> = [
  { value: "AUTO", label: "自动匹配" },
  { value: "EXAMPLE", label: "生活例子" },
  { value: "VISUAL", label: "图示讲解" },
  { value: "STORY", label: "故事讲解" },
  { value: "STEP_BY_STEP", label: "分步骤" },
  { value: "CODE", label: "代码实践" },
];

export const TEACHER_STYLES: Array<{ value: TeacherStyle; label: string }> = [
  { value: "AUTO", label: "自动适配" },
  { value: "GENTLE", label: "温柔鼓励" },
  { value: "PLAYFUL", label: "活泼有趣" },
  { value: "PRECISE", label: "严谨清晰" },
  { value: "SOCRATIC", label: "启发提问" },
];

export const VOICE_OPTIONS: Array<{ value: VoicePreference; label: string }> = [
  { value: "DISABLED", label: "关闭语音功能" },
  { value: "INPUT_ONLY", label: "仅在对话中使用语音输入" },
  { value: "OUTPUT_ONLY", label: "开启互动问题朗读" },
  { value: "INPUT_AND_OUTPUT", label: "对话语音输入与互动朗读" },
];

export function stageLabel(stage: Stage | null | undefined): string {
  return STAGES.find((item) => item.value === stage)?.label ?? "尚未选择学段";
}
