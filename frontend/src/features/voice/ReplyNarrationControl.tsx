import { useNarration } from "../interactive/useNarration";
import { replyNarrationText } from "./replyNarration";
export function ReplyNarrationControl({ messageId, text }: { messageId: string; text: string }) {
  const voice = useNarration(() => "");
  const prose = replyNarrationText(text);
  const active = ["loading", "speaking", "paused"].includes(voice.status);
  return <div className="conv-message-actions">
    <button type="button" className="secondary" aria-label="朗读回复" disabled={!prose || voice.status === "loading" || !voice.outputEnabled} onClick={() => {
      if (voice.status === "speaking") voice.pause();
      else if (voice.status === "paused") voice.resume();
      else void voice.play({ id: `reply-${messageId}`, scene_id: "reply", text: prose, audio: null, trigger: "MANUAL" });
    }}>{voice.status === "loading" ? "准备语音…" : voice.status === "speaking" ? "暂停朗读" : voice.status === "paused" ? "继续朗读" : "朗读"}</button>
    {active ? <button type="button" className="secondary" onClick={voice.stop}>停止朗读</button> : null}
    <span className="conv-voice-note conv-reply-voice-status" role="status">{!voice.outputEnabled ? "语音输出已关闭，可在设置中开启。" : voice.notice || (voice.status === "error" ? "播放失败，请手动重试。" : voice.status === "unavailable" ? voice.voiceNotice : "")}</span>
  </div>;
}
