import { useEffect, useState } from "react";

import { SPRITE_FRAME_MS } from "../lib/sprite";
import { spriteFrames, type CompanionAiState } from "../types";

/** 每 220ms 切帧（对齐原型 animateSprites），按状态 frames 循环 */
export function useSpriteFrame(
  state: CompanionAiState,
  animated = true,
): number {
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    setFrame(0);
    if (!animated) return;
    const frames = spriteFrames[state].frames;
    const timer = window.setInterval(() => {
      setFrame((current) => (current + 1) % frames);
    }, SPRITE_FRAME_MS);
    return () => window.clearInterval(timer);
  }, [animated, state]);

  return frame;
}
