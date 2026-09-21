import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useBlocker, useBeforeUnload } from "react-router-dom";

type EditingEntry = { dirty: boolean };
type EditingContextValue = { register: (id: string, entry: EditingEntry) => () => void };
const EditingContext = createContext<EditingContextValue | null>(null);

export function EditingGuardProvider({ children }: { children: ReactNode }) {
  const entries = useRef(new Map<string, EditingEntry>());
  const [dirty, setDirty] = useState(false);
  // Recompute the aggregate from the registry and only publish a change when
  // the boolean actually flips. Bumping a counter on every register/unregister
  // re-rendered the provider, which minted a new context object, which re-ran
  // every consumer's effect, which registered again: an update loop.
  const sync = useCallback(() => {
    setDirty(Array.from(entries.current.values()).some((entry) => entry.dirty));
  }, []);
  const register = useCallback((id: string, entry: EditingEntry) => {
    entries.current.set(id, entry);
    sync();
    return () => {
      entries.current.delete(id);
      sync();
    };
  }, [sync]);
  // The context value must keep a stable identity across renders, otherwise
  // consumers that depend on it re-run their registration effect forever.
  const value = useMemo(() => ({ register }), [register]);
  const blocker = useBlocker(dirty);
  useBeforeUnload((event) => {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm("当前页面有未保存的修改，确认放弃并离开吗？")) blocker.proceed();
    else blocker.reset();
  }, [blocker]);
  return <EditingContext.Provider value={value}>{children}</EditingContext.Provider>;
}

export function useEditingRegistration(id: string, dirty: boolean) {
  const context = useContext(EditingContext);
  useEffect(() => {
    if (!context) return undefined;
    return context.register(id, { dirty });
  }, [context, id, dirty]);
}
