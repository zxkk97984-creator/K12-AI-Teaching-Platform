import { useEffect, useId, useRef, useState } from 'react';
import type { InteractivePrompt } from './api';
import type { useNarration } from './useNarration';
import type { useLessonPlayback } from './useLessonPlayback';

type Narrator = ReturnType<typeof useNarration>;
export const NARRATION_LABELS = { idle: '尚未朗读', loading: '准备语音中…', speaking: '正在朗读本段', paused: '朗读已暂停', ended: '本段朗读已结束', unavailable: '当前朗读声音不可用，请选择其他声音或阅读讲解。', error: '音频播放失败，请阅读讲解或重试。' };
type Automatic = ReturnType<typeof useLessonPlayback> & { total: number; begin: () => void; manual: () => void };

function ControlText({ full, short }: { full: string; short: string }) {
  return <><span className="interactive-control-label">{full}</span><span className="interactive-control-short" aria-hidden="true">{short}</span></>;
}

function compactAudioStatus(narrator: Narrator, enabled: boolean, recorded: boolean) {
  if (!enabled) return '朗读已关闭，仍可阅读讲解';
  if (narrator.notice) return narrator.notice;
  if (narrator.muted) return '已静音，仍可阅读讲解';
  if (narrator.status === 'error') return '音频播放失败，可阅读讲解或重试';
  if (!recorded && narrator.voiceNotice.startsWith('所选声音当前不可用')) {
    return narrator.status === 'unavailable' ? '所选声音当前不可用，可阅读讲解' : `${NARRATION_LABELS[narrator.status]} · 所选声音当前不可用`;
  }
  if (narrator.status === 'unavailable' || (!recorded && narrator.voiceNotice.includes('没有可用的普通话声音'))) {
    return '没有可用的普通话声音，可阅读讲解';
  }
  return NARRATION_LABELS[narrator.status];
}

