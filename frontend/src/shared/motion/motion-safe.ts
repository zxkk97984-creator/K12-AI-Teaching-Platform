import { useEffect, useState } from "react";

/**
 * M01 · 动态偏好门控.
 *
 * The boolean means "animation is allowed", NOT "the user asked to reduce
 * motion" — keeping the polarity explicit stops the two call sites from
 * inverting each other. A user who has not expressed a preference gets
 * animation, matching the reference behaviour.
 */
export const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function query(): MediaQueryList | null {
  if (typeof window === "undefined" || !window.matchMedia) return null;
  return window.matchMedia(REDUCED_MOTION_QUERY);
}

/**
 * Read the current preference without subscribing.
 *
 * Defaults to allowing animation when the browser exposes no `matchMedia`
 * (older engines, jsdom, or a non-browser render), because hiding motion is a
 * deliberate choice rather than a fallback. Callers must still provide a
 * static final state, so a wrong answer here never leaves content invisible.
 */
export function getMotionSafe(): boolean {
  const media = query();
  return media ? !media.matches : true;
}

/**
 * Subscribe to the preference. CSS animations are still gated by the
 * `prefers-reduced-motion` media rule in the stylesheet; this hook exists for
 * the JavaScript-driven motion that the media query cannot reach — sprite
 * frame timers, canvas loops and background particles. It does not control
 * anything inside an iframe, which owns its own document.
 */
export function useMotionSafe(): boolean {
  const [motionSafe, setMotionSafe] = useState(getMotionSafe);
  useEffect(() => {
    const media = query();
    if (!media) return;
    const update = () => setMotionSafe(!media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return motionSafe;
}
