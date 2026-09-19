import { useEffect, useState } from "react";
import { ApiError, getMe, logout, patchPreferences } from "../../features/identity/api";
import { stageLabel, STYLES, VOICE_OPTIONS, type MeResponse, type PreferredStyle, type VoicePreference } from "../../features/identity/types";
import { navigate } from "../../features/identity/session";
import "../../features/workbench/workbench.css";

export function SettingsPage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [style, setStyle] = useState<PreferredStyle>("AUTO");
  const [interests, setInterests] = useState("");
  const [proactive, setProactive] = useState(true);
  const [voice, setVoice] = useState<VoicePreference>("DISABLED");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getMe().then((value) => {
      setMe(value);
      if (value.preferences) {
        setStyle(value.preferences.preferred_style);
        setInterests(value.preferences.interests.join(", "));
        setProactive(value.preferences.proactive_guidance_enabled);
        setVoice(value.preferences.voice_preference);
      }
    }).catch((reason) => {
      if (reason instanceof ApiError && reason.status === 401) navigate("/login");
      else setError(reason instanceof Error ? `无法读取设置：${reason.message}` : "无法读取设置");
    });
  }, []);

  async function save() {
    if (!me?.preferences) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await patchPreferences({
        base_revision: me.preferences.profile_revision,
        preferred_style: style,
        interests: interests.split(",").map((item) => item.trim()).filter(Boolean),
        proactive_guidance_enabled: proactive,
        voice_preference: voice,
      });
      setMe(updated);
      setMessage("偏好已保存");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    await logout();
    navigate("/login");
  }

  if (!me) return <main className="auth-shell"><section className="auth-card">{error ? <><h1>暂时无法打开</h1><p className="form-error" role="alert">{error}</p></> : <p>正在读取档案…</p>}</section></main>;
  if (me.user.role === "admin") {
    return (
      <main className="auth-shell">
        <section className="auth-card">
          <p className="eyebrow">管理员</p>
          <h1>{me.user.username}</h1>
          <p className="muted">管理员身份由服务端校验。本轮不提供批量用户管理入口。</p>
          <button type="button" onClick={signOut}>退出登录</button>
        </section>
      </main>
    );
  }
  if (!me.profile?.onboarding_completed) {
    navigate("/onboarding");
    return null;
  }

  return (
    <main className="auth-shell">
      <section className="auth-card wide">
        <p className="eyebrow">设置</p>
        <h1>{me.user.username}</h1>
        <p className="muted">学段：{stageLabel(me.profile.stage)} · 档案版本 {me.profile.revision}</p>
        <div className="form-grid">
          <label>偏好讲解方式<select value={style} onChange={(e) => setStyle(e.target.value as PreferredStyle)}>{STYLES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          <label>兴趣（逗号分隔）<input value={interests} onChange={(e) => setInterests(e.target.value)} /></label>
          <label className="check"><input type="checkbox" checked={proactive} onChange={(e) => setProactive(e.target.checked)} /> 主动引导</label>
          <label>语音偏好（能力尚未启用）<select value={voice} onChange={(e) => setVoice(e.target.value as VoicePreference)}>{VOICE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        </div>
        {message && <p className="form-success" role="status">{message}</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="actions"><a className="wb-link" href="/workbench">打开学习工作台</a><button type="button" onClick={save} disabled={busy}>{busy ? "正在保存…" : "保存偏好"}</button><button type="button" className="secondary" onClick={signOut}>退出登录</button></div>
      </section>
    </main>
  );
}
