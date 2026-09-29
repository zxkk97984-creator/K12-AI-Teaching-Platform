import type { MeResponse } from "./types";
import "./account-avatar.css";

export function AccountAvatar({ me, size = "sidebar" }: { me: MeResponse; size?: "sidebar" | "large" }) {
  const name = me.profile?.nickname?.trim() || me.user.username;
  const initial = Array.from(name)[0]?.toUpperCase() ?? "?";
  return <span className={`account-avatar account-avatar--${size}`} aria-hidden="true">
    {me.profile?.avatar_url ? <img src={me.profile.avatar_url} alt="" /> : <span>{initial}</span>}
  </span>;
}