export function NarrationControls({ narrator, prompt, enabled, started, enable, play, children, automatic }: {
  narrator: Narrator; prompt?: InteractivePrompt; enabled: boolean; started: boolean;
  enable: () => void; play: (prompt: InteractivePrompt) => void; children: React.ReactNode;
  automatic?: Automatic;
}) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const root = useRef<HTMLElement>(null);
  const settingsId = useId();
  useEffect(() => {
    const footer = root.current;
    if (!footer) return;
    const closeMenus = (returnFocus = false) => {
      const menus = [...footer.querySelectorAll<HTMLDetailsElement>('details[open]')];
      if (!menus.length) return;
      menus.forEach(menu => { menu.open = false; });
      setSettingsOpen(false);
      if (returnFocus) menus.at(-1)?.querySelector<HTMLElement>('summary')?.focus();
    };
    const outside = (event: Event) => {
      if (event.target instanceof Node && !footer.contains(event.target)) closeMenus();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || !footer.querySelector('details[open]')) return;
      event.preventDefault(); event.stopPropagation(); closeMenus(true);
    };
    const exclusive = (event: Event) => {
      if (!(event.target instanceof HTMLDetailsElement) || !event.target.open) return;
      const opened = event.target;
      footer.querySelectorAll<HTMLDetailsElement>('details[open]').forEach(menu => {
        if (menu !== opened) menu.open = false;
      });
    };
    footer.addEventListener('toggle', exclusive, true);
    document.addEventListener('pointerdown', outside);
    document.addEventListener('focusin', outside);
    document.addEventListener('keydown', escape);
    return () => {
      footer.removeEventListener('toggle', exclusive, true);
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('focusin', outside);
      document.removeEventListener('keydown', escape);
    };
  }, []);
  const busy = narrator.status === 'loading';
  const recorded = Boolean(prompt?.audio);
  const missingVoice = narrator.voiceId && !narrator.voiceOptions.some(voice => voice.id === narrator.voiceId);
  const playLabel = busy ? '准备语音…' : narrator.status === 'speaking' ? '暂停讲解' : narrator.status === 'paused' ? '继续讲解' : '播放讲解';
  const automaticLabel = automatic?.running ? '暂停播放' : automatic?.status === 'paused' ? '继续播放' : automatic?.status === 'ended' ? '再看一遍' : '自动播放';
  const audioStatus = compactAudioStatus(narrator, enabled, recorded);
  const fullStatus = narrator.notice || (!enabled ? '朗读已关闭，仍可阅读讲解和操作课件。' : narrator.muted ? '已静音，仍可阅读讲解和操作课件。' : recorded ? `${NARRATION_LABELS[narrator.status]} · 本段使用课件音频，音色由音频文件决定。` : narrator.status === 'unavailable' ? narrator.voiceNotice : `${NARRATION_LABELS[narrator.status]} · ${narrator.voiceNotice}`);
  const playbackStatus = automatic?.status === 'ended' ? '演示播放完了，可以再看一遍或自己试一试' : automatic?.status === 'paused' ? '画面与讲解已暂停' : automatic?.status === 'error' ? '自动播放暂时中断，请重试' : `自动演示 ${automatic ? automatic.index + 1 : 0}/${automatic?.total ?? 0} · ${automatic?.status === 'reading' ? '按字幕播放' : '讲完本段再前进'}`;
  return <footer ref={root} className="interactive-control-area" data-pet-avoid data-automatic={automatic?.active || undefined}>
    <div className="interactive-voice-controls" aria-label="讲解朗读控制">
      <div className="interactive-control-actions">
        {automatic ? <button type="button" data-testid="lesson-autoplay" aria-label={automaticLabel} disabled={!started} onClick={() => {
          if (automatic.running) automatic.pause();
          else if (automatic.status === 'paused') automatic.resume();
          else automatic.begin();
        }}><ControlText full={automaticLabel} short={automatic.running ? '暂停' : automatic.status === 'paused' ? '继续' : automatic.status === 'ended' ? '再看' : '自动播放'} /></button> : null}
        {automatic ? <>{automatic.active ? <button type="button" className="secondary" aria-label="重播本段" disabled={!started} onClick={automatic.replay}><ControlText full="重播本段" short="重播" /></button> : null}<button type="button" className="secondary" aria-label="自己试一试" disabled={!started} onClick={automatic.manual}><ControlText full="自己试一试" short="试一试" /></button></> : null}
        {enabled ? !automatic?.active ? <><button type="button" aria-label={playLabel} disabled={!started || !prompt || busy || narrator.muted} onClick={() => {
          if (narrator.status === 'speaking') narrator.pause();
          else if (narrator.status === 'paused') narrator.resume();
          else if (prompt) play(prompt);
        }}><ControlText full={playLabel} short={busy ? '准备…' : narrator.status === 'speaking' ? '暂停' : narrator.status === 'paused' ? '继续' : '播放'} /></button>
        <button type="button" className="secondary" aria-label="重播本段" disabled={!started || !prompt || narrator.muted} onClick={() => prompt && play(prompt)}><ControlText full="重播本段" short="重播" /></button></> : null : <button type="button" aria-label="开启朗读" onClick={enable}><ControlText full="开启朗读" short="朗读" /></button>}
      </div>
      <div className="interactive-control-status">
        <p className="interactive-audio-status" title={fullStatus} role={narrator.status === 'error' || narrator.status === 'unavailable' ? 'alert' : 'status'}>{audioStatus}</p>
        {automatic?.active ? <p className="interactive-playback-status" role="status" title={`${playbackStatus}${automatic.notice ? ` · ${automatic.notice}` : ''}`}>{playbackStatus}</p> : null}
      </div>
      <div className="interactive-control-tools">
        {enabled ? <details className="interactive-voice-settings" open={settingsOpen} onToggle={event => setSettingsOpen(event.currentTarget.open)}>
          <summary aria-label="声音设置" aria-controls={settingsId} aria-expanded={settingsOpen} title="声音、语速和静音设置"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="var(--sl-surface)"/><circle cx="15" cy="17" r="3" fill="var(--sl-surface)"/></svg><span className="interactive-control-label">声音设置</span></summary>
          <div id={settingsId} className="interactive-voice-settings-content">
            <label className="interactive-voice-choice">声音<select aria-label="朗读声音" title={recorded ? '本段使用课件音频，音色由音频文件决定' : `${narrator.voiceDescription} · 下一次播放时生效，选择会保存在当前浏览器`} disabled={recorded} value={recorded ? 'recorded' : narrator.voiceId} onChange={event => narrator.selectVoice(event.target.value)}>
              {recorded ? <option value="recorded">课件音频</option> : <><option value="">自动普通话</option>{missingVoice ? <option value={narrator.voiceId}>所选声音暂不可用</option> : null}{['普通话', '粤语', '其他声音'].map(group => <optgroup key={group} label={group}>{narrator.voiceOptions.filter(voice => voice.group === group).map(voice => <option key={voice.id} value={voice.id}>{voice.label}</option>)}</optgroup>)}</>}
            </select></label>
            <label>语速<select aria-label="朗读语速" title="下一次播放时生效" value={narrator.rate} onChange={event => narrator.setRate(Number(event.target.value))}><option value="0.8">慢</option><option value="1">正常</option><option value="1.2">快</option><option value="1.5">1.5 倍</option></select></label>
            <label><input type="checkbox" checked={narrator.muted} onChange={event => { narrator.setMuted(event.target.checked); narrator.stop(); }} />静音</label>
            <p className="interactive-voice-description">{fullStatus}</p>
            {automatic?.active && automatic.notice ? <p className="interactive-voice-description">{automatic.notice}</p> : null}
            <p className="interactive-voice-description">声音与语速调整在下一次播放生效。</p>
          </div>
        </details> : null}
        {children}
      </div>
    </div>
  </footer>;
}
