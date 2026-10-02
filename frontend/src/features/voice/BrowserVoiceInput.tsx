import { useSpeechInput } from "./useSpeechInput";
export function BrowserVoiceInput(props: Parameters<typeof useSpeechInput>[0] & { compact?: boolean }) {
  const input = useSpeechInput(props);
  const recording = input.status === "listening" || input.status === "stopping";
  const idleHint = !input.supported ? "当前浏览器不支持语音输入，可直接打字。" : props.enabled === false ? "语音输入已关闭，可在设置中开启。" : "";
  return <span className="conv-voice-control">
    <button type="button" className="secondary conv-voice-button" onClick={input.toggle}
      disabled={props.disabled || props.enabled === false || !input.supported || input.status === "stopping"}
      aria-pressed={recording} aria-label={recording ? "停止语音输入" : "开始语音输入"}
      title={idleHint || "语音转文字，识别结果放入输入框，修改后手动发送"} data-testid="voice-input">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={recording ? "M6 6h12v12H6z" : "M9 4a3 3 0 0 1 6 0v8a3 3 0 0 1-6 0zM5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"} /></svg>
    </button>
    <span className="conv-voice-note conv-voice-feedback" role={input.status === "error" ? "alert" : "status"}>
      {idleHint ? props.compact ? "" : idleHint : recording ? input.status === "stopping" ? "正在结束识别…" : "正在听，请说话…" : input.notice}
    </span>
  </span>;
}
