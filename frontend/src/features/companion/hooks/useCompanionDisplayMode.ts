import { useCallback, useState } from "react";

export type CompanionDisplayMode = "compact" | "full";

function readMode(key: string): CompanionDisplayMode {
  try {
    return localStorage.getItem(key) === "full" ? "full" : "compact";
  } catch {
    return "compact";
  }
}

/** Appearance is a bounded, account-scoped preference in this browser. */
export function useCompanionDisplayMode(userId: string) {
  const key = `k12:companion:${userId}:display:v1`;
  const [saved, setSaved] = useState(() => ({ key, mode: readMode(key) }));
  const mode = saved.key === key ? saved.mode : readMode(key);
  if (saved.key !== key) setSaved({ key, mode });

  const selectMode = useCallback((next: CompanionDisplayMode) => {
    if (next !== "full" && next !== "compact") return;
    try { localStorage.setItem(key, next); } catch { /* In-memory choice still works. */ }
    setSaved({ key, mode: next });
  }, [key]);

  return [mode, selectMode] as const;
}
