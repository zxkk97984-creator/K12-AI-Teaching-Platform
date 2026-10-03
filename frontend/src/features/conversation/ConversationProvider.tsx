import {
  createContext,
  useContext,
  useLayoutEffect,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { useAccount } from "../identity/AccountContext";
import { ConversationController } from "./controller";
export const ConversationContext = createContext<ConversationController | null>(
  null,
);
export function ConversationProvider({ children }: { children: ReactNode }) {
  const account = useAccount();
  const [controller] = useState(() => new ConversationController(account?.user.id, account?.profile?.stage ?? undefined));
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
