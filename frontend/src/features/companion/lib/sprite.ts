import { spriteFrames, type CompanionAiState } from "../types";

/** spritesheet 网格（参考项目 spritesheet-extended.webp） */
export const SPRITE_GRID_COLS = 8;
export const SPRITE_GRID_ROWS = 11;
export const SPRITE_FRAME_MS = 220;
export const SPRITE_CELL_WIDTH = 192;
export const SPRITE_CELL_HEIGHT = 208;
export const SPRITE_SHEET_URL = "/spritesheet-extended.webp";

export const COMPANION_PETS = [
  {
    id: "shuangling",
    displayName: "霜铃",
    description: "温柔可靠的银发学习伙伴。",
    spritesheetUrl: SPRITE_SHEET_URL,
    gridRows: SPRITE_GRID_ROWS,
    headCrop: { cellWidth: 70, left: 20, top: 6 },
  },
  {
    id: "anya",
    displayName: "阿尼亚",
    description: "活泼可爱的粉发校园伙伴。",
    spritesheetUrl: "/pets/anya/spritesheet.webp",
    gridRows: 9,
    headCrop: { cellWidth: 70, left: 17, top: 15 },
  },
  {
    id: "doraemon",
    displayName: "哆啦A梦",
    description: "爱帮忙的蓝色机器猫伙伴。",
    spritesheetUrl: "/pets/doraemon/spritesheet.webp",
    gridRows: 9,
    headCrop: { cellWidth: 62, left: 13, top: 8 },
  },
  {
    id: "kun-like",
    displayName: "Kun Like",
    description: "抱着篮球、充满活力的小鸡伙伴。",
    spritesheetUrl: "/pets/kun-like/spritesheet.webp",
    gridRows: 9,
    headCrop: { cellWidth: 60, left: 18, top: 5 },
  },
  {
    id: "lulu-capybara",
    displayName: "噜噜",
    description: "软萌安静、圆滚滚的治愈水豚。",
    spritesheetUrl: "/pets/lulu-capybara/spritesheet.webp",
    gridRows: 9,
    headCrop: { cellWidth: 52, left: 8, top: 3 },
  },
  {
    id: "shinchan",
    displayName: "小新",
    description: "古灵精怪的幼儿园小伙伴。",
    spritesheetUrl: "/pets/shinchan/spritesheet.webp",
    gridRows: 9,
    headCrop: { cellWidth: 54, left: 10, top: 4 },
  },
] as const;

export type CompanionPetId = (typeof COMPANION_PETS)[number]["id"];
export type CompanionPet = (typeof COMPANION_PETS)[number];

export function getCompanionPet(id: string): CompanionPet {
  return COMPANION_PETS.find((pet) => pet.id === id) ?? COMPANION_PETS[0];
}

export interface SpriteStyle {
  backgroundImage: string;
  backgroundRepeat: "no-repeat";
  backgroundSize: string;
  backgroundPosition: string;
}

export function getSpriteStyle(
  state: CompanionAiState,
  frame: number,
  cellWidth: number,
  petId: CompanionPetId = "shuangling",
): SpriteStyle {
  const spec = spriteFrames[state];
  const pet = getCompanionPet(petId);
  const cellHeight = Math.round(
    (cellWidth * SPRITE_CELL_HEIGHT) / SPRITE_CELL_WIDTH,
  );

  return {
    backgroundImage: `url(${pet.spritesheetUrl})`,
    backgroundRepeat: "no-repeat",
    backgroundSize: `${cellWidth * SPRITE_GRID_COLS}px ${cellHeight * pet.gridRows}px`,
    backgroundPosition: `${frame === 0 ? 0 : -frame * cellWidth}px ${
      spec.row === 0 ? 0 : -spec.row * cellHeight
    }px`,
  };
}

/** 计算与当前渲染尺寸匹配的 spritesheet background-position。 */
export function spriteBackground(
  state: CompanionAiState,
  frame: number,
  cellWidth: number,
  petId: CompanionPetId = "shuangling",
): string {
  return getSpriteStyle(state, frame, cellWidth, petId).backgroundPosition;
}
