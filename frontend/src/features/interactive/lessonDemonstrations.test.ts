import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
// @ts-expect-error The existing jsdom test dependency does not bundle declarations.
import { JSDOM } from 'jsdom';
import { describe, expect, it, vi } from 'vitest';

const read = (path: string) => readFileSync(resolve(process.cwd(), '../curriculum/interactive/computing-ai-v1', path), 'utf8');
describe('authored HTML demonstrations', () => {
  for (const folder of ['ai-picture', 'binary-cards']) it(`${folder}: renders all cues and restores manual work without saving demonstration actions`, async () => {
    const manifest = JSON.parse(read(`${folder}/manifest.json`));
    const dom = new JSDOM(read(`${folder}/index.html`), {runScripts: 'outside-only'});
    const win = dom.window;
    const gameState = folder === 'ai-picture' ? {red: true} : {bits: [true, false, false, false, false], target: 16};
    const save = vi.fn(async () => ({}));
    let handle!: (command: Record<string, unknown>) => Promise<void>;
    let steps: Array<{scene_id: string; prompt_id: string}> = [];
    const register = vi.fn(async (_commands, handler, options) => { handle = handler; steps = options.playback_steps; return {embedded: true}; });
    Object.assign(win, {LESSON_SCENES: manifest.scenes, K12: {
      ready: async () => ({gameState, currentScene: manifest.scenes[0].id, prompts: manifest.prompts}),
      workspace: {register, onSession() {}, report: async () => ({})},
      scene: {enter: async () => ({})}, checkpoint: {save},
      narration: {onState() {}},
    }});
    win.eval(read('shared/bootstrap.js'));
    win.eval(read(`${folder}/activity.js`));
    await vi.waitFor(() => expect(register).toHaveBeenCalledOnce());
    const before = win.document.querySelector('.result')!.textContent;
    expect(steps).toHaveLength(4);
    for (const step of steps) {
      await handle({command: 'scene', scene_id: step.scene_id});
      await handle({command: 'demonstrate', prompt_id: step.prompt_id});
      expect(win.document.body.classList.contains('demonstrating')).toBe(true);
      expect(win.document.querySelector('#visual')!.inert).toBe(true);
      if (folder === 'ai-picture' && step.scene_id === 'examples') expect(win.document.querySelector('.result')!.textContent).toBe('红苹果和黄香蕉 → 已加入样例');
    }
    expect(win.document.querySelector('.result')!.textContent).toContain(folder === 'ai-picture' ? '绿色苹果 → 苹果' : '11111₂ = 31₁₀');
    expect(save).not.toHaveBeenCalled();
    await handle({command: 'demonstrate', prompt_id: null});
    expect(win.document.body.classList.contains('demonstrating')).toBe(false);
    expect(win.document.querySelector('.result')!.textContent).toBe(before);
    expect(win.document.querySelector('#visual')!.inert).toBe(false);
    dom.window.close();
  });
});
