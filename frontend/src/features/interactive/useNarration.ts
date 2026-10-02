import { useCallback, useEffect, useRef, useState } from "react";
import type { InteractivePrompt } from "./api";
import { chooseNarrationVoice, narrationVoiceGroup, narrationVoiceId, narrationVoiceLabel } from "./narrationVoices";
import { narrationVoiceStorageKey, useNarrationVoice } from "./useNarrationVoice";
import { acquireAudio, ownsAudio, releaseAudio } from "../voice/audioOwnership";
import { useAccount } from "../identity/AccountContext";

export type NarrationStatus = "idle" | "loading" | "speaking" | "paused" | "ended" | "unavailable" | "error";
export type NarrationSnapshot = { status: NarrationStatus; prompt_id: string | null; subtitle: string };

/** State follows actual playback events; cancellation settles pending requests. */
export function useNarration(audioUrl: (prompt: InteractivePrompt) => string, voiceStorageKey?: string) {
  const [snapshot, setSnapshot] = useState<NarrationSnapshot>({ status: "idle", prompt_id: null, subtitle: "" });
  const account = useAccount();
  const storageKey = voiceStorageKey ?? (account ? narrationVoiceStorageKey(account.user.id) : "k12:interactive:voice:v1");
  const outputEnabled = !account || ["OUTPUT_ONLY", "INPUT_AND_OUTPUT"].includes(account.preferences?.voice_preference ?? "DISABLED");
  const owner = useRef(Symbol("narration"));
  const [notice, setNotice] = useState("");
  const [muted, setMuted] = useState(false);
  const { voices, setVoices, voiceId, selectVoice, rate, setRate } = useNarrationVoice(storageKey);
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
    if (ownsAudio(owner.current)) window.dispatchEvent(new CustomEvent("companion:narration", {
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
    if (ownsAudio(owner.current)) window.speechSynthesis?.cancel();
    utterance.current = null;
    change("idle");
    releaseAudio(owner.current);
  }, [change]);

  useEffect(() => { stop(); current.current = null; setNotice(""); return stop; }, [storageKey, account?.user.id, outputEnabled, stop]);

  useEffect(() => {
    const onHidden = () => { if (document.hidden) stop(); };
    document.addEventListener("visibilitychange", onHidden);
    window.addEventListener("pagehide", stop);
    window.addEventListener("identity:signed-out", stop);
    return () => {
      document.removeEventListener("visibilitychange", onHidden);
      window.removeEventListener("pagehide", stop);
      window.removeEventListener("identity:signed-out", stop);
      stop();
    };
  }, [stop]);

  const play = useCallback(async (prompt: InteractivePrompt, options?: { automatic?: boolean }): Promise<boolean> => {
    if (options?.automatic && !acquireAudio(owner.current, stop, true)) {
      setNotice("当前正在播放或录音，未自动朗读；可稍后手动朗读。");
      return false;
    }
    stop();
    setNotice("");
    if (!outputEnabled) { setNotice("语音输出已关闭，可在账号设置中开启。"); change("unavailable", prompt); return false; }
    acquireAudio(owner.current, stop);
    current.current = prompt;
    if (muted) { change("idle", prompt); releaseAudio(owner.current); return false; }
    const token = generation.current;
    const valid = () => token === generation.current && ownsAudio(owner.current);
    const settle = (status: NarrationStatus) => {
      if (!valid()) return;
      change(status, prompt);
      generation.current += 1;
      releaseAudio(owner.current);
    };
    change("loading", prompt);
    if (prompt.audio) {
      const element = new Audio(audioUrlRef.current(prompt));
      audio.current = element;
      element.playbackRate = rate;
      element.onplaying = () => { if (valid()) change("speaking", prompt); };
      element.onpause = () => { if (valid() && !element.ended) change("paused", prompt); };
      element.onended = () => { if (valid()) settle("ended"); };
      element.onerror = () => { if (valid()) settle("error"); };
      try { await element.play(); return valid(); }
      catch { if (valid()) settle("error"); return false; }
    }
    const synthesis = window.speechSynthesis;
    if (!synthesis || !("SpeechSynthesisUtterance" in window)) {
      settle("unavailable"); return false;
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
      if (!valid()) return false;
      voices = synthesis.getVoices();
    }
    setVoices([...voices]);
    const {voice} = chooseNarrationVoice(voices, voiceId);
    if (!voice) { settle("unavailable"); return false; }
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
        if (valid()) { settle("error"); synthesis.cancel(); }
        finish(false);
      }, 5000);
      pending.current = cancelPending;
      speech.onstart = () => {
        if (valid()) { change("speaking", prompt); finish(true); }
        else finish(false);
      };
      speech.onpause = () => { if (valid()) change("paused", prompt); };
      speech.onresume = () => { if (valid()) change("speaking", prompt); };
      speech.onend = () => { if (valid()) settle("ended"); finish(false); };
      speech.onerror = () => { if (valid()) settle("error"); finish(false); };
      utterance.current = speech;
      try { if (synthesis.paused) synthesis.resume(); synthesis.speak(speech); }
      catch { if (valid()) settle("error"); finish(false); }
    });
  }, [change, muted, rate, stop, voiceId, outputEnabled]);

  const pause = useCallback(() => {
    if (!ownsAudio(owner.current)) return;
    if (audio.current) audio.current.pause();
    else if (utterance.current && ownsAudio(owner.current)) {
      // Some browser voices never emit pause/resume events or cannot resume.
      // Cancel this utterance and retain its prompt for a fresh playback.
      generation.current += 1;
      pending.current?.();
      pending.current = null;
      utterance.current = null;
      if (ownsAudio(owner.current)) window.speechSynthesis?.cancel();
      change("paused", current.current);
    }
  }, [change]);
  const resume = useCallback(() => {
    if (!ownsAudio(owner.current)) return;
    if (audio.current) {
      const element = audio.current, token = generation.current;
      void element.play().catch(() => { if (token === generation.current && audio.current === element) { change("error", current.current); generation.current += 1; releaseAudio(owner.current); } });
    }
    else if (current.current && snapshot.status === "paused") void play(current.current);
  }, [change, play, snapshot.status]);
  const replay = useCallback(() => current.current ? play(current.current) : Promise.resolve(false), [play]);
  const choice = chooseNarrationVoice(voices, voiceId);
  const voiceDescription = choice.voice ? narrationVoiceLabel(choice.voice) : "暂无可用声音";
  const voiceNotice = choice.missingSelection
    ? choice.voice ? `所选声音当前不可用，暂用普通话（${choice.voice.lang}）。` : "所选声音当前不可用，也没有可用的普通话声音，请选择其他声音或阅读讲解。"
    : !choice.voice ? snapshot.status === 'loading' ? "正在读取浏览器声音…" : "当前设备没有可用的普通话声音，请选择其他声音或阅读讲解。" : voiceId ? `当前声音：${narrationVoiceGroup(choice.voice)}（${choice.voice.lang}）` : `自动普通话（${choice.voice.lang}）`;
  const voiceOptions = voices.map(voice => ({id: narrationVoiceId(voice), label: narrationVoiceLabel(voice), group: narrationVoiceGroup(voice)}));
  return { ...snapshot, notice, outputEnabled, rate, setRate, muted, setMuted, voiceId, selectVoice, voiceOptions, voiceNotice, voiceDescription, play, pause, resume, stop, replay };
}
