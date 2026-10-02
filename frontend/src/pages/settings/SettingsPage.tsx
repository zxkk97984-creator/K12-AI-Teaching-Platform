import { useEffect, useState } from "react";
import { CompanionPetPicker } from "../../features/companion/CompanionPetPicker";
import { getCompanionPet, type CompanionPetId } from "../../features/companion/lib/sprite";
import { AccountAvatar } from "../../features/identity/AccountAvatar";
import { GradePicker } from "../../features/identity/GradePicker";
import { NarrationVoiceSettings } from "./NarrationVoiceSettings";
import {
  ApiError, deleteAvatar, getMe, logout, patchPreferences, patchProfile, uploadAvatar,
} from "../../features/identity/api";
import {
  gradeLabel, gradeOption, STYLES, TEACHER_STYLES, VOICE_OPTIONS,
  type MeResponse, type PreferredStyle, type TeacherStyle, type VoicePreference,
} from "../../features/identity/types";
import { navigate } from "../../features/identity/session";
import "./preferences.css";

const AVATAR_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);
const AVATAR_LIMIT = 2 * 1024 * 1024;

export function SettingsPage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [nickname, setNickname] = useState("");
  const [grade, setGrade] = useState<number | null>(null);
  const [style, setStyle] = useState<PreferredStyle>("AUTO");
  const [teacherStyle, setTeacherStyle] = useState<TeacherStyle>("AUTO");
  const [companionPetId, setCompanionPetId] = useState<CompanionPetId>("shuangling");
  const [interests, setInterests] = useState("");
  const [proactive, setProactive] = useState(true);
  const [voice, setVoice] = useState<VoicePreference>("DISABLED");
  const [autoRead, setAutoRead] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [avatarMessage, setAvatarMessage] = useState("");
  const [avatarError, setAvatarError] = useState("");
  const [busy, setBusy] = useState(false);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const narrationTargetRequested = window.location.hash === "#settings-narration-voice";
  useEffect(() => {
    if (me?.user.id && narrationTargetRequested) {
      document.getElementById("settings-narration-voice")?.scrollIntoView?.({ block: "center" });
    }
  }, [me?.user.id, narrationTargetRequested]);

  useEffect(() => {
    let active = true;
    void getMe().then((value) => {
      if (!active) return;
      setMe(value);
      setNickname(value.profile?.nickname ?? "");
      setGrade(value.profile?.grade ?? null);
      if (value.preferences) {
        setStyle(value.preferences.preferred_style);
        setTeacherStyle(value.preferences.teacher_style);
        setCompanionPetId(getCompanionPet(value.preferences.companion_pet_id).id);
        setInterests(value.preferences.interests.join(", "));
        setProactive(value.preferences.proactive_guidance_enabled);
        setVoice(value.preferences.voice_preference);
        setAutoRead(value.preferences.auto_read_replies ?? false);
      }
    }).catch((reason) => {
      if (!active) return;
      if (reason instanceof ApiError && reason.status === 401) navigate("/login");
      else setError(reason instanceof Error ? `无法读取设置：${reason.message}` : "无法读取设置");
    });
    return () => { active = false; };
  }, []);

  async function save() {
    if (!me?.profile || !me.preferences || busy || avatarBusy) return;
    const chosen = gradeOption(grade);
    if (grade !== null && !chosen) { setError("请重新选择年级"); return; }
    const normalizedName = nickname.trim() || null;
    const interestList = interests.split(",").map((item) => item.trim()).filter(Boolean);
    setBusy(true);
    setError("");
    setMessage("");
    let latest = me;
    try {
      const gradeChanged = Boolean(chosen && (
        grade !== me.profile.grade || chosen.stage !== me.profile.stage
      ));
      const profileChanged = normalizedName !== (me.profile.nickname ?? null) || gradeChanged;
      if (profileChanged) {
        latest = await patchProfile({
          base_revision: me.profile.revision,
          nickname: normalizedName,
          ...(chosen && gradeChanged ? { stage: chosen.stage, grade } : {}),
        });
        setMe(latest);
        setNickname(latest.profile?.nickname ?? "");
      }
      const preferenceChanged = style !== me.preferences.preferred_style
        || teacherStyle !== me.preferences.teacher_style
        || companionPetId !== me.preferences.companion_pet_id
        || interestList.join("\u0000") !== me.preferences.interests.join("\u0000")
        || proactive !== me.preferences.proactive_guidance_enabled
        || voice !== me.preferences.voice_preference
        || autoRead !== (me.preferences.auto_read_replies ?? false);
      if (preferenceChanged) {
        latest = await patchPreferences({
          base_revision: latest.profile?.revision ?? me.preferences.profile_revision,
          preferred_style: style,
          teacher_style: teacherStyle,
          companion_pet_id: companionPetId,
          interests: interestList,
          proactive_guidance_enabled: proactive,
          voice_preference: voice,
          auto_read_replies: autoRead,
        });
        setMe(latest);
        setCompanionPetId(getCompanionPet(latest.preferences?.companion_pet_id ?? "").id);
      }
      setMessage(profileChanged || preferenceChanged ? "已保存到当前账号，侧栏与学习内容已同步。" : "没有需要保存的修改。");
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        // Refresh the revision without replacing the student's unsaved choices.
        try { setMe(await getMe()); } catch { /* retain choices and show original failure */ }
      }
      setError(`${latest !== me ? "个人资料已保存，但学习偏好未保存：" : "保存失败："}${reason instanceof Error ? reason.message : "请重试"}`);
    } finally {
      setBusy(false);
    }
  }

  async function onAvatarFile(file: File | undefined) {
    if (!file || !me?.profile || avatarBusy) return;
    setAvatarError(""); setAvatarMessage("");
    if (!AVATAR_TYPES.has(file.type)) { setAvatarError("请选择 PNG、JPG 或 WebP 图片。"); return; }
    if (file.size > AVATAR_LIMIT) { setAvatarError("头像文件不能超过 2 MB。"); return; }
    setAvatarBusy(true);
    try {
      const updated = await uploadAvatar(file);
      setMe(updated);
      setAvatarMessage("头像已保存到当前账号。");
    } catch (reason) {
      setAvatarError(reason instanceof Error ? reason.message : "头像上传失败，请重试");
    } finally {
      setAvatarBusy(false);
    }
  }

  async function removeCurrentAvatar() {
    if (!me?.profile?.avatar_url || avatarBusy) return;
    setAvatarBusy(true);
    setAvatarError(""); setAvatarMessage("");
    try {
      const updated = await deleteAvatar();
      setMe(updated);
      setAvatarMessage("头像已移除。");
    } catch (reason) {
      setAvatarError(reason instanceof Error ? reason.message : "无法移除头像，请重试");
    } finally {
      setAvatarBusy(false);
    }
  }

  async function signOut() {
    try { await logout(); navigate("/login"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "退出失败，请重试"); }
  }

  if (!me) return <main className="settings-loading" role="status">{error || "正在读取学习设置…"}</main>;
  if (me.user.role === "admin") return <main className="settings-page settings-page--admin"><h1>管理员账号</h1><p>当前登录账号：{me.user.username}</p><button type="button" onClick={() => void signOut()}>退出登录</button></main>;
  if (!me.profile?.onboarding_completed) { navigate("/onboarding"); return null; }

  const displayName = me.profile.nickname || me.user.username;
  const selectedPet = getCompanionPet(companionPetId);
  const petChanged = companionPetId !== me.preferences?.companion_pet_id;
  return <main className="settings-page" data-testid="settings-page">
    <header className="settings-intro">
      <div><p className="settings-eyebrow">个人设置 / MY SPACE</p><h1>设置你的学习空间</h1><p>选好年级，让霜铃把合适的内容放在你面前。头像与昵称会同步到左侧导航。</p><a className="settings-pet-shortcut" href="#settings-companion-title">选择桌宠形象 ↓</a></div>
      <span className="settings-current-grade">{gradeLabel(me.profile.grade)}</span>
    </header>

    <div className="settings-grid">
      <div className="settings-main-column">
        <section className="settings-panel settings-profile" aria-labelledby="settings-profile-title">
          <div className="settings-section-head"><span className="settings-index">01</span><div><h2 id="settings-profile-title">个人资料</h2><p>用你喜欢的名字和头像开始学习。</p></div></div>
          <div className="settings-avatar-row">
            <AccountAvatar me={me} size="large" />
            <div className="settings-avatar-copy"><strong>{displayName}</strong><span>支持 PNG、JPG、WebP；最大 2 MB。图片会裁成正方形。</span><div className="settings-avatar-actions">
              <label className="settings-upload-control" htmlFor="settings-avatar-file">{avatarBusy ? "正在保存…" : "上传新头像"}</label>
              <input id="settings-avatar-file" type="file" accept="image/png,image/jpeg,image/webp" disabled={avatarBusy || busy} onChange={(event) => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; void onAvatarFile(file); }} />
              {me.profile.avatar_url && <button type="button" className="settings-text-button" disabled={avatarBusy} onClick={() => void removeCurrentAvatar()}>移除头像</button>}
            </div></div>
          </div>
          {avatarMessage && <p className="settings-inline-success" role="status">{avatarMessage}</p>}
          {avatarError && <p className="settings-inline-error" role="alert">{avatarError}</p>}
          <label className="settings-field" htmlFor="settings-nickname"><span>昵称</span><input id="settings-nickname" value={nickname} maxLength={24} placeholder="你希望大家怎么称呼你？" onChange={(event) => setNickname(event.target.value)} /><small>只改变页面显示名称，登录账号仍是 {me.user.username}。</small></label>
        </section>

        <section className="settings-panel settings-grade-panel" aria-labelledby="settings-grade-title">
          <div className="settings-section-head"><span className="settings-index">02</span><div><h2 id="settings-grade-title">我的年级</h2><p>选好现在的年级，学习内容会随之更新。</p></div></div>
          <GradePicker value={grade} onChange={(value) => setGrade(value)} />
          {grade === null && <p className="settings-grade-note">还未设置具体年级；当前仍按已有学段展示学习内容。</p>}
        </section>
      </div>

      <div className="settings-side-column">
        <section className="settings-panel settings-companion" aria-labelledby="settings-companion-title">
          <div className="settings-section-head"><span className="settings-index">03</span><div><h2 id="settings-companion-title">桌宠形象</h2><p>选一个陪你学习的伙伴，也可以在桌宠对话中更换。</p></div></div>
          <CompanionPetPicker value={companionPetId} onChange={setCompanionPetId} disabled={busy || avatarBusy} />
          <p className="settings-pet-status" role="status">{petChanged ? `已选择${selectedPet.displayName}，保存设置后生效。` : `当前陪伴你的是${selectedPet.displayName}。`}</p>
        </section>
        <section className="settings-panel settings-learning" aria-labelledby="settings-learning-title">
          <div className="settings-section-head"><span className="settings-index">04</span><div><h2 id="settings-learning-title">学习偏好</h2><p>这些设置会影响教师讲解方式，不改变你的年级。</p></div></div>
          <div className="settings-fields">
            <label className="settings-field"><span>偏好讲解方式</span><select value={style} onChange={(event) => setStyle(event.target.value as PreferredStyle)}>{STYLES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
            <label className="settings-field"><span>教师风格</span><select value={teacherStyle} onChange={(event) => setTeacherStyle(event.target.value as TeacherStyle)}>{TEACHER_STYLES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
            <label className="settings-field"><span>感兴趣的内容</span><input value={interests} onChange={(event) => setInterests(event.target.value)} placeholder="例如：机器人、绘画" /><small>用逗号分隔，最多十项。</small></label>
            <label className="settings-field"><span>语音偏好</span><select value={voice} onChange={(event) => setVoice(event.target.value as VoicePreference)}>{VOICE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select><small>朗读不会自动开启麦克风。</small></label>
            <NarrationVoiceSettings userId={me.user.id} />
            <label className="settings-toggle"><input type="checkbox" checked={autoRead} onChange={(event) => setAutoRead(event.target.checked)} /><span><strong>自动朗读新回复</strong><small>默认关闭；仅在语音输出开启时朗读当前对话的新回复一次，不打断课文、课件或录音。</small></span></label>
            <label className="settings-toggle"><input type="checkbox" checked={proactive} onChange={(event) => setProactive(event.target.checked)} /><span><strong>主动引导</strong><small>需要时由霜铃提示下一步。</small></span></label>
          </div>
        </section>
      </div>
    </div>

    <footer className="settings-savebar"><div>{message && <p className="settings-inline-success" role="status">{message}</p>}{error && <p className="settings-inline-error" role="alert">{error}</p>}{!message && !error && <p>个人资料和学习偏好仅对当前账号生效。</p>}</div><div className="settings-save-actions"><button type="button" className="settings-signout" onClick={() => void signOut()}>退出登录</button><button type="button" className="settings-save-button" disabled={busy || avatarBusy} onClick={() => void save()}>{busy ? "正在保存…" : "保存设置"}</button></div></footer>
  </main>;
}
