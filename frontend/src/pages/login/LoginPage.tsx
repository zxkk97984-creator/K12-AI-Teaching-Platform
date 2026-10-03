import { FormEvent, useState } from "react";
import { login } from "../../features/identity/api";
import { navigate } from "../../features/identity/session";
import "./login.css";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password) { setError("请输入用户名和密码。"); return; }
    setBusy(true);
    setError(null);
    try {
      const result = await login({ username, password });
      if (result.user.role === "admin") navigate("/admin/resources");
      else navigate(result.profile?.onboarding_completed ? "/workbench" : "/onboarding");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return <main className="od-login">
    <div className="od-login-layout">
      <section className="od-login-panel" aria-labelledby="login-form-title">
        <p className="od-login-wordmark"><img src="/shuangling-brand.svg" width="32" height="32" alt="" />霜铃 K12</p>
        <h1 id="login-form-title">登录</h1>
        <form onSubmit={(event) => void submit(event)}>
          {error && <p className="od-login-error" role="alert">{error}</p>}
          <label>用户名<input name="username" autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} /></label>
          <label>密码<input name="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          <button type="submit" disabled={busy}>{busy ? "正在登录…" : "登录并继续"}<span aria-hidden="true">→</span></button>
        </form>
        <p className="od-login-privacy">本轮使用合成账户，不开放真实未成年人自助注册。</p>
      </section>
    </div>
  </main>;
}
