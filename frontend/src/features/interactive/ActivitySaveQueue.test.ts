import {describe, expect, it, vi} from 'vitest';
import {ActivitySaveQueue} from './ActivitySaveQueue';
import type {InteractiveSession} from './api';
import {saveInteractive, viewedInteractive} from './api';
vi.mock('./api', () => ({saveInteractive: vi.fn(), completeInteractive: vi.fn(), viewedInteractive: vi.fn()}));
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

describe('viewing and stale receipts', () => {
  it('retries the same viewing event then saves an experiment without completion', async () => {
    let session = initial;
    vi.mocked(viewedInteractive).mockReset().mockRejectedValueOnce(new Error('offline')).mockImplementation(async () => ({...session, base_revision: session.base_revision+1, viewed_at: '2026-10-02T06:00:00Z'}));
    vi.mocked(saveInteractive).mockReset().mockImplementation(async (_id, body) => ({...session, base_revision: body.base_revision+1, game_state: body.game_state ?? {}}));
    const queue = new ActivitySaveQueue({session: () => session, saved: s => {session=s;}, status: vi.fn()});
    await expect(queue.enqueue({viewed: true})).rejects.toThrow('offline');
    await queue.enqueue({game_state: {experiment: 2}});
    expect(viewedInteractive).toHaveBeenCalledTimes(2);
    expect(vi.mocked(viewedInteractive).mock.calls[0]).toEqual(vi.mocked(viewedInteractive).mock.calls[1]);
    expect(session.viewed_at).toBeTruthy(); expect(session.game_state).toEqual({experiment: 2});
  });
  it('does not apply an older idempotency receipt over a newer local revision', async () => {
    let session = {...initial, base_revision: 4};
    vi.mocked(saveInteractive).mockReset().mockResolvedValue({...initial, base_revision: 2, game_state: {old: true}});
    const apply = vi.fn();
    const queue = new ActivitySaveQueue({session: () => session, saved: apply, status: vi.fn()});
    const pending = queue.enqueue({game_state: {new: true}});
    session = {...session, base_revision: 5};
    expect((await pending)?.base_revision).toBe(5); expect(apply).not.toHaveBeenCalled();
  });
  it('retains a conflict and never replaces the unconfirmed display with remote data', async () => {
    vi.mocked(saveInteractive).mockReset().mockRejectedValue(new Error('活动已更新，请读取最新记录'));
    const apply = vi.fn();
    const queue = new ActivitySaveQueue({session: () => initial, saved: apply, status: vi.fn()});
    await expect(queue.enqueue({game_state: {local: 7}})).rejects.toThrow('活动已更新');
    expect(queue.dirty).toBe(true); expect(apply).not.toHaveBeenCalled();
  });
});
