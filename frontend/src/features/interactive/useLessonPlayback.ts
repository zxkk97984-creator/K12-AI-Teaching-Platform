import { useCallback, useEffect, useRef, useState } from 'react';
import type { InteractivePrompt } from './api';
import type { PlaybackStep } from './bridge';
import type { useNarration } from './useNarration';

type Status = 'idle' | 'playing' | 'reading' | 'paused' | 'ended' | 'error';
type Options = {
  steps: PlaybackStep[];
  prompts: InteractivePrompt[];
  narrator: ReturnType<typeof useNarration>;
  present: (step: PlaybackStep, isCurrent: () => boolean) => Promise<void>;
};

/** Speech completion drives the timeline. Only silent playback uses a reading timer. */
export function useLessonPlayback(options: Options) {
  const latest = useRef(options);
  latest.current = options;
  const [status, setStatus] = useState<Status>('idle');
  const [index, setIndex] = useState(0);
  const [notice, setNotice] = useState('');
  const generation = useRef(0);
  const cursor = useRef(0);
  const running = useRef(false);
  const phase = useRef<'preparing' | 'narrating' | 'reading' | 'gap'>('preparing');
  const timer = useRef<number | null>(null);
  const runStep = useRef<(index: number, token: number) => Promise<void>>(async () => {});
  const clearTimer = useCallback(() => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  }, []);
  const advance = useCallback((token: number, delay = 650) => {
    if (!running.current || generation.current !== token || phase.current === 'gap') return;
    phase.current = 'gap';
    clearTimer();
    timer.current = window.setTimeout(() => {
      timer.current = null;
      if (!running.current || generation.current !== token) return;
      if (cursor.current + 1 >= latest.current.steps.length) {
        running.current = false;
        setStatus('ended');
      } else void runStep.current(cursor.current + 1, token);
    }, delay);
  }, [clearTimer]);
  const readSilently = useCallback((prompt: InteractivePrompt, token: number, message: string) => {
    if (!running.current || generation.current !== token || phase.current === 'reading' || phase.current === 'gap') return;
    phase.current = 'reading';
    setStatus('reading');
    setNotice(message);
    clearTimer();
    // Leave enough time for a child to read the whole caption; never cuts off speech.
    const duration = Math.max(3500, Array.from(prompt.text).length * 300 / latest.current.narrator.rate);
    timer.current = window.setTimeout(() => { timer.current = null; advance(token); }, duration);
  }, [advance, clearTimer]);
  runStep.current = async (next, token) => {
    const { steps, prompts, narrator, present } = latest.current;
    const step = steps[next];
    const prompt = prompts.find(item => item.id === step?.prompt_id && item.scene_id === step.scene_id);
    const isCurrent = () => running.current && generation.current === token;
    if (!step || !prompt || !isCurrent()) return;
    cursor.current = next; setIndex(next); setStatus('playing'); phase.current = 'preparing';
    try {
      await present(step, isCurrent);
      if (!isCurrent()) return;
      phase.current = 'narrating';
      if (narrator.muted) { readSilently(prompt, token, '已静音，按字幕阅读时间自动演示。'); return; }
      const accepted = await latest.current.narrator.play(prompt);
      if (isCurrent() && !accepted && phase.current === 'narrating') readSilently(prompt, token, '声音暂不可用，按字幕阅读时间自动演示；可选择声音后重播。');
    } catch (caught) {
      if (!isCurrent()) return;
      running.current = false; setStatus('error');
      setNotice(caught instanceof Error ? caught.message : '自动播放暂时无法继续，请重试。');
    }
  };
  const start = useCallback((from = 0) => {
    clearTimer(); generation.current += 1; running.current = true; setNotice('');
    latest.current.narrator.stop();
    void runStep.current(from, generation.current);
  }, [clearTimer]);
  const pause = useCallback(() => {
    if (!running.current) return;
    running.current = false; generation.current += 1; clearTimer();
    latest.current.narrator.pause(); setStatus('paused');
  }, [clearTimer]);
  const stop = useCallback(() => {
    running.current = false; generation.current += 1; clearTimer();
    latest.current.narrator.stop(); setStatus('idle'); setNotice('');
  }, [clearTimer]);
  const resume = useCallback(() => start(cursor.current), [start]);
  const replay = useCallback(() => start(cursor.current), [start]);
  useEffect(() => {
    if (!running.current || phase.current !== 'narrating') return;
    const { narrator, steps, prompts } = latest.current;
    const step = steps[cursor.current];
    const prompt = prompts.find(item => item.id === step?.prompt_id);
    if (!prompt) return;
    if (narrator.muted) readSilently(prompt, generation.current, '已静音，按字幕阅读时间自动演示。');
    else if (narrator.prompt_id === prompt.id) {
      if (narrator.status === 'ended') advance(generation.current);
      else if (narrator.status === 'unavailable' || narrator.status === 'error') readSilently(prompt, generation.current, '声音暂不可用，按字幕阅读时间自动演示；可选择声音后重播。');
    }
  }, [options.narrator.status, options.narrator.prompt_id, options.narrator.muted, advance, readSilently]);
  useEffect(() => {
    const hidden = () => { if (document.hidden) pause(); };
    document.addEventListener('visibilitychange', hidden);
    window.addEventListener('pagehide', pause);
    window.addEventListener('identity:signed-out', stop);
    return () => {
      document.removeEventListener('visibilitychange', hidden);
      window.removeEventListener('pagehide', pause);
      window.removeEventListener('identity:signed-out', stop);
      running.current = false; generation.current += 1; clearTimer();
    };
  }, [clearTimer, pause, stop]);
  return { status, index, notice, active: status !== 'idle', running: status === 'playing' || status === 'reading', isRunning: () => running.current, start, pause, resume, replay, stop };
}
