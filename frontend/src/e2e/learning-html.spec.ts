import {chromium, expect, test, type Page} from '@playwright/test';
import {mkdir, writeFile, mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

test.skip(process.env.HTML_LEARNING_E2E !== '1', 'Run scripts/test-learning-browser.sh against the isolated database');
const evidence = 'test-results/learning-content-browser';
const cases = [
  {stage: 'PRIMARY_LOWER', slug: 'primary-ai', key: 'ai-picture'},
  {stage: 'PRIMARY_UPPER', slug: 'primary-unplugged', key: 'binary-cards'},
  {stage: 'JUNIOR', slug: 'junior-python', key: 'conditions-loops'},
  {stage: 'SENIOR', slug: 'senior-algorithms', key: 'binary-search'},
];
async function saved(page: Page) { await expect(page.locator('.interactive-player-header .interactive-status')).toHaveText('已保存到账号'); await expect(page.locator('.interactive-player-header .interactive-status')).toBeInViewport(); }
async function enableVoice(page: Page) {
  const button = page.getByRole('button', {name: '开启朗读', exact: true});
  if (await button.isVisible()) await button.click();
}
async function checkGeometry(page: Page) {
  const host = await page.evaluate(() => ({overflow: document.documentElement.scrollWidth > innerWidth, scroll: document.scrollingElement!.scrollHeight > innerHeight + 1, height: document.querySelector('.interactive-stage')!.getBoundingClientRect().height}));
  expect(host.overflow).toBe(false); expect(host.scroll).toBe(false); expect(host.height).toBeGreaterThan(80);
  const frame = page.frames().find(frame => frame.parentFrame());
  expect(await frame!.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await expect.poll(() => page.getByTestId('companion-dock').evaluate(el => { const pet = el.getBoundingClientRect(); return pet.left >= 0 && pet.right <= innerWidth; })).toBe(true);
}
for (const item of cases) test(`${item.stage}: unified workspace, restore, teacher and responsive layout`, async ({page}) => {
  test.setTimeout(90000);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await mkdir(evidence, {recursive: true});
  await page.setViewportSize({width: 1366, height: 768});
  await page.goto('/login');
  await page.getByLabel('用户名', {exact: true}).fill('html.' + item.stage.toLowerCase());
  await page.getByLabel('密码', {exact: true}).fill('synthetic-html-pass-2026');
  await page.getByRole('button', {name: '登录并继续'}).click();
  await expect(page).toHaveURL(/\/workbench$/);
  const catalog = await (await page.request.get('/api/v1/interactive/resources')).json();
  const activity = catalog.items[0];
  const courses = await (await page.request.get('/api/v1/courses')).json();
  const course = courses.items.find((entry: {slug: string}) => entry.slug === item.slug);
  const chapter = course.chapters.find((entry: {revision_id: string}) => activity.chapter_revision_ids.includes(entry.revision_id));
  await page.goto(`/chapters/${chapter.chapter_id}`);
  await expect(page.locator('.chapter-markdown').first()).toBeVisible();
  const csrf = (await (await page.request.get('/api/v1/auth/csrf')).json()).csrf_token;
  await page.request.post('/api/v1/interactive/sessions', {data: {resource_id: activity.id, restart: true}, headers: {Origin: new URL(page.url()).origin, 'X-CSRF-Token': csrf}});
  await page.goto(`/interactive/${activity.id}?from=activities`);
  await expect(page.getByRole('button', {name: '开始学习', exact: true})).toBeVisible();
  await page.screenshot({path: `${evidence}/${item.key}-start.png`});
  await page.getByRole('button', {name: '开始学习', exact: true}).click();
  const frame = page.frameLocator('.interactive-stage iframe');
  await expect(frame.locator('body')).toHaveClass(/embedded/);
  await expect(frame.locator('body > header')).toBeHidden();
  await expect(frame.locator('#scenes')).toBeHidden();
  await expect(frame.getByRole('button', {name: '朗读当前台词'})).toBeHidden();
  if (item.key === 'ai-picture') {
    for (const name of ['红苹果 · 苹果', '黄香蕉 · 香蕉', '绿苹果 · 苹果']) await frame.getByRole('button', {name: new RegExp(name)}).click();
    await expect(frame.locator('#prediction')).toHaveText('绿色苹果 → 苹果');
  } else if (item.key === 'binary-cards') {
    for (const weight of [8, 4, 1]) await frame.getByRole('button', {name: `${weight}卡片，关`, exact: true}).click();
    await expect(frame.locator('.result')).toContainText('01101₂ = 13₁₀');
  } else if (item.key === 'conditions-loops') {
    for (let i = 0; i < 8; i++) await frame.getByRole('button', {name: '执行下一轮'}).click();
    await expect(frame.locator('.summary')).toContainText('total 从 12 变为 20');
    await expect(frame.locator('.code-line[aria-current=step]')).toContainText('total += number');
    expect(await frame.getByRole('button', {name: '执行下一轮'}).isEnabled()).toBe(false);
    // Loop completion does not complete the course.
    expect((await (await page.request.get(`/api/v1/interactive/sessions/${(await (await page.request.get('/api/v1/interactive/resources')).json()).items[0].session_id}`)).json()).session.status).toBe('ACTIVE');
  } else {
    await frame.getByRole('button', {name: '下一次比较'}).click();
    await expect(frame.locator('.summary')).toContainText('找到目标 23，下标为 5');
    await frame.locator('#values').fill('3, 1, 2'); await frame.getByRole('button', {name: '应用参数'}).click();
    await expect(frame.locator('#parameter-error')).toContainText('严格递增');
  }
  await saved(page);
  const before = await frame.locator('.result, #prediction').textContent();
  const loaded = page.frames().find(frame => frame.parentFrame())!;
  await loaded.evaluate(() => { (window as Window & {workspaceMarker?: number}).workspaceMarker = 123; });
  await page.getByRole('button', {name: '专注模式', exact: true}).click();
  await expect(page.locator('.app-sidebar')).toBeHidden();
  expect(await loaded.evaluate(() => (window as Window & {workspaceMarker?: number}).workspaceMarker)).toBe(123);
  await expect.poll(() => loaded.evaluate(() => innerWidth)).toBeGreaterThan(1300);
  await loaded.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.screenshot({path: `${evidence}/${item.key}-focus.png`});
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', {name: '专注模式', exact: true})).toBeVisible();
  expect(await loaded.evaluate(() => (window as Window & {workspaceMarker?: number}).workspaceMarker)).toBe(123);
  await page.reload();
  await expect(page.getByRole('button', {name: '继续学习', exact: true})).toBeVisible();
  await page.screenshot({path: `${evidence}/${item.key}-resume.png`});
  await page.getByRole('button', {name: '继续学习', exact: true}).click();
  await expect(frame.locator('.result, #prediction')).toHaveText(before ?? '');

  if (item.key === 'conditions-loops') {
    await enableVoice(page);
    await page.locator('.interactive-more > summary').click();
    const stop = page.getByRole('button', {name: '停止讲解', exact: true});
    if (await stop.isEnabled()) await stop.click();
    await page.locator('.interactive-more > summary').click();
    await page.getByRole('button', {name: '播放讲解', exact: true}).click();
    await expect(page.getByRole('button', {name: '暂停讲解'})).toBeEnabled();
    await page.getByRole('button', {name: '暂停讲解'}).click();
    await expect(page.getByRole('button', {name: '继续讲解'})).toBeEnabled();
    await page.getByRole('button', {name: '继续讲解'}).click();
    await expect(page.locator('.interactive-audio-status')).toContainText('正在朗读本段');
    await page.getByRole('button', {name: '重播本段'}).click();
    await expect(page.getByRole('button', {name: '暂停讲解'})).toBeEnabled();
    await page.screenshot({path: `${evidence}/${item.key}-audio-playing.png`});
    await expect(page.locator('.interactive-audio-status')).toContainText('本段朗读已结束', {timeout: 10000});
    await page.route('**/api/v1/interactive/sessions/*/audio/*', route => route.fulfill({status: 503, body: 'synthetic audio failure'}));
    await page.getByRole('button', {name: '重播本段'}).click();
    await expect(page.locator('.interactive-audio-status')).toContainText('音频播放失败');
    await page.screenshot({path: `${evidence}/${item.key}-audio-failure.png`});
    await page.unroute('**/api/v1/interactive/sessions/*/audio/*');
    await page.getByLabel('静音', {exact: true}).check();
    await expect(page.locator('.interactive-audio-status')).toContainText('已静音');
    await page.getByLabel('静音', {exact: true}).uncheck();
  }
  await page.getByRole('button', {name: '下一环节', exact: true}).click();
  await expect(page.getByLabel('当前课程环节')).toHaveValue(item.key === 'ai-picture' ? 'examples' : item.key === 'binary-cards' ? 'compose' : item.key === 'conditions-loops' ? 'condition' : 'middle');
  await saved(page);
  // Without a system Chinese voice the real system path must degrade visibly.
  await enableVoice(page);
  await page.getByRole('button', {name: '重播本段'}).click();
  const voices = await page.evaluate(() => window.speechSynthesis?.getVoices().map(v => ({name: v.name, lang: v.lang})) ?? []);
  await writeFile(`${evidence}/${item.key}-voice-capability.json`, JSON.stringify(voices, null, 2));
  await expect.poll(async () => /正在朗读|播放失败|没有可用/.test(await page.locator('.interactive-audio-status').innerText()), {timeout: 8000}).toBe(true);

  for (const viewport of [{width: 1366, height: 768}, {width: 1920, height: 1080}, {width: 768, height: 1024}, {width: 390, height: 844}, {width: 320, height: 568}]) {
    await page.setViewportSize(viewport); await checkGeometry(page);
    await page.screenshot({path: `${evidence}/${item.key}-${viewport.width}x${viewport.height}.png`});
  }
  await page.setViewportSize({width: 1366, height: 768});
  await page.getByTestId('companion-dock').getByRole('button', {name: /打开.*学习助手/}).click();
  await expect(page.locator('.companion-panel--learning')).toBeVisible();
  await expect(page.locator('.interactive-guide textarea')).toHaveCount(0);
  const input = page.getByLabel('想对老师说什么', {exact: true});
  await input.fill('请结合当前环节和实验记录解释这个知识点。');
  await page.getByRole('button', {name: '收起对话', exact: true}).click();
  await page.getByRole('button', {name: '问老师', exact: true}).click();
  await expect(input).toHaveValue('请结合当前环节和实验记录解释这个知识点。');
  await page.getByTestId('send-turn').click();
  await expect(page.getByTestId('assistant-card').last()).toBeVisible({timeout: 15000});
  await expect(page.getByTestId('fixture-badge').last()).toBeVisible();
  await expect.poll(() => page.locator('.conv-messages').evaluate(el => el.clientHeight)).toBeGreaterThan(120);
  await page.screenshot({path: `${evidence}/${item.key}-teacher.png`});
  await page.setViewportSize({width: 320, height: 568});
  if (!(await page.locator('.companion-panel').isVisible())) await page.getByRole('button', {name: '问老师', exact: true}).click();
  await expect(input).toBeInViewport();
  await page.screenshot({path: `${evidence}/${item.key}-teacher-mobile.png`});
  await page.keyboard.press('Escape');
  await expect(page.locator('.companion-panel')).toHaveCount(0);
  await page.setViewportSize({width: 1366, height: 768});
  if (!(await page.locator('.companion-panel').isVisible())) await page.getByRole('button', {name: '问老师', exact: true}).click();
  await expect(frame.locator('.result, #prediction')).toHaveText(before ?? '');
  expect(errors).toEqual([]);
});

async function openJunior(page: Page) {
  await page.goto('/login'); await page.getByLabel('用户名', {exact: true}).fill('html.junior'); await page.getByLabel('密码', {exact: true}).fill('synthetic-html-pass-2026'); await page.getByRole('button', {name: '登录并继续'}).click(); await expect(page).toHaveURL(/\/workbench$/);
  const activity = (await (await page.request.get('/api/v1/interactive/resources')).json()).items[0];
  const csrf = (await (await page.request.get('/api/v1/auth/csrf')).json()).csrf_token;
  const session = await (await page.request.post('/api/v1/interactive/sessions', {data: {resource_id: activity.id, restart: true}, headers: {Origin: new URL(page.url()).origin, 'X-CSRF-Token': csrf}})).json();
  await page.goto(`/interactive/${activity.id}`); await page.getByRole('button', {name: '开始学习', exact: true}).click(); await expect(page.frameLocator('iframe').locator('body')).toHaveClass(/embedded/);
  return {activity, session};
}
async function actions(page: Page) { if (await page.locator('.interactive-more').getAttribute('open') === null) await page.locator('.interactive-more > summary').click(); }

test('JUNIOR: failed save preserves question, reset confirmation, completion and leave', async ({page}) => {
  test.setTimeout(60000); await page.setViewportSize({width: 1366, height: 768});
  const {session} = await openJunior(page); const frame = page.frameLocator('iframe');
  let turns = 0; page.on('request', request => { if (request.method() === 'POST' && /\/(turns|messages)$/.test(request.url())) turns++; });
  await page.route('**/api/v1/interactive/sessions/*/checkpoint', route => route.fulfill({status: 503, contentType: 'application/json', body: JSON.stringify({detail: '合成保存失败，操作仍在本页。'})}));
  await frame.getByRole('button', {name: '执行下一轮'}).click(); await expect(page.locator('.interactive-player-header')).toContainText('未保存');
  await page.getByRole('button', {name: '问老师', exact: true}).click();
  const input = page.getByLabel('想对老师说什么', {exact: true}); await input.fill('保存失败时保留这个问题草稿'); await page.getByTestId('send-turn').click();
  await expect(page.locator('.conv-error')).toContainText('问题草稿已保留'); await expect(input).toHaveValue('保存失败时保留这个问题草稿'); expect(turns).toBe(0);
  await page.screenshot({path: `${evidence}/conditions-loops-save-failure.png`});
  await page.unroute('**/api/v1/interactive/sessions/*/checkpoint'); await page.getByRole('button', {name: '重试保存', exact: true}).click(); await saved(page);
  await page.getByTestId('send-turn').click(); await expect(page.getByTestId('assistant-card').last()).toBeVisible(); expect(turns).toBe(1);
  await page.getByRole('button', {name: '收起对话', exact: true}).click();
  await frame.locator('#n').fill('6'); await frame.locator('#n').blur(); await expect(frame.locator('dialog')).toBeVisible(); await frame.getByRole('button', {name: '保留当前进度'}).click(); await expect(frame.locator('#n')).toHaveValue('8'); await expect(frame.locator('.result')).toContainText('number = 1');
  await actions(page); page.once('dialog', dialog => dialog.dismiss()); await page.getByRole('button', {name: '重置当前实验'}).click(); await expect(frame.locator('.result')).toContainText('number = 1');
  page.once('dialog', dialog => dialog.accept()); await page.getByRole('button', {name: '重置当前实验'}).click(); await expect(frame.locator('.result')).toContainText('number = —'); await saved(page);
  await page.getByRole('button', {name: '完成本次学习'}).click(); await expect(page.getByText('本次活动已完成', {exact: true})).toBeVisible();
  const completed = (await (await page.request.get(`/api/v1/interactive/sessions/${session.id}`)).json()).session;
  expect(completed.status).toBe('COMPLETED'); expect(completed.completion_source).toBe('SDK_REPORTED');
  await page.screenshot({path: `${evidence}/conditions-loops-completed.png`});
  await page.getByRole('link', {name: '← 返回', exact: true}).click(); await expect(page).toHaveURL(/\/activities$/); await expect(page.locator('.interactive-stage iframe')).toHaveCount(0);
});

test('JUNIOR: real Chrome 200 percent zoom keeps course and teacher controls reachable', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'k12-workspace-zoom-'));
  const context = await chromium.launchPersistentContext(directory, {channel: 'chrome', headless: true, baseURL: process.env.CODELAB_E2E_BASE_URL ?? 'http://localhost:15174', viewport: {width: 1366, height: 768}});
  try {
    const page = await context.newPage();
    await page.goto('chrome://settings/appearance'); await page.locator('select#zoomLevel').selectOption('2');
    await openJunior(page);
    expect(await page.evaluate(() => devicePixelRatio)).toBe(2); expect(await page.evaluate(() => innerWidth)).toBe(683);
    await checkGeometry(page); await page.screenshot({path: `${evidence}/conditions-loops-zoom-200.png`});
    if (!(await page.locator('.companion-panel').isVisible())) await page.getByRole('button', {name: '问老师', exact: true}).click(); await page.getByRole('button', {name: '问老师', exact: true}).click();
    await expect(page.getByLabel('想对老师说什么', {exact: true})).toBeInViewport(); await expect(page.getByRole('button', {name: '收起对话', exact: true})).toBeInViewport();
    await page.screenshot({path: `${evidence}/conditions-loops-zoom-200-teacher.png`}); await page.keyboard.press('Escape'); await expect(page.locator('.companion-panel')).toHaveCount(0);
  } finally { await context.close(); await rm(directory, {recursive: true, force: true}); }
});

