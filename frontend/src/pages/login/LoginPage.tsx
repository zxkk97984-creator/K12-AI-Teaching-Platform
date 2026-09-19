import { FormEvent, useState } from "react";
import { login } from "../../features/identity/api";
import { navigate } from "../../features/identity/session";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await login({ username, password });
      if (result.user.role === "admin") navigate("/");
      else navigate(result.profile?.onboarding_completed ? "/settings" : "/onboarding");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <p className="eyebrow">霜铃 · 本地身份</p>
        <h1>回到你的学习空间</h1>
        <p className="muted">本轮只使用合成账户，不开放真实未成年人自助注册。</p>
        <form onSubmit={submit}>
          <label>用户名<input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} /></label>
          <label>密码<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button type="submit" disabled={busy}>{busy ? "正在登录…" : "登录"}</button>
        </form>
      </section>
    </main>
  );
}
