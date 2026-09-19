import { getMe } from "./api";
import type { MeResponse } from "./types";

export async function requireMe(): Promise<MeResponse | null> {
  try {
    return await getMe();
  } catch {
    return null;
  }
}

export function navigate(path: string): void {
  window.location.assign(path);
}