test('JUNIOR: synthetic browser voices prefer Mandarin, remember selection and report missing voices', async ({page}) => {
  await page.addInitScript(() => {
    const initial = [
      {voiceURI: 'test-hk', name: '合成测试粤语', lang: 'zh-HK', default: true},
      {voiceURI: 'test-cn-a', name: '合成测试普通话 A', lang: 'zh-CN', default: false},
      {voiceURI: 'test-cn-b', name: '合成测试普通话 B', lang: 'zh-CN', default: false},
    ];
    let voices = initial;
    const events = new EventTarget();
    const history: Array<{name?: string; lang: string}> = [];
    class TestUtterance {
      voice?: {name: string}; lang = ''; rate = 1; onstart?: () => void;
      constructor(public text: string) {}
    }
    Object.defineProperty(window, 'speechSynthesis', {configurable: true, value: {
      getVoices: () => voices,
      addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events),
      speak: (speech: TestUtterance) => { history.push({name: speech.voice?.name, lang: speech.lang}); speech.onstart?.(); },
      cancel() {}, pause() {}, resume() {},
    }});
    Object.defineProperty(window, 'SpeechSynthesisUtterance', {configurable: true, value: TestUtterance});
    Object.assign(window, {syntheticVoiceHistory: history, useOnlySyntheticCantonese: () => { voices = initial.slice(0, 1); events.dispatchEvent(new Event('voiceschanged')); }});
  });
  await page.setViewportSize({width: 1366, height: 768});
  await openJunior(page); await enableVoice(page);
  const select = page.getByLabel('朗读声音', {exact: true});
  await expect(select).toBeDisabled(); await expect(select).toContainText('课件音频');
  await page.getByRole('button', {name: '下一环节', exact: true}).click(); await saved(page);
  await expect(select).toBeEnabled(); await expect(select).toHaveValue('');
  await page.getByRole('button', {name: '重播本段', exact: true}).click();
  const lastVoice = () => page.evaluate(() => (window as unknown as {syntheticVoiceHistory: Array<{name: string; lang: string}>}).syntheticVoiceHistory.at(-1));
  await expect.poll(lastVoice).toEqual({name: '合成测试普通话 A', lang: 'zh-CN'});
  await select.selectOption({label: '合成测试普通话 B · zh-CN'});
  await page.getByRole('button', {name: '重播本段', exact: true}).click();
  await expect.poll(lastVoice).toEqual({name: '合成测试普通话 B', lang: 'zh-CN'});
  const selection = await select.inputValue();
  await page.screenshot({path: `${evidence}/voice-selection-mandarin.png`});
  await page.reload(); await page.getByRole('button', {name: '继续学习', exact: true}).click();
  await expect(select).toHaveValue(selection);
  await page.evaluate(() => (window as unknown as {useOnlySyntheticCantonese: () => void}).useOnlySyntheticCantonese());
  await expect(page.locator('.interactive-audio-status')).toContainText('所选声音当前不可用');
  await select.selectOption(''); await page.getByRole('button', {name: '重播本段', exact: true}).click();
  await expect(page.locator('.interactive-audio-status')).toContainText('没有可用的普通话声音');
  await page.screenshot({path: `${evidence}/voice-selection-unavailable.png`});
  await select.selectOption({label: '合成测试粤语 · zh-HK'}); await page.getByRole('button', {name: '重播本段', exact: true}).click();
  await expect.poll(lastVoice).toEqual({name: '合成测试粤语', lang: 'zh-HK'});
});

