import { useCallback, useEffect, useState } from "react";

export const narrationVoiceStorageKey = (userId?: string) => `k12:interactive:voice:${userId}:v1`;
const preferenceEvent = "narration:voice-preference";

function readVoice(key: string) {
  try { return localStorage.getItem(key) ?? ""; } catch { return ""; }
}

/** Browser voices are device-specific; share the choice across reading and settings. */
export function useNarrationVoice(storageKey: string) {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [voiceId, setVoiceId] = useState(() => readVoice(storageKey));
  useEffect(() => {
    setVoiceId(readVoice(storageKey));
    const localChange = (event: Event) => {
      const detail = (event as CustomEvent<{ key: string; id: string }>).detail;
      if (detail?.key === storageKey) setVoiceId(detail.id);
    };
    const storedChange = (event: StorageEvent) => {
      if (event.key === storageKey || event.key === null) setVoiceId(readVoice(storageKey));
    };
    window.addEventListener(preferenceEvent, localChange);
    window.addEventListener("storage", storedChange);
    return () => {
      window.removeEventListener(preferenceEvent, localChange);
      window.removeEventListener("storage", storedChange);
    };
  }, [storageKey]);
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
  return { voices, setVoices, voiceId, selectVoice };
}
