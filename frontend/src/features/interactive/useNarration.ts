import { useCallback, useEffect, useRef, useState } from "react";
import type { InteractivePrompt } from "./api";

export type NarrationStatus = "idle" | "loading" | "speaking" | "paused" | "unavailable" | "error";

/** Audio and speech synthesis are both controlled by actual playback events. */
export function useNarration(audioUrl: (prompt: InteractivePrompt) => string) {
  const [status, setStatus] = useState<NarrationStatus>("idle");
  const [subtitle, setSubtitle] = useState("");
  const [rate, setRate] = useState(1);
  const [muted, setMuted] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);
  const utterance = useRef<SpeechSynthesisUtterance | null>(null);
  const current = useRef<InteractivePrompt | null>(null);
  const generation = useRef(0);

  const change = useCallback((next: NarrationStatus, text = "") => {
    setStatus(next);
    setSubtitle(text);
    window.dispatchEvent(new CustomEvent("companion:narration", {
      detail: { speaking: next === "speaking", subtitle: next === "speaking" || next === "paused" ? text : "" },
    }));
  }, []);

  const stop = useCallback(() => {
    generation.current += 1;
    if (audio.current) {
      audio.current.pause();
      audio.current.src = "";
      audio.current = null;
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
    utterance.current = null;
    change("idle");
  }, [change]);

  useEffect(() => {
    const onHidden = () => { if (document.hidden) stop(); };
    const onSignOut = () => stop();
    document.addEventListener("visibilitychange", onHidden);
    window.addEventListener("identity:signed-out", onSignOut);
    return () => {
      document.removeEventListener("visibilitychange", onHidden);
      window.removeEventListener("identity:signed-out", onSignOut);
      stop();
    };
  }, [stop]);

  const play = useCallback(async (prompt: InteractivePrompt): Promise<boolean> => {
    stop();
    current.current = prompt;
    if (muted) { change("idle", prompt.text); return false; }
    const token = generation.current;
    change("loading", prompt.text);
    if (prompt.audio) {
      const element = new Audio(audioUrl(prompt));
      audio.current = element;
      element.playbackRate = rate;
      element.onplay = () => { if (token === generation.current) change("speaking", prompt.text); };
      element.onpause = () => { if (token === generation.current && !element.ended) change("paused", prompt.text); };
      element.onended = () => { if (token === generation.current) change("idle"); };
      element.onerror = () => { if (token === generation.current) change("error", prompt.text); };
      try { await element.play(); return true; }
      catch { if (token === generation.current) change("error", prompt.text); return false; }
    }
    if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) {
      change("unavailable", prompt.text); return false;
    }
    const voices = window.speechSynthesis.getVoices();
    const voice = voices.find((item) => item.lang.toLowerCase().startsWith("zh"));
    if (!voice) { change("unavailable", prompt.text); return false; }
    const speech = new SpeechSynthesisUtterance(prompt.text);
    speech.voice = voice;
    speech.lang = voice.lang;
    speech.rate = rate;
    return new Promise<boolean>((resolve) => {
      let settled = false;
      const finish = (accepted: boolean) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(startTimeout);
        resolve(accepted);
      };
      // This checks whether speech actually started; it never simulates its end.
      const startTimeout = window.setTimeout(() => {
        if (token === generation.current) { window.speechSynthesis.cancel(); change("error", prompt.text); }
        finish(false);
      }, 5000);
      speech.onstart = () => {
        if (token === generation.current) { change("speaking", prompt.text); finish(true); }
        else finish(false);
      };
      speech.onpause = () => { if (token === generation.current) change("paused", prompt.text); };
      speech.onresume = () => { if (token === generation.current) change("speaking", prompt.text); };
      speech.onend = () => { if (token === generation.current) change("idle"); finish(false); };
      speech.onerror = () => { if (token === generation.current) change("error", prompt.text); finish(false); };
      utterance.current = speech;
      try { window.speechSynthesis.speak(speech); }
      catch { if (token === generation.current) change("error", prompt.text); finish(false); }
    });
  }, [audioUrl, change, muted, rate, stop]);

  const pause = useCallback(() => {
    if (audio.current) audio.current.pause();
    else if (utterance.current) window.speechSynthesis.pause();
  }, []);
  const resume = useCallback(() => {
    if (audio.current) void audio.current.play();
    else if (utterance.current) window.speechSynthesis.resume();
  }, []);
  const replay = useCallback(() => current.current ? play(current.current) : Promise.resolve(false), [play]);
  return { status, subtitle, rate, setRate, muted, setMuted, play, pause, resume, stop, replay };
}
