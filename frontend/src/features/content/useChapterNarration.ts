import { useCallback, useEffect, useRef, useState } from "react";
import { useNarration } from "../interactive/useNarration";
import type { InteractivePrompt } from "../interactive/api";
import type { ReadingSegment } from "./chapterNarration";
import { narrationVoiceStorageKey } from "../interactive/useNarrationVoice";

type QueuedSegment = ReadingSegment & { prompt: InteractivePrompt };

export function useChapterNarration(chapterKey: string, userId?: string) {
  const narrator = useNarration(() => "", narrationVoiceStorageKey(userId));
  const [queue, setQueue] = useState<QueuedSegment[]>([]);
  const [position, setPosition] = useState(0);
  const [scope, setScope] = useState<"chapter" | "selection">("chapter");
  const [message, setMessage] = useState("");
  const sequence = useRef(0);
  const { play, stop: stopNarration, status, prompt_id } = narrator;

  const stop = useCallback(() => {
    stopNarration();
    setQueue([]);
    setPosition(0);
    setMessage("");
  }, [stopNarration]);

  useEffect(() => () => stop(), [chapterKey, stop]);

  const start = useCallback((segments: ReadingSegment[], nextScope: "chapter" | "selection" = "chapter") => {
    stop();
    const request = ++sequence.current;
    const next = segments.filter((segment) => segment.text.trim()).map((segment, index) => ({
      ...segment,
      prompt: { id: `reader-${request}-${index}`, scene_id: "chapter", text: segment.text, trigger: "MANUAL" as const, audio: null },
    }));
    if (!next.length) {
      setMessage("正文仍在排版或没有可朗读的文字，请稍后重试。");
      return;
    }
    setScope(nextScope);
    setQueue(next);
    void play(next[0].prompt);
  }, [play, stop]);

  useEffect(() => {
    if (status !== "ended" || prompt_id !== queue[position]?.prompt.id) return;
    const next = queue[position + 1];
    if (!next) return;
    setPosition(position + 1);
    void play(next.prompt);
  }, [status, prompt_id, queue, position, play]);

  const active = status === "speaking" || status === "paused" || status === "loading";
  return {
    ...narrator, stop, start, scope, message,
    segment: queue[position], position, total: queue.length,
    activeBlockId: active ? queue[position]?.blockId ?? null : null,
    activeRange: active ? queue[position]?.range ?? null : null,
    active,
  };
}
