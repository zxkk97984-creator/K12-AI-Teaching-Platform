// Companion 客户端 UI 状态类型（0-B §2.1/§2.13；服务器数据不进此层）

export const COMPANION_STATES = [
  "idle",
  "running-right",
  "running-left",
  "listening",
  "thinking",
  "speaking",
  "happy",
  "confused",
  "encouraging",
] as const;

export type CompanionAiState = (typeof COMPANION_STATES)[number];

export interface SpriteFrameSpec {
  row: number;
  frames: number;
  label: string;
}

/** 原型 spriteFrames 数据结构（row/frames/label 一一对应，0-B §2.13） */
export const spriteFrames: Record<CompanionAiState, SpriteFrameSpec> = {
  idle: { row: 0, frames: 6, label: "待机中" },
  "running-right": { row: 1, frames: 8, label: "向右移动中" },
  "running-left": { row: 2, frames: 8, label: "向左移动中" },
  listening: { row: 6, frames: 6, label: "正在听" },
  thinking: { row: 8, frames: 6, label: "思考中" },
  speaking: { row: 3, frames: 4, label: "讲解中" },
  happy: { row: 4, frames: 5, label: "很开心" },
  confused: { row: 5, frames: 8, label: "有点疑惑" },
  encouraging: { row: 7, frames: 6, label: "给你鼓励" },
};

/** 原型状态胶囊文案（chipLabels） */
export const stateChipLabels: Record<CompanionAiState, string> = {
  idle: "在线 · 随时可以问我",
  "running-right": "正在向右移动",
  "running-left": "正在向左移动",
  listening: "正在听你说话",
  thinking: "正在思考你的问题",
  speaking: "正在讲解当前内容",
  happy: "为你的进步开心",
  confused: "我们可以换一种讲法",
  encouraging: "正在生成测验",
};
