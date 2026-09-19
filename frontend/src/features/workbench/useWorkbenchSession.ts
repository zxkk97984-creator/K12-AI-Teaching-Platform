import { useCallback, useEffect, useState } from "react";
import { ApiError, getMe } from "../identity/api";
import type { MeResponse } from "../identity/types";

export type WorkbenchSession =
  | { kind: "loading" }
  | { kind: "ready"; me: MeResponse }
  | { kind: "error"; status: number | null; message: string; requestId: string | null };

/**
 * Reads the authenticated profile through the T05 request wrapper. 401 is
 * handled by the global identity listener (redirect to /login); 503 and other
 * failures become a visible error state with the real message and request id.
 */
export function useWorkbenchSession(): { state: WorkbenchSession; reload: () => void } {
  const [state, setState] = useState<WorkbenchSession>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setState({ kind: "loading" });
    getMe()
      .then((me) => {
        if (active) setState({ kind: "ready", me });
      })
      .catch((reason: unknown) => {
        if (!active) return;
        if (reason instanceof ApiError) {
          setState({
            kind: "error",
            status: reason.status,
            message: reason.message,
            requestId: reason.requestId,
          });
        } else {
          setState({
            kind: "error",
            status: null,
            message: reason instanceof Error ? reason.message : "未知错误",
            requestId: null,
          });
        }
      });
    return () => {
      active = false;
    };
  }, [attempt]);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);
  return { state, reload };
}
