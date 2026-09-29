import { getMe } from "./api";
import type { MeResponse } from "./types";

export async function requireMe(): Promise<MeResponse | null> {
  try {
    return await getMe();
  } catch {
    return null;
  }
}

type Navigator = (path: string) => void;
let clientNavigate: Navigator | null = null;
export function registerNavigator(navigator: Navigator): () => void {
  clientNavigate = navigator;
  return () => {
    if (clientNavigate === navigator) clientNavigate = null;
  };
}
export function navigate(path: string): void {
  if (clientNavigate) clientNavigate(path);
  else window.location.assign(path);
}
