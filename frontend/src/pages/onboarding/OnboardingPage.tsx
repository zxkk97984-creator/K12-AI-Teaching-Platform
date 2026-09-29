import { FormEvent, useEffect, useState } from "react";
import { ApiError, getMe, patchPreferences, patchProfile } from "../../features/identity/api";
import { GradePicker } from "../../features/identity/GradePicker";
import { gradeLabel, gradeOption, STYLES, VOICE_OPTIONS, type MeResponse, type PreferredStyle, type VoicePreference } from "../../features/identity/types";
import { navigate } from "../../features/identity/session";
import "../settings/preferences.css";

export function OnboardingPage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [grade, setGrade] = useState<number | null>(null);
  const [style, setStyle] = useState<PreferredStyle>("AUTO");
  const [interests, setInterests] = useState("");
  const [proactive, setProactive] = useState(true);
  const [voice, setVoice] = useState<VoicePreference>("DISABLED");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getMe().then((value) => {
      setMe(value);
      if (value.profile?.grade) setGrade(value.profile.grade);
      if (value.preferences) {
        setStyle(value.preferences.preferred_style);
        setInterests(value.preferences.interests.join(", "));
        setProactive(value.preferences.proactive_guidance_enabled);
        setVoice(value.preferences.voice_preference);
      }
    }).catch((reason) => {
      if (reason instanceof ApiError && reason.status === 401) navigate("/login");
      else setError(reason instanceof Error ? `无法读取档案：${reason.message}` : "无法读取档案");
    });
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!me?.profile) return;
    const chosen = gradeOption(grade);
    if (!chosen) { setError("请选择你现在的年级"); return; }
    setBusy(true);
    setError(null);
    try {
      const profileResult = await patchProfile({
        base_revision: me.profile.revision,
        stage: chosen.stage,
        grade,
      });
      setMe(profileResult);
      const revision = profileResult.profile?.revision;
      if (revision === undefined) throw new Error("档案保存失败");
      const final = await patchPreferences({
        base_revision: revision,
        preferred_style: style,
        interests: interests.split(",").map((item) => item.trim()).filter(Boolean),
        proactive_guidance_enabled: proactive,
        voice_preference: voice,
      });
      setMe(final);
      navigate("/workbench");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  if (!me) return <main className="auth-shell"><section className="auth-card">{error ? <><h1>暂时无法打开</h1><p className="form-error" role="alert">{error}</p></> : <p>正在读取档案…</p>}</section></main>;
  return (
    <main className="auth-shell od-preferences">
      <section className="auth-card wide">
        <p className="eyebrow">从适合你的内容开始</p>
        <h1>你现在读几年级？</h1>
        <p className="muted">选好具体年级，霜铃会自动匹配适合你的阅读、练习和讲解入口。</p>
        <form onSubmit={submit}>
          <GradePicker value={grade} onChange={(value) => setGrade(value)} name="onboarding-grade" />
          <label>偏好讲解方式<select value={style} onChange={(e) => setStyle(e.target.value as PreferredStyle)}>{STYLES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          {/* R28: a free-text field submits on Enter, so an in-progress Chinese
    composition must be allowed to finish instead of firing the form. */}
          <label>兴趣（逗号分隔）<input value={interests} onChange={(e) => setInterests(e.target.value)} onKeyDown={(event) => { if (event.nativeEvent.isComposing || event.keyCode === 229) return; }} /></label>
          <label className="check"><input type="checkbox" checked={proactive} onChange={(e) => setProactive(e.target.checked)} /> 允许教学助手主动引导下一小步</label>
          <label>语音偏好（互动问题可朗读）<select value={voice} onChange={(e) => setVoice(e.target.value as VoicePreference)}>{VOICE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button type="submit" disabled={busy}>{busy ? "正在保存…" : `完成设置，进入${grade === null ? "学习" : gradeLabel(grade)}首页 →`}</button>
        </form>
      </section>
    </main>
  );
}
