import { createContext, useContext, type ReactNode } from "react";
import type { MeResponse } from "./types";

const AccountContext = createContext<MeResponse | null>(null);

export function AccountProvider({ me, children }: { me: MeResponse; children: ReactNode }) {
  return <AccountContext.Provider value={me}>{children}</AccountContext.Provider>;
}

export function useAccount() {
  return useContext(AccountContext);
}
