import { createContext, useContext, useMemo, useRef, type ReactNode } from "react";

type LearningHandlers = {
  beforeOpen: (promptId?: string) => string;
  beforeSend: () => Promise<void>;
};
type LearningTeacher = {
  register: (handlers: LearningHandlers) => () => void;
  beforeOpen: (promptId?: string) => string | undefined;
  beforeSend: () => Promise<void>;
  setVisible: (visible: boolean) => void;
  isVisible: () => boolean;
};
const Context = createContext<LearningTeacher | null>(null);

/** Shares the existing floating teacher with the active lesson's save/context hooks. */
export function LearningTeacherProvider({ children }: { children: ReactNode }) {
  const active = useRef<LearningHandlers | null>(null);
  const visible = useRef(false);
  const value = useMemo<LearningTeacher>(() => ({
    register: handlers => {
      active.current = handlers;
      return () => { if (active.current === handlers) active.current = null; };
    },
    beforeOpen: promptId => active.current?.beforeOpen(promptId),
    beforeSend: async () => {
      if (!active.current) throw new Error("学习页面正在切换，请稍后重试。问题草稿已保留。");
      await active.current.beforeSend();
    },
    setVisible: value => { visible.current = value; },
    isVisible: () => visible.current,
  }), []);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useLearningTeacher() {
  const value = useContext(Context);
  if (!value) throw new Error("LearningTeacherProvider is required");
  return value;
}
