import { useEffect, useRef, useState } from "react";
import type { VoiceComposerProps, VoiceInteractionState } from "./types";
import { LOCAL_VOICE_CAPABILITY } from "./types";
import "./voice.css";

const STATE_LABELS: Record<VoiceInteractionState, string> = {
  IDLE: "未开始录音",
  REQUESTING_PERMISSION: "等待麦克风权限…",
  RECORDING: "正在录音",
  TRANSCRIBING: "正在转写…",
  READY_TO_SEND: "转写完成，请确认文字",
  CANCELLED: "录音已取消",
  ERROR: "语音不可用",
};

export function VoiceComposer({
  preference,
  capability = LOCAL_VOICE_CAPABILITY,
  transcribe,
  onSendText,
}: VoiceComposerProps) {
  const [state, setState] = useState<VoiceInteractionState>("IDLE");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const cancelled = useRef(false);

  function releaseStream() {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    recorder.current = null;
  }

  useEffect(() => releaseStream, []);

  async function startRecording() {
    setError(null);
    if (preference === "DISABLED") {
      setState("ERROR");
      setError("语音输入已关闭；文本输入仍然可用。请在设置中主动开启。 ");
      return;
    }
    if (capability.inputState !== "READY") {
      setState("ERROR");
      setError(capability.reason);
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setState("ERROR");
      setError("当前浏览器没有可用的受支持录音能力；文本输入仍然可用。 ");
      return;
    }
    setState("REQUESTING_PERMISSION");
    cancelled.current = false;
    try {
      const acquired = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = acquired;
      const chunks: BlobPart[] = [];
      const active = new MediaRecorder(acquired);
      recorder.current = active;
      active.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data);
      };
      active.onstop = async () => {
        releaseStream();
        if (cancelled.current) return;
        if (!transcribe) {
          setState("ERROR");
          setError("语音 provider 尚未配置；没有上传音频。 ");
          return;
        }
        setState("TRANSCRIBING");
        try {
          const text = await transcribe(new Blob(chunks, { type: active.mimeType }));
          setDraft(text);
          setState("READY_TO_SEND");
        } catch {
          setState("ERROR");
          setError("转写失败；文本输入仍然可用。 ");
        }
      };
      active.start();
      setState("RECORDING");
    } catch (caught) {
      releaseStream();
      setState("ERROR");
      setError(caught instanceof DOMException && caught.name === "NotAllowedError"
        ? "麦克风权限被拒绝；没有上传音频，文本输入仍然可用。"
        : "无法开始录音；文本输入仍然可用。 ");
    }
  }

  function cancelRecording() {
    cancelled.current = true;
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
    releaseStream();
    setState("CANCELLED");
    setError(null);
  }

  function finishRecording() {
    if (!recorder.current || recorder.current.state === "inactive") return;
    recorder.current.stop();
  }

  function sendDraft() {
    if (!draft.trim() || !onSendText) return;
    onSendText(draft.trim());
    setDraft("");
    setState("IDLE");
  }

  const recording = state === "RECORDING" || state === "REQUESTING_PERMISSION";
  return (
    <section className="voice-composer" aria-label="语音输入边界" data-testid="voice-composer">
      <div className="voice-composer__header">
        <div>
          <p className="eyebrow">语音辅助</p>
          <p className="voice-composer__status" data-testid="voice-status">
            {STATE_LABELS[state]}
          </p>
        </div>
        <span className="voice-composer__badge" data-testid="voice-capability">
          {capability.inputState === "READY" ? "已配置 provider" : "未配置 provider"}
        </span>
      </div>
      <p className="voice-composer__reason">{capability.reason}</p>
      <div className="voice-composer__actions">
        <button
          type="button"
          className="secondary"
          onClick={() => void startRecording()}
          disabled={recording || state === "TRANSCRIBING"}
          data-testid="voice-start"
        >
          开始录音
        </button>
        {recording ? (
          <>
            <button type="button" className="secondary" onClick={finishRecording} data-testid="voice-stop">
              完成录音
            </button>
            <button type="button" className="secondary" onClick={cancelRecording} data-testid="voice-cancel">
              取消录音
            </button>
          </>
        ) : null}
      </div>
      {state === "READY_TO_SEND" || draft ? (
        <label className="voice-composer__draft">
          转写文本（可编辑）
          <textarea value={draft} onChange={(event) => setDraft(event.target.value)} />
          <button type="button" onClick={sendDraft} disabled={!draft.trim()} data-testid="voice-send-text">
            将确认后的文字交给文本输入
          </button>
        </label>
      ) : null}
      {error ? <p className="voice-composer__error" role="alert">{error}</p> : null}
      <p className="voice-composer__tts" data-testid="voice-tts-state">
        语音播报：{capability.outputState === "READY" ? "已配置" : "未配置"}；文本不受影响。
      </p>
    </section>
  );
}
