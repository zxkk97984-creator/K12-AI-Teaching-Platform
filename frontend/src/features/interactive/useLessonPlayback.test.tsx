import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { InteractivePrompt } from './api';
import type { useNarration } from './useNarration';
import { useLessonPlayback } from './useLessonPlayback';

const steps = [{scene_id: 'first', prompt_id: 'first-read'}, {scene_id: 'second', prompt_id: 'second-read'}];
const prompts: InteractivePrompt[] = steps.map(step => ({id: step.prompt_id, scene_id: step.scene_id, text: '一起观察画面中的变化。', trigger: 'SCENE_ENTER'}));
function setup(present = vi.fn(async () => {})) {
  let narrator = {status: 'idle', prompt_id: null, muted: false, rate: 1, play: vi.fn(async () => true), pause: vi.fn(), stop: vi.fn()} as unknown as ReturnType<typeof useNarration>;
  const hook = renderHook(() => useLessonPlayback({steps, prompts, narrator, present}));
  const update = (patch: Partial<typeof narrator>) => {
    narrator = {...narrator, ...patch};
    hook.rerender();
  };
  return {...hook, present, update, narrator};
}
beforeEach(() => vi.useFakeTimers());
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('automatic lesson playback', () => {
  it('holds the current picture for arbitrarily long speech and advances only after the matching end', async () => {
    const h = setup();
    await act(async () => h.result.current.start());
    act(() => h.update({status: 'speaking', prompt_id: 'first-read'}));
    await act(async () => vi.advanceTimersByTimeAsync(60000));
    expect(h.present).toHaveBeenCalledTimes(1);
    act(() => h.update({status: 'ended', prompt_id: 'stale-read'}));
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(h.result.current.index).toBe(0);
    act(() => h.update({status: 'ended', prompt_id: 'first-read'}));
    await act(async () => vi.advanceTimersByTimeAsync(650));
    expect(h.result.current.index).toBe(1);
    expect(h.narrator.play).toHaveBeenLastCalledWith(prompts[1]);
    act(() => h.update({status: 'ended', prompt_id: 'second-read'}));
    await act(async () => vi.advanceTimersByTimeAsync(650));
    expect(h.result.current.status).toBe('ended');
    expect(h.result.current.isRunning()).toBe(false);
  });
  it('cancels advancement when paused, and replays the current paragraph on resume', async () => {
    const h = setup();
    await act(async () => h.result.current.start());
    act(() => h.update({status: 'ended', prompt_id: 'first-read'}));
    act(() => h.result.current.pause());
    await act(async () => vi.advanceTimersByTimeAsync(10000));
    expect(h.result.current.status).toBe('paused');
    expect(h.present).toHaveBeenCalledTimes(1);
    act(() => h.update({status: 'idle'}));
    await act(async () => h.result.current.resume());
    expect(h.present).toHaveBeenCalledTimes(2);
    expect(h.result.current.index).toBe(0);
  });
  it('uses an explicit reading-time fallback for unavailable voices and for mute', async () => {
    const h = setup();
    vi.mocked(h.narrator.play).mockResolvedValue(false);
    await act(async () => h.result.current.start());
    expect(h.result.current.status).toBe('reading');
    expect(h.result.current.notice).toContain('声音暂不可用');
    await act(async () => vi.advanceTimersByTimeAsync(4150));
    expect(h.result.current.index).toBe(1);
    act(() => h.result.current.stop());
    act(() => h.update({muted: true}));
    vi.mocked(h.narrator.play).mockClear();
    await act(async () => h.result.current.start());
    expect(h.result.current.notice).toContain('已静音');
    expect(h.narrator.play).not.toHaveBeenCalled();
  });
  it('does not start speech after a pending scene change has been stopped or unmounted', async () => {
    let release!: () => void;
    const present = vi.fn(() => new Promise<void>(resolve => { release = resolve; }));
    const h = setup(present);
    await act(async () => h.result.current.start());
    act(() => h.result.current.stop());
    await act(async () => release());
    expect(h.narrator.play).not.toHaveBeenCalled();
    await act(async () => h.result.current.start());
    h.unmount();
    await act(async () => release());
    expect(h.narrator.play).not.toHaveBeenCalled();
  });
  it('pauses when the page is hidden and surfaces a failed scene/save command', async () => {
    const h = setup();
    await act(async () => h.result.current.start());
    const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    expect(h.result.current.status).toBe('paused');
    hidden.mockRestore();
    h.present.mockRejectedValueOnce(new Error('保存冲突，请重试'));
    await act(async () => h.result.current.resume());
    expect(h.result.current.status).toBe('error');
    expect(h.result.current.notice).toContain('保存冲突');
  });
});