test('JUNIOR: start and resume play the introduction once, with real media events and a mute opt-out', async ({page}) => {
  test.setTimeout(60000);
  await page.addInitScript(() => {
    const observations = {plays: 0, playing: 0, ended: 0};
    Object.assign(window, {introAudioObservations: observations});
    const nativePlay = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function () {
      if (this.src.includes('/interactive/sessions/')) {
        observations.plays++;
        this.addEventListener('playing', () => { observations.playing++; }, {once: true});
        this.addEventListener('ended', () => { observations.ended++; }, {once: true});
      }
      return nativePlay.call(this);
    };
  });
  await page.setViewportSize({width: 1366, height: 768});
  await page.goto('/login'); await page.getByLabel('用户名', {exact: true}).fill('html.junior'); await page.getByLabel('密码', {exact: true}).fill('synthetic-html-pass-2026'); await page.getByRole('button', {name: '登录并继续'}).click(); await expect(page).toHaveURL(/\/workbench$/);
  const me = await (await page.request.get('/api/v1/me')).json();
  const csrf = (await (await page.request.get('/api/v1/auth/csrf')).json()).csrf_token;
  const preferences = await page.request.patch('/api/v1/me/preferences', {data: {base_revision: me.preferences.profile_revision, voice_preference: 'DISABLED'}, headers: {Origin: new URL(page.url()).origin, 'X-CSRF-Token': csrf}});
  expect(preferences.ok()).toBe(true);
  const activity = (await (await page.request.get('/api/v1/interactive/resources')).json()).items[0];
  await page.request.post('/api/v1/interactive/sessions', {data: {resource_id: activity.id, restart: true}, headers: {Origin: new URL(page.url()).origin, 'X-CSRF-Token': csrf}});
  await page.goto(`/interactive/${activity.id}`);
  await expect(page.getByRole('button', {name: '开启朗读', exact: true})).toBeVisible();
  await page.getByRole('button', {name: '开始学习', exact: true}).click();
  const observations = () => page.evaluate(() => (window as unknown as {introAudioObservations: {plays: number; playing: number; ended: number}}).introAudioObservations);
  await expect(page.locator('.interactive-audio-status')).toContainText('正在朗读本段');
  await expect.poll(observations).toEqual({plays: 1, playing: 1, ended: 0});
  await page.getByRole('button', {name: '收起讲解', exact: true}).click();
  await page.getByRole('button', {name: '本步讲解', exact: true}).click();
  await page.getByRole('button', {name: '专注模式', exact: true}).click();
  await page.getByRole('button', {name: '退出专注', exact: true}).click();
  await expect(page.locator('.interactive-audio-status')).toContainText('本段朗读已结束', {timeout: 10000});
  await expect.poll(observations).toEqual({plays: 1, playing: 1, ended: 1});
  expect((await (await page.request.get('/api/v1/me')).json()).preferences.voice_preference).toBe('DISABLED');
  await page.frameLocator('iframe').getByRole('button', {name: '执行下一轮'}).click(); await saved(page);
  await page.reload(); await page.getByRole('button', {name: '继续学习', exact: true}).click();
  await expect(page.locator('.interactive-audio-status')).toContainText('正在朗读本段');
  await expect.poll(observations).toEqual({plays: 1, playing: 1, ended: 0});
  await page.screenshot({path: `${evidence}/start-auto-narration.png`});
  await page.reload(); await expect(page.getByRole('button', {name: '继续学习', exact: true})).toBeVisible(); await enableVoice(page); await page.getByLabel('静音', {exact: true}).check();
  await page.getByRole('button', {name: '继续学习', exact: true}).click();
  await expect(page.frameLocator('iframe').locator('body')).toHaveClass(/embedded/);
  await expect(page.locator('.interactive-audio-status')).toContainText('已静音');
  expect(await observations()).toEqual({plays: 0, playing: 0, ended: 0});
});
