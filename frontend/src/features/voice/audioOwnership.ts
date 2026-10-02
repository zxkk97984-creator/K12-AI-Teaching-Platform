/** One application audio owner, including microphone capture. */
let active: { id: symbol; cancel: () => void } | null = null;
export function acquireAudio(id: symbol, cancel: () => void, automatic = false): boolean {
  if (automatic && active) return false;
  if (active && active.id !== id) {
    const previous = active;
    previous.cancel();
  }
  active = { id, cancel };
  return true;
}
export function ownsAudio(id: symbol) { return active?.id === id; }
export function releaseAudio(id: symbol) { if (ownsAudio(id)) active = null; }
