import {
  createContext,
  useContext,
  useLayoutEffect,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { ConversationController } from "./controller";
export const ConversationContext = createContext<ConversationController | null>(
  null,
);
export function ConversationProvider({ children }: { children: ReactNode }) {
  const [controller] = useState(() => new ConversationController());
  useLayoutEffect(() => {
    controller.activate();
    return () => controller.dispose();
  }, [controller]);
  return (
    <ConversationContext.Provider value={controller}>
      {children}
    </ConversationContext.Provider>
  );
}
export function useConversation() {
  const controller = useContext(ConversationContext);
  if (!controller) throw new Error("ConversationProvider required");
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
  );
  return { controller, ...state };
}
