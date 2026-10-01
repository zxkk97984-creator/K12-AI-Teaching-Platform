import {describe, expect, it, vi} from 'vitest';
import {ActivitySaveQueue} from './ActivitySaveQueue';
import type {InteractiveSession} from './api';
import {saveInteractive} from './api';
vi.mock('./api', () => ({saveInteractive: vi.fn(), completeInteractive: vi.fn()}));
const initial = {id: 'session', base_revision: 0, current_scene_id: 'first'} as InteractiveSession;

describe('checkpoint retry queue', () => {
  it('reuses a lost receipt request, then writes the latest experiment in order', async () => {
    let session = initial;
    const statuses: string[] = [];
    const queue = new ActivitySaveQueue({session: () => session, saved: value => {session = value;}, status: value => statuses.push(value)});
    const save = vi.mocked(saveInteractive); save.mockReset();
    save.mockRejectedValueOnce(new Error('connection lost'));
    save.mockImplementation(async (_id, body) => ({...session, base_revision: body.base_revision + 1, game_state: body.game_state ?? {}}));
    await expect(queue.enqueue({game_state: {step: 1}})).rejects.toThrow('connection lost');
    expect(queue.dirty).toBe(true);
    await queue.enqueue({game_state: {step: 2}});
    expect(save.mock.calls[0][1]).toEqual(save.mock.calls[1][1]);
    expect(save.mock.calls[2][1].base_revision).toBe(1);
    expect(session.game_state).toEqual({step: 2});
    expect(queue.dirty).toBe(false);
    expect(statuses).toContain('unsaved');
    expect(statuses.at(-1)).toBe('saved');
  });
  it('ignores a late write receipt after leaving the activity', async () => {
    let resolve!: (value: InteractiveSession) => void;
    vi.mocked(saveInteractive).mockReset().mockImplementation(() => new Promise(done => {resolve = done;}));
    const saved = vi.fn();
    const queue = new ActivitySaveQueue({session: () => initial, saved, status: vi.fn()});
    const pending = queue.enqueue({game_state: {step: 1}});
    queue.reset(); resolve({...initial, base_revision: 1});
    expect(await pending).toBeNull();
    expect(saved).not.toHaveBeenCalled();
    expect(queue.dirty).toBe(false);
  });
});
