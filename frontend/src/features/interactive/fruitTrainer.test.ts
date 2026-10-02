import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
// @ts-expect-error The existing jsdom test dependency does not bundle declarations.
import { JSDOM } from 'jsdom';
import { afterEach, describe, expect, it, vi } from 'vitest';

const html = readFileSync(resolve(process.cwd(), '../curriculum/interactive/computing-ai-v1/ai-fruit-trainer/index.html'), 'utf8');
const opened: Array<{window: Window & {close(): void}}> = [];
function game(sdk?: object) {
  const dom = new JSDOM(html, {runScripts: 'outside-only'});
  opened.push(dom);
  if (sdk) dom.window.K12 = sdk;
  dom.window.eval(dom.window.document.querySelector('script').textContent);
  const doc = dom.window.document as Document;
  const click = (selector: string) => (doc.querySelector(selector) as HTMLButtonElement).click();
  const label = (id: string, value: string) => { click(`[data-card="${id}"]`); click(`[data-label="${value}"]`); };
  const text = (id: string) => doc.getElementById(id)!.textContent;
  return {dom, doc, click, label, text};
}
afterEach(() => {for (const dom of opened.splice(0)) dom.window.close();});
function mockHost(gameState: object = {}) {
  let handle!: (command: Record<string, string>) => Promise<void>;
  const save = vi.fn(async (_state: object) => ({persisted: true}));
  const complete = vi.fn(async (_result: object) => ({}));
  const enter = vi.fn(async (_scene: string) => ({}));
  const sdk = {
    ready: async () => ({gameState, currentScene: null, prompts: []}),
    workspace: {register: vi.fn(async (_commands, handler) => {handle = handler; return {embedded: true};}), report: vi.fn(async () => ({}))},
    checkpoint: {save}, scene: {enter}, complete,
    narration: {play: vi.fn(async () => ({}))}, askTeacher: vi.fn(async () => ({})),
  };
  return {sdk, save, complete, enter, command: (value: Record<string, string>) => handle(value)};
}
async function firstRound(g: ReturnType<typeof game>) {
  g.label('r1','apple');g.label('r2','apple');g.label('b1','banana');g.label('b2','banana');g.click('#test');
  expect(g.text('feedback')).toContain('挑战成功');g.click('#next');
  await vi.waitFor(() => expect(g.text('mission-title')).toBe('帮机器人见多识广'));
  await vi.waitFor(() => expect((g.doc.getElementById('test') as HTMLButtonElement).disabled).toBe(false));
}
describe('AI fruit trainer: the actual single-file game', () => {
  it('handles no examples, a missing class, and conflicting nearest labels', () => {
    const g = game();g.click('#test');expect(g.text('feedback')).toContain('还没有学习样例');
    g.label('r1','apple');g.click('#test');expect(g.text('feedback')).toContain('只见过一种标签');
    g.label('r2','banana');g.click('#test');expect(g.text('feedback')).toContain('一样像');
    expect(g.text('test-cards')).toContain('暂时不确定');
    expect((g.doc.getElementById('next') as HTMLButtonElement).disabled).toBe(true);
  });
  it('predicts from student labels rather than test answers, and supports keyboard labels', () => {
    const g = game();g.click('[data-card="r1"]');
    g.doc.dispatchEvent(new g.dom.window.KeyboardEvent('keydown', {key:'2', bubbles:true}));
    g.label('r2','banana');g.label('b1','apple');g.label('b2','apple');g.click('#test');
    expect(g.text('feedback')).toContain('0 / 2');expect(g.text('test-cards')).toContain('我猜：香蕉');
    g.label('r1','apple');g.label('r2','apple');g.label('b1','banana');g.label('b2','banana');g.click('#test');
    expect(g.text('feedback')).toContain('挑战成功');
  });
  it('finishes three challenges only after observing and repairing both errors', async () => {
    const g = game();await firstRound(g);
    g.click('#test');expect(g.text('test-cards')).toContain('再看看：其实是苹果');expect(g.text('feedback')).toContain('2 / 3');
    g.label('y1','apple');g.label('g1','apple');g.label('g2','banana');g.click('#test');
    expect(g.text('feedback')).toContain('从 2 / 3 到 3 / 3');g.click('#next');
    await vi.waitFor(() => expect(g.text('mission-title')).toContain('检查一下'));
    await vi.waitFor(() => expect((g.doc.getElementById('test') as HTMLButtonElement).disabled).toBe(false));
    g.click('#test');expect(g.text('feedback')).toContain('2 / 3');
    g.label('y1','apple');g.click('#test');expect(g.text('feedback')).toContain('标签改对了');g.click('#next');
    await vi.waitFor(() => expect(g.doc.getElementById('celebration')!.hidden).toBe(false));
    await vi.waitFor(() => expect((g.doc.getElementById('finish') as HTMLButtonElement).disabled).toBe(false));
    expect(g.text('finish-note')).toBe('点击领取徽章，确认完成。');g.click('#finish');
    await vi.waitFor(() => expect(g.text('finish-note')).toContain('本次挑战已完成'));
  });
  it('guides the learner to observe the initial mistake before editing examples', async () => {
    const g = game();await firstRound(g);
    expect((g.doc.querySelector('[data-card="y1"]') as HTMLButtonElement).disabled).toBe(true);
    expect(g.text('selection-text')).toContain('先让机器人猜一猜');
    g.click('#test');expect(g.text('feedback')).toContain('2 / 3');
    expect((g.doc.querySelector('[data-card="y1"]') as HTMLButtonElement).disabled).toBe(false);
    expect((g.doc.getElementById('next') as HTMLButtonElement).disabled).toBe(true);
  });
  it('serializes saves, keeps an unsaved operation, retries and restores its labels', async () => {
    const h = mockHost();const g = game(h.sdk);
    await vi.waitFor(() => expect(g.doc.body.classList.contains('embedded')).toBe(true));
    h.save.mockRejectedValueOnce(new Error('测试：保存失败'));
    g.label('r1','apple');
    await vi.waitFor(() => expect(g.text('error')).toContain('保存失败'));
    expect(g.text('training-cards')).toContain('标签：苹果');g.click('#retry-save');
    await vi.waitFor(() => expect(g.text('save-status')).toBe('游戏进度已保存'));
    const snapshot = h.save.mock.calls.at(-1)![0];const resumed = game(mockHost(snapshot).sdk);
    await vi.waitFor(() => expect(resumed.text('training-cards')).toContain('标签：苹果'));
    expect(resumed.text('sample-count')).toContain('1 / 4');
    await expect(h.command({command:'complete'})).rejects.toThrow('完成三个挑战');
    await expect(h.command({command:'scene',scene_id:'repair'})).rejects.toThrow('先完成前面的挑战');
    expect(h.complete).not.toHaveBeenCalled();
  });
  it('restores an observed error, preserves separate training/test cards and sends a bounded result', async () => {
    const h = mockHost();const g = game(h.sdk);
    await vi.waitFor(() => expect(g.doc.body.classList.contains('embedded')).toBe(true));
    await firstRound(g);g.click('#test');
    await vi.waitFor(() => expect(g.text('save-status')).toBe('游戏进度已保存'));
    const snapshot = h.save.mock.calls.at(-1)![0];const h2 = mockHost(snapshot);const resumed = game(h2.sdk);
    await vi.waitFor(() => expect(resumed.text('mission-title')).toBe('帮机器人见多识广'));
    expect(resumed.text('test-cards')).toContain('再看看：其实是苹果');
    resumed.label('y1','apple');resumed.label('g1','apple');resumed.label('g2','banana');resumed.click('#test');resumed.click('#next');
    await vi.waitFor(() => expect(resumed.text('mission-title')).toContain('检查一下'));
    await vi.waitFor(() => expect((resumed.doc.getElementById('test') as HTMLButtonElement).disabled).toBe(false));
    resumed.click('#test');resumed.label('y1','apple');resumed.click('#test');resumed.click('#next');
    await vi.waitFor(() => expect(resumed.doc.getElementById('celebration')!.hidden).toBe(false));
    await vi.waitFor(() => expect((resumed.doc.getElementById('finish') as HTMLButtonElement).disabled).toBe(false));
    expect(h2.complete).not.toHaveBeenCalled();resumed.click('#finish');
    await vi.waitFor(() => expect(h2.complete).toHaveBeenCalledOnce());
    expect(h2.complete.mock.calls[0][0]).toMatchObject({score:3,maxScore:3,badge:'AI 小训练员'});
    for (const [saved] of h2.save.mock.calls) expect(JSON.stringify(saved)).not.toContain('test-y');
  });
});
