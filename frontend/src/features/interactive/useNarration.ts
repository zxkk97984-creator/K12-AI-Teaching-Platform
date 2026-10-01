import { useCallback, useEffect, useRef, useState } from "react";
import type { InteractivePrompt } from "./api";
import { chooseNarrationVoice, narrationVoiceGroup, narrationVoiceId, narrationVoiceLabel } from "./narrationVoices";

export type NarrationStatus = "idle" | "loading" | "speaking" | "paused" | "ended" | "unavailable" | "error";
export type NarrationSnapshot = { status: NarrationStatus; prompt_id: string | null; subtitle: string };

/** State follows actual playback events; cancellation settles pending requests. */
export function useNarration(audioUrl: (prompt: InteractivePrompt) => string, voiceStorageKey = "k12:interactive:voice:v1") {
  const [snapshot, setSnapshot] = useState<NarrationSnapshot>({ status: "idle", prompt_id: null, subtitle: "" });
  const [rate, setRate] = useState(1);
  const [muted, setMuted] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [voiceId, setVoiceId] = useState(() => { try { return localStorage.getItem(voiceStorageKey) ?? ""; } catch { return ""; } });
  useEffect(() => {
    try { setVoiceId(localStorage.getItem(voiceStorageKey) ?? ""); } catch { setVoiceId(""); }
  }, [voiceStorageKey]);
  useEffect(() => {
    const synthesis = window.speechSynthesis;
    if (!synthesis) return;
    const update = () => setVoices([...synthesis.getVoices()]);
    update();
    synthesis.addEventListener?.("voiceschanged", update);
    return () => synthesis.removeEventListener?.("voiceschanged", update);
  }, []);
  const selectVoice = useCallback((id: string) => {
    setVoiceId(id);
    try { if (id) localStorage.setItem(voiceStorageKey, id); else localStorage.removeItem(voiceStorageKey); } catch { /* session-only preference */ }
  }, [voiceStorageKey]);
  const audio = useRef<HTMLAudioElement | null>(null);
  const utterance = useRef<SpeechSynthesisUtterance | null>(null);
  const current = useRef<InteractivePrompt | null>(null);
  const generation = useRef(0);
  const pending = useRef<(() => void) | null>(null);
  const audioUrlRef = useRef(audioUrl);
  audioUrlRef.current = audioUrl;

  const change = useCallback((status: NarrationStatus, prompt: InteractivePrompt | null = null) => {
    const next = { status, prompt_id: prompt?.id ?? null, subtitle: prompt?.text ?? "" };
    setSnapshot(next);
    window.dispatchEvent(new CustomEvent("companion:narration", {
      detail: { ...next, speaking: status === "speaking" },
    }));
  }, []);

  const stop = useCallback(() => {
    generation.current += 1;
    pending.current?.();
    pending.current = null;
    if (audio.current) {
      audio.current.pause();
      audio.current.src = "";
      audio.current = null;
    }
    window.speechSynthesis?.cancel();
    utterance.current = null;
    change("idle");
  }, [change]);

  useEffect(() => {
    const onHidden = () => { if (document.hidden) stop(); };
    document.addEventListener("visibilitychange", onHidden);
    window.addEventListener("identity:signed-out", stop);
    return () => {
      document.removeEventListener("visibilitychange", onHidden);
      window.removeEventListener("identity:signed-out", stop);
      stop();
    };
  }, [stop]);

  const play = useCallback(async (prompt: InteractivePrompt): Promise<boolean> => {
    stop();
    current.current = prompt;
    if (muted) { change("idle", prompt); return false; }
    const token = generation.current;
    change("loading", prompt);
    if (prompt.audio) {
      const element = new Audio(audioUrlRef.current(prompt));
      audio.current = element;
      element.playbackRate = rate;
      element.onplaying = () => { if (token === generation.current) change("speaking", prompt); };
      element.onpause = () => { if (token === generation.current && !element.ended) change("paused", prompt); };
      element.onended = () => { if (token === generation.current) change("ended", prompt); };
      element.onerror = () => { if (token === generation.current) change("error", prompt); };
      try { await element.play(); return token === generation.current; }
      catch { if (token === generation.current) change("error", prompt); return false; }
    }
    const synthesis = window.speechSynthesis;
    if (!synthesis || !("SpeechSynthesisUtterance" in window)) {
      change("unavailable", prompt); return false;
    }
    let voices = synthesis.getVoices();
    if (voices.length === 0 && typeof synthesis.addEventListener === "function") {
      await new Promise<void>((resolve) => {
        const finish = () => {
          window.clearTimeout(timer);
          synthesis.removeEventListener("voiceschanged", finish);
          if (pending.current === finish) pending.current = null;
          resolve();
        };
        const timer = window.setTimeout(finish, 1500);
        pending.current = finish;
        synthesis.addEventListener("voiceschanged", finish);
      });
      if (token !== generation.current) return false;
      voices = synthesis.getVoices();
    }
    setVoices([...voices]);
    const {voice} = chooseNarrationVoice(voices, voiceId);
    if (!voice) { change("unavailable", prompt); return false; }
    const speech = new SpeechSynthesisUtterance(prompt.text);
    speech.voice = voice;
    speech.lang = voice.lang;
    speech.rate = rate;
    return new Promise<boolean>((resolve) => {
      let settled = false;
      const cancelPending = () => finish(false);
      const finish = (accepted: boolean) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(startTimeout);
        if (pending.current === cancelPending) pending.current = null;
        resolve(accepted);
      };
      const startTimeout = window.setTimeout(() => {
        if (token === generation.current) { synthesis.cancel(); change("error", prompt); }
        finish(false);
      }, 5000);
      pending.current = cancelPending;
      speech.onstart = () => {
        if (token === generation.current) { change("speaking", prompt); finish(true); }
        else finish(false);
      };
      speech.onpause = () => { if (token === generation.current) change("paused", prompt); };
      speech.onresume = () => { if (token === generation.current) change("speaking", prompt); };
      speech.onend = () => { if (token === generation.current) change("ended", prompt); finish(false); };
      speech.onerror = () => { if (token === generation.current) change("error", prompt); finish(false); };
      utterance.current = speech;
      try { synthesis.speak(speech); }
      catch { if (token === generation.current) change("error", prompt); finish(false); }
    });
  }, [change, muted, rate, stop, voiceId]);

  const pause = useCallback(() => {
    if (audio.current) audio.current.pause();
    else if (utterance.current) window.speechSynthesis?.pause();
  }, []);
  const resume = useCallback(() => {
    if (audio.current) {
      const element = audio.current, token = generation.current;
      void element.play().catch(() => { if (token === generation.current && audio.current === element) change("error", current.current); });
    }
    else if (utterance.current) window.speechSynthesis?.resume();
  }, [change]);
  const replay = useCallback(() => current.current ? play(current.current) : Promise.resolve(false), [play]);
  const choice = chooseNarrationVoice(voices, voiceId);
  const voiceDescription = choice.voice ? narrationVoiceLabel(choice.voice) : "暂无可用声音";
  const voiceNotice = choice.missingSelection
    ? choice.voice ? `所选声音当前不可用，暂用普通话（${choice.voice.lang}）。` : "所选声音当前不可用，也没有可用的普通话声音，请选择其他声音或阅读讲解。"
    : !choice.voice ? snapshot.status === 'loading' ? "正在读取浏览器声音…" : "当前设备没有可用的普通话声音，请选择其他声音或阅读讲解。" : voiceId ? `当前声音：${narrationVoiceGroup(choice.voice)}（${choice.voice.lang}）` : `自动普通话（${choice.voice.lang}）`;
  const voiceOptions = voices.map(voice => ({id: narrationVoiceId(voice), label: narrationVoiceLabel(voice), group: narrationVoiceGroup(voice)}));
  return { ...snapshot, rate, setRate, muted, setMuted, voiceId, selectVoice, voiceOptions, voiceNotice, voiceDescription, play, pause, resume, stop, replay };
}
