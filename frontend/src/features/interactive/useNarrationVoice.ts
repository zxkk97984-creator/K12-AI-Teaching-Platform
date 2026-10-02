import { useCallback, useEffect, useState } from "react";

export const narrationVoiceStorageKey = (userId?: string) => `k12:interactive:voice:${userId}:v1`;
const preferenceEvent = "narration:voice-preference";
function readRate(key: string) { const value = Number(readVoice(key)); return [0.8, 1, 1.2, 1.5].includes(value) ? value : 1; }

function readVoice(key: string) {
  try { return localStorage.getItem(key) ?? ""; } catch { return ""; }
}

/** Browser voices are device-specific; share the choice across reading and settings. */
export function useNarrationVoice(storageKey: string) {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [selection, setSelection] = useState(() => ({ key: storageKey, id: readVoice(storageKey) }));
  const voiceId = selection.key === storageKey ? selection.id : readVoice(storageKey);
  const rateKey = `${storageKey}:rate`;
  const [speed, setSpeed] = useState(() => ({ key: rateKey, value: readRate(rateKey) }));
  const rate = speed.key === rateKey ? speed.value : readRate(rateKey);
  const setVoiceId = (id: string) => setSelection({ key: storageKey, id });
  const setRate = useCallback((value: number) => {
    const safe = [0.8, 1, 1.2, 1.5].includes(value) ? value : 1;
    try { localStorage.setItem(rateKey, String(safe)); } catch { /* session-only */ }
    setSpeed({ key: rateKey, value: safe });
    window.dispatchEvent(new CustomEvent(preferenceEvent, { detail: { key: rateKey, id: String(safe) } }));
  }, [rateKey]);
  useEffect(() => {
    setVoiceId(readVoice(storageKey));
    setSpeed({ key: rateKey, value: readRate(rateKey) });
    const localChange = (event: Event) => {
      const detail = (event as CustomEvent<{ key: string; id: string }>).detail;
      if (detail?.key === storageKey) setVoiceId(detail.id);
      if (detail?.key === rateKey) setSpeed({ key: rateKey, value: [0.8, 1, 1.2, 1.5].includes(Number(detail.id)) ? Number(detail.id) : 1 });
    };
    const storedChange = (event: StorageEvent) => {
      if (event.key === storageKey || event.key === null) setVoiceId(readVoice(storageKey));
      if (event.key === rateKey || event.key === null) setSpeed({ key: rateKey, value: readRate(rateKey) });
    };
    window.addEventListener(preferenceEvent, localChange);
    window.addEventListener("storage", storedChange);
    return () => {
      window.removeEventListener(preferenceEvent, localChange);
      window.removeEventListener("storage", storedChange);
    };
  }, [storageKey, rateKey]);
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
    try { if (id) localStorage.setItem(storageKey, id); else localStorage.removeItem(storageKey); } catch { /* session-only preference */ }
    window.dispatchEvent(new CustomEvent(preferenceEvent, { detail: { key: storageKey, id } }));
  }, [storageKey]);
  return { voices, setVoices, voiceId, selectVoice, rate, setRate };
}
