import { chooseNarrationVoice, narrationVoiceGroup, narrationVoiceId, narrationVoiceLabel } from "../../features/interactive/narrationVoices";
import { narrationVoiceStorageKey, useNarrationVoice } from "../../features/interactive/useNarrationVoice";

export function NarrationVoiceSettings({ userId }: { userId: string }) {
  const { voices, voiceId, selectVoice } = useNarrationVoice(narrationVoiceStorageKey(userId));
  const choice = chooseNarrationVoice(voices, voiceId);
  return <label className="settings-field" id="settings-narration-voice">
    <span>朗读声音</span>
    <select aria-label="朗读声音" value={voiceId} onChange={(event) => selectVoice(event.target.value)}>
      <option value="">自动普通话</option>
      {choice.missingSelection ? <option value={voiceId}>所选声音暂不可用</option> : null}
      {["普通话", "粤语", "其他声音"].map((group) => <optgroup key={group} label={group}>{voices.filter((voice) => narrationVoiceGroup(voice) === group).map((voice) => <option key={narrationVoiceId(voice)} value={narrationVoiceId(voice)}>{narrationVoiceLabel(voice)}</option>)}</optgroup>)}
    </select>
    <small>{choice.voice ? `当前声音：${narrationVoiceLabel(choice.voice)}。` : "当前浏览器没有可用的普通话声音，可在有中文声音的 Edge／Chrome 中选择。"}选择后立即生效，保存在当前账号的本机浏览器中，课文与互动朗读共用。</small>
  </label>;
}
