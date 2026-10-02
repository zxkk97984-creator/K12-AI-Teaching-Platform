import { useCallback, useEffect, useRef, useState } from "react";
import { acquireAudio, releaseAudio } from "./audioOwnership";

type Result = { isFinal: boolean; 0: { transcript: string } };
export type Recognition = {
  lang: string; continuous: boolean; interimResults: boolean;
  onresult: ((event: { resultIndex: number; results: ArrayLike<Result> }) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void; stop: () => void; abort: () => void;
};
function constructor() {
  const browser = window as Window & { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return browser.SpeechRecognition ?? browser.webkitSpeechRecognition;
}
const errors: Record<string, string> = {
  "not-allowed": "麦克风权限被拒绝，请在浏览器中允许麦克风后重试。",
  "service-not-allowed": "浏览器不允许语音识别，请检查权限。",
  "audio-capture": "没有可用的麦克风，请检查设备。",
  "no-speech": "没有识别到语音，请重试或直接输入文字。",
  network: "语音识别网络错误，请重试或直接输入文字。",
  aborted: "语音输入已取消。",
};

/** Final results only; every callback belongs to one account/conversation capture. */
export function useSpeechInput({ scopeKey, draft, onDraft, enabled = true, disabled = false }: {
  scopeKey: string; draft: string; onDraft: (text: string) => void; enabled?: boolean; disabled?: boolean;
}) {
  const [status, setStatus] = useState<"idle" | "listening" | "stopping" | "error">("idle");
  const [notice, setNotice] = useState("");
  const owner = useRef(Symbol("microphone"));
  const capture = useRef<Recognition | null>(null);
  const generation = useRef(0);
  const latest = useRef({ scopeKey, draft, onDraft, enabled, disabled });
  latest.current = { scopeKey, draft, onDraft, enabled, disabled };
  const cancel = useCallback(() => {
    generation.current += 1;
    const previous = capture.current;
    capture.current = null;
    if (previous) { previous.onresult = null; previous.onend = null; previous.onerror = null; try { previous.abort(); } catch { /* browser already ended capture */ } }
    releaseAudio(owner.current);
    setStatus("idle");
  }, []);
  useEffect(() => { cancel(); setNotice(""); return cancel; }, [scopeKey, enabled, disabled, cancel]);
  useEffect(() => {
    const hidden = () => { if (document.hidden) cancel(); };
    window.addEventListener("identity:signed-out", cancel);
    window.addEventListener("pagehide", cancel);
    document.addEventListener("visibilitychange", hidden);
    return () => { window.removeEventListener("identity:signed-out", cancel); window.removeEventListener("pagehide", cancel); document.removeEventListener("visibilitychange", hidden); };
  }, [cancel]);
  const toggle = () => {
    if (capture.current) {
      setStatus("stopping");
      try { capture.current.stop(); } catch { cancel(); setNotice("无法结束语音识别，已取消；可继续输入文字。"); }
      return;
    }
    const Constructor = constructor();
    if (!Constructor || !enabled || disabled) return;
    cancel();
    acquireAudio(owner.current, cancel);
    const token = generation.current;
    const scope = scopeKey;
    const valid = () => token === generation.current && latest.current.scopeKey === scope && latest.current.enabled && !latest.current.disabled;
    let instance: Recognition;
    try { instance = new Constructor(); } catch { cancel(); setStatus("error"); setNotice("无法开始语音识别，请重试或直接输入文字。"); return; }
    instance.lang = "zh-CN";
    instance.continuous = false;
    instance.interimResults = false;
    const seen = new Set<number>();
    let received = false;
    let failed = false;
    instance.onresult = (event) => {
      if (!valid()) return;
      const pieces: string[] = [];
      for (let index = event.resultIndex ?? 0; index < event.results.length; index += 1) {
        const result = event.results[index];
        if (!result?.isFinal || seen.has(index)) continue;
        seen.add(index);
        const text = result[0]?.transcript.trim();
        if (text) pieces.push(text);
      }
      if (!pieces.length) return;
      received = true;
      // Read the latest draft, including edits made while the microphone was open.
      const existing = latest.current.draft;
      const text = `${existing}${existing && !/\s$/.test(existing) ? " " : ""}${pieces.join(" ")}`.slice(0, 8000);
      latest.current.draft = text;
      latest.current.onDraft(text);
      setNotice("识别文字已放入输入框，可修改后手动发送。");
    };
    instance.onerror = (event) => {
      if (!valid()) return;
      failed = true;
      setNotice(errors[event.error ?? ""] ?? "语音识别失败，请重试或直接输入文字。");
      setStatus("error");
      generation.current += 1;
      capture.current = null;
      releaseAudio(owner.current);
      try { instance.abort(); } catch { /* recognition already ended */ }
    };
    instance.onend = () => {
      if (!valid()) return;
      generation.current += 1;
      capture.current = null;
      releaseAudio(owner.current);
      setStatus("idle");
      if (!received && !failed) setNotice(errors["no-speech"]);
    };
    capture.current = instance;
    setNotice("");
    setStatus("listening");
    try { instance.start(); } catch { cancel(); setStatus("error"); setNotice("无法开始语音识别，请重试或直接输入文字。"); }
  };
  return { status, notice, supported: Boolean(constructor()), toggle, cancel };
}
