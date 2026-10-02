import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {NarrationControls} from './LearningControls';
import type {useNarration} from './useNarration';
import type {InteractivePrompt} from './api';

afterEach(cleanup);
const prompt: InteractivePrompt = {id:'read',scene_id:'start',text:'先观察图卡。',trigger:'SCENE_ENTER'};
function setup(overrides: Partial<ReturnType<typeof useNarration>> = {}, audio?: string) {
  const narrator = {
    status:'unavailable',rate:1,muted:false,voiceId:'',voiceOptions:[],
    voiceNotice:'当前设备没有可用的普通话声音，请选择其他声音或阅读讲解。',voiceDescription:'暂无可用声音',
    pause:vi.fn(),resume:vi.fn(),stop:vi.fn(),setMuted:vi.fn(),setRate:vi.fn(),selectVoice:vi.fn(),
    ...overrides,
  } as unknown as ReturnType<typeof useNarration>;
  const play=vi.fn(),enable=vi.fn();
  render(<><button>画布外侧</button><NarrationControls narrator={narrator} prompt={{...prompt,...(audio?{audio}:{})}} enabled started enable={enable} play={play}>
    <details className="interactive-more"><summary>学习操作</summary><div>保存并退出</div></details>
  </NarrationControls></>);
  const settings=document.querySelector<HTMLDetailsElement>('.interactive-voice-settings')!;
  const toggle=settings.querySelector<HTMLElement>('summary')!;
  return {narrator,play,settings,toggle};
}
describe('compact narration controls', () => {
  it('starts folded without repeating voice warnings and keeps playback available', () => {
    const g=setup();expect(g.settings.open).toBe(false);
    expect(document.querySelector('.interactive-audio-status')!.textContent).toBe('没有可用的普通话声音，可阅读讲解');
    fireEvent.click(screen.getByRole('button',{name:'播放讲解'}));expect(g.play).toHaveBeenCalledWith(prompt);
    expect(g.narrator.pause).not.toHaveBeenCalled();
  });
  it('changes settings without restarting playback, then closes on Escape and restores focus', async () => {
    const g=setup({status:'speaking'});fireEvent.click(g.toggle);await waitFor(()=>expect(g.settings.open).toBe(true));
    fireEvent.change(screen.getByLabelText('朗读语速'),{target:{value:'0.8'}});expect(g.narrator.setRate).toHaveBeenCalledWith(0.8);
    expect(g.play).not.toHaveBeenCalled();expect(g.narrator.pause).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('静音'));expect(g.narrator.setMuted).toHaveBeenCalledWith(true);expect(g.narrator.stop).toHaveBeenCalledOnce();
    fireEvent.keyDown(document,{key:'Escape'});await waitFor(()=>expect(g.settings.open).toBe(false));expect(document.activeElement).toBe(g.toggle);
  });
  it('keeps only one menu open and closes the menus when the canvas takes focus', async () => {
    const g=setup();fireEvent.click(g.toggle);await waitFor(()=>expect(g.settings.open).toBe(true));
    const more=document.querySelector<HTMLDetailsElement>('.interactive-more')!;
    fireEvent.click(more.querySelector('summary')!);await waitFor(()=>expect(more.open).toBe(true));await waitFor(()=>expect(g.settings.open).toBe(false));
    fireEvent.focusIn(screen.getByRole('button',{name:'画布外侧'}));expect(more.open).toBe(false);
    fireEvent.click(g.toggle);await waitFor(()=>expect(g.settings.open).toBe(true));fireEvent.pointerDown(screen.getByRole('button',{name:'画布外侧'}));expect(g.settings.open).toBe(false);
  });
  it('retains recorded-audio restrictions and the selected-voice warning', async () => {
    const g=setup({},'audio/intro.wav');fireEvent.click(g.toggle);await waitFor(()=>expect(g.settings.open).toBe(true));
    expect((screen.getByLabelText('朗读声音') as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByLabelText('朗读声音') as HTMLSelectElement).value).toBe('recorded');
    expect(g.settings.textContent).toContain('本段使用课件音频');
    cleanup();setup({voiceNotice:'所选声音当前不可用，也没有可用的普通话声音，请选择其他声音或阅读讲解。'});
    expect(document.querySelector('.interactive-audio-status')!.textContent).toContain('所选声音当前不可用');
  });
});
