import { useEffect, useState } from "react";
import { useSpriteFrame } from "../hooks/useSpriteFrame";
import {
  getCompanionPet,
  getSpriteStyle,
  type CompanionPetId,
} from "../lib/sprite";
import type { CompanionAiState } from "../types";
import { useMotionSafe } from "../../../shared/motion/motion-safe";
export function CompanionSprite({
  petId = "shuangling",
  state = "idle",
  size = 104,
}: {
  petId?: CompanionPetId;
  state?: CompanionAiState;
  size?: number;
}) {
  // M01 owns the motion preference; this component only adds the extra rule
  // that a hidden tab must not keep ticking sprite frames.
  const motionSafe = useMotionSafe();
  const [visible, setVisible] = useState(() =>
    typeof document === "undefined" ? true : document.visibilityState !== "hidden",
  );
  useEffect(() => {
    const update = () => setVisible(document.visibilityState !== "hidden");
    update();
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  const animated = motionSafe && visible;
  const frame = useSpriteFrame(state, animated);
  return (
    <span
      className="companion-sprite"
      role="img"
      aria-label={getCompanionPet(petId).displayName}
      data-state={state}
      style={{
        ...getSpriteStyle(state, frame, size, petId),
        width: size,
        height: Math.round((size * 208) / 192),
      }}
    />
  );
}
