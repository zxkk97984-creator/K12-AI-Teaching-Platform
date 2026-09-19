import type { Stage } from "../identity/types";

export type Density = "spacious" | "compact";

/**
 * Low grades get fewer simultaneous actions and larger controls. This is a
 * layout/density decision from the four-stage policy, not a colour swap.
 * A student without a stage only reaches this code inside tests, where
 * "compact" keeps the DOM predictable while the page asks for onboarding.
 */
export function densityForStage(stage: Stage | null | undefined): Density {
  if (stage === "PRIMARY_LOWER" || stage === "PRIMARY_UPPER") return "spacious";
  return "compact";
}
