import type { InteractivePrompt } from './api';
import type { useNarration } from './useNarration';

type Narrator = ReturnType<typeof useNarration>;
export const NARRATION_LABELS = { idle: '尚未朗读', loading: '准备语音中…', speaking: '正在朗读本段', paused: '朗读已暂停', ended: '本段朗读已结束', unavailable: '当前朗读声音不可用，请选择其他声音或阅读讲解。', error: '音频播放失败，请阅读讲解或重试。' };
export function NarrationControls({ narrator, prompt, enabled, started, enable, play, children }: {
  narrator: Narrator; prompt?: InteractivePrompt; enabled: boolean; started: boolean;
  enable: () => void; play: (prompt: InteractivePrompt) => void; children: React.ReactNode;
}) {
  const busy = narrator.status === 'loading';
  const recorded = Boolean(prompt?.audio);
  const missingVoice = narrator.voiceId && !narrator.voiceOptions.some(voice => voice.id === narrator.voiceId);
  return <footer className="interactive-control-area" data-pet-avoid>
    <div className="interactive-voice-controls" aria-label="讲解朗读控制">
      {enabled ? <><button type="button" disabled={!started || !prompt || busy || narrator.muted} onClick={() => {
        if (narrator.status === 'speaking') narrator.pause();
        else if (narrator.status === 'paused') narrator.resume();
        else if (prompt) play(prompt);
      }}>{busy ? '准备语音…' : narrator.status === 'speaking' ? '暂停讲解' : narrator.status === 'paused' ? '继续讲解' : '播放讲解'}</button>
      <button type="button" className="secondary" disabled={!started || !prompt || narrator.muted} onClick={() => prompt && play(prompt)}>重播本段</button>
      <label className="interactive-voice-choice">声音<select aria-label="朗读声音" title={recorded ? '本段使用课件音频，音色由音频文件决定' : `${narrator.voiceDescription} · 下一次播放时生效，选择会保存在当前浏览器`} disabled={recorded} value={recorded ? 'recorded' : narrator.voiceId} onChange={event => narrator.selectVoice(event.target.value)}>
        {recorded ? <option value="recorded">课件音频</option> : <><option value="">自动普通话</option>{missingVoice ? <option value={narrator.voiceId}>所选声音暂不可用</option> : null}{['普通话', '粤语', '其他声音'].map(group => <optgroup key={group} label={group}>{narrator.voiceOptions.filter(voice => voice.group === group).map(voice => <option key={voice.id} value={voice.id}>{voice.label}</option>)}</optgroup>)}</>}
      </select></label>
      <label>语速<select aria-label="朗读语速" title="下一次播放时生效" value={narrator.rate} onChange={event => narrator.setRate(Number(event.target.value))}><option value="0.8">慢</option><option value="1">正常</option><option value="1.2">快</option></select></label>
      <label><input type="checkbox" checked={narrator.muted} onChange={event => { narrator.setMuted(event.target.checked); narrator.stop(); }} />静音</label></> : <button type="button" onClick={enable}>开启朗读</button>}
      {children}
    </div>
    <p className="interactive-audio-status" role={narrator.status === 'error' || narrator.status === 'unavailable' ? 'alert' : 'status'}>{!enabled ? '朗读已关闭，仍可阅读讲解和操作课件。' : narrator.muted ? '已静音，仍可阅读讲解和操作课件。' : NARRATION_LABELS[narrator.status]}{enabled ? recorded ? ' · 本段使用课件音频，音色由音频文件决定。语速调整在下一次播放生效。' : ` · ${narrator.voiceNotice} · 声音与语速调整在下一次播放生效` : ''}</p>
  </footer>;
}
